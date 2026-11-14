"""
Orchestrator — one call produces the full analysis the frontend needs.

Flow (every upstream call goes through intelligenceM4.providers):
  1. Inputs were validated by AnalyzeRequest (M1 registry: location/scenario/year).
  2. M3: farm profile if M3 implements it, else the FarmContext in the request.
  3. In parallel: M1 scenarios, M1 history, M2 rotation evaluation, M2 alternatives.
  4. M2 suitability for EVERY crop in the current rotation and the alternatives,
     with M1's projected temperature for the selected scenario/year and the
     farmer's soil pH (when supplied). M4 only *selects* M1's value and records
     its field_path; it never computes one. No value -> nothing is passed and
     the blind-spot detector reports it.
  5. M2 water demand and M5 resilience, if implemented.
  6. AnalysisBundle -> Evidence Passport + Blind-Spot Report (existing code).

Robustness: every provider call has a timeout and returns a ProviderResult, so a
failing or slow module becomes "unavailable" and the analysis continues with
what is available. Only invalid input (rejected by AnalyzeRequest) is a 4xx.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Callable

from pydantic import BaseModel

from intelligenceM4 import blind_spot_detector
from intelligenceM4.evidence_passport import build_passport
from intelligenceM4.providers import (
    agriculture_provider,
    climate_provider,
    describe_error,
    farm_provider,
    resilience_provider,
)
from intelligenceM4.schemas import (
    AgricultureInput,
    AnalysisBundle,
    AnalyzeRequest,
    AnalyzeResponse,
    CallReport,
    ClimateInput,
    FarmContext,
    ModuleReport,
    ProviderResult,
    ScenarioResponse,
    SuitabilityInput,
)

TEMPERATURE_NOTE = (
    "M1 ensemble-mean annual mean air temperature for the selected scenario and year: "
    "an annual regional projection, not a growing-season or field measurement."
)


# ---------------------------------------------------------------------------
# Timeouts (seconds, from the environment; read per request)
# ---------------------------------------------------------------------------

def _seconds(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def scenarios_timeout() -> float:
    return _seconds("M4_SCENARIOS_TIMEOUT_SECONDS", 90.0)


def history_timeout() -> float:
    return _seconds("M4_HISTORY_TIMEOUT_SECONDS", 30.0)


def module_timeout() -> float:
    """Timeout for each synchronous M2 / M3 / M5 provider call."""
    return _seconds("M4_MODULE_TIMEOUT_SECONDS", 30.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _sync(module: str, called: str, fn: Callable[[], ProviderResult]) -> ProviderResult:
    """Run a synchronous provider call in a thread, bounded by module_timeout()."""
    limit = module_timeout()
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn), timeout=limit)
    except asyncio.TimeoutError:
        return ProviderResult(module=module, status="unavailable", called=called,
                              error=f"TimeoutError: no response within {limit:g}s")
    except Exception as exc:  # providers never raise, but never let one fail /analyze
        return ProviderResult(module=module, status="unavailable", called=called,
                              error=describe_error(exc))


async def _done(result: ProviderResult) -> ProviderResult:
    return result


def _skipped(module: str, called: str, reason: str) -> ProviderResult:
    return ProviderResult(module=module, status="unavailable", called=called, error=reason)


def select_temperature(scenarios: ScenarioResponse | None, scenario: str | None,
                       year: int | None) -> SuitabilityInput | None:
    """M1's ensemble-mean temperature for the selected scenario/year, with its field_path."""
    if scenarios is None or scenario is None or year is None:
        return None
    for i, ensemble in enumerate(scenarios.ensemble):
        if ensemble.id != scenario:
            continue
        for j, value in enumerate(ensemble.values):
            if value.year == year:
                return SuitabilityInput(
                    factor="temperature_c", value=value.temperature_c.mean, unit="°C",
                    source_module="M1",
                    field_path=f"climate.scenarios.ensemble[{i}].values[{j}].temperatureC.mean",
                    note=TEMPERATURE_NOTE,
                )
    return None


def select_soil_ph(farm: FarmContext) -> SuitabilityInput | None:
    if farm.soil_ph is None:
        return None
    return SuitabilityInput(factor="soil_ph", value=farm.soil_ph, unit="pH",
                            source_module=farm.source, field_path="farm.soil_ph")


def module_report(results: list[ProviderResult]) -> ModuleReport:
    """Aggregate one module's calls. not_implemented calls don't degrade the status."""
    implemented = [r for r in results if r.status != "not_implemented"]
    if not implemented:
        status = "not_implemented"
    elif all(r.status == "unavailable" for r in implemented):
        status = "unavailable"
    elif all(r.status == "ok" for r in implemented):
        status = "ok"
    else:
        status = "partial"
    errors = [f"{r.called}: {r.error}" for r in results if r.error]
    return ModuleReport(
        status=status,
        called="; ".join(dict.fromkeys(r.called for r in results)) or None,
        error="; ".join(dict.fromkeys(errors)) or None,
        calls=[CallReport(called=r.called, status=r.status, error=r.error) for r in results],
    )


def _data(result: ProviderResult) -> Any:
    return result.data if result.usable else None


def _as_dict(data: Any) -> dict[str, Any] | None:
    if data is None:
        return None
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    analysis_id = request.analysis_id or f"analysis-{uuid.uuid4().hex[:12]}"
    calls: dict[str, list[ProviderResult]] = {"M1": [], "M2": [], "M3": [], "M5": []}

    # -- M3: farm context ------------------------------------------------------
    farm = request.farm
    if farm_provider.farm_profile_implemented():
        if farm.farm_id:
            m3 = await _sync("M3", farm_provider.FARM_CALL,
                             lambda: farm_provider.get_farm_context(farm.farm_id))
            if m3.usable:
                farm = m3.data
        else:
            m3 = _skipped("M3", farm_provider.FARM_CALL,
                          "No farm_id supplied; the farm context from the request was used.")
    else:
        m3 = farm_provider.get_farm_context(farm.farm_id or "")
    calls["M3"].append(m3)

    crops = list(farm.current_rotation or [])
    location = farm.location_id

    # -- M1 + M2 rotation/alternatives, concurrently ---------------------------
    no_rotation = "No current rotation was supplied for this farm."
    scen, hist, rotation, alternatives = await asyncio.gather(
        climate_provider.get_scenarios(location, timeout=scenarios_timeout()),
        climate_provider.get_history(location, timeout=history_timeout()),
        _sync("M2", agriculture_provider.ROTATION_CALL,
              lambda: agriculture_provider.evaluate_rotation(crops)) if crops else
        _done(_skipped("M2", agriculture_provider.ROTATION_CALL, no_rotation)),
        _sync("M2", agriculture_provider.GENERATE_CALL,
              lambda: agriculture_provider.generate_alternatives(crops, request.max_alternatives))
        if crops else
        _done(_skipped("M2", agriculture_provider.GENERATE_CALL, no_rotation)),
    )
    calls["M1"] += [scen, hist]
    calls["M2"] += [rotation, alternatives]

    # -- M2 suitability for every crop, with selected inputs -------------------
    temperature = select_temperature(_data(scen), request.scenario, request.year)
    soil_ph = select_soil_ph(farm)
    suitability_crops = list(crops)
    if alternatives.usable:
        for alt in alternatives.data.alternative_rotations:
            suitability_crops += alt.rotation
    suitability_crops = list(dict.fromkeys(suitability_crops))

    def screen(crop: str) -> Callable[[], ProviderResult]:
        return lambda: agriculture_provider.check_suitability(
            crop,
            temperature_c=temperature.value if temperature else None,
            soil_ph=soil_ph.value if soil_ph else None,
        )

    suitability = list(await asyncio.gather(*[
        _sync("M2", agriculture_provider.SUITABILITY_CALL, screen(crop))
        for crop in suitability_crops
    ]))
    calls["M2"] += suitability

    # -- M2 water, M5 resilience ----------------------------------------------
    if agriculture_provider.water_demand_implemented() and crops:
        water = await _sync("M2", agriculture_provider.WATER_CALL,
                            lambda: agriculture_provider.get_water_demand(crops))
    else:  # returns not_implemented immediately; no M2 code runs
        water = agriculture_provider.get_water_demand(crops)
    calls["M2"].append(water)

    if resilience_provider.resilience_implemented():
        resilience = await _sync(
            "M5", resilience_provider.RESILIENCE_CALL,
            lambda: resilience_provider.get_resilience(
                location, request.scenario, request.year, crops))
    else:
        resilience = resilience_provider.get_resilience(
            location, request.scenario, request.year, crops)
    calls["M5"].append(resilience)

    # -- Bundle -> passport + blind spots (existing code) ---------------------
    bundle = AnalysisBundle(
        analysis_id=analysis_id,
        farm=farm,
        selected_scenario=request.scenario,
        selected_year=request.year,
        climate=ClimateInput(scenarios=_data(scen), history=_data(hist)),
        agriculture=AgricultureInput(
            rotation=_data(rotation),
            alternatives=_data(alternatives),
            suitability=[r.data for r in suitability if r.usable],
            water=_as_dict(_data(water)),
            suitability_inputs=[i for i in (temperature, soil_ph) if i is not None],
        ),
        resilience=_data(resilience),
    )
    return AnalyzeResponse(
        analysis_id=analysis_id,
        modules={module: module_report(results) for module, results in calls.items()},
        bundle=bundle,
        passport=build_passport(bundle),
        blind_spot_report=blind_spot_detector.build_report(bundle),
    )
