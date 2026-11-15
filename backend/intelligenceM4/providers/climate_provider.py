"""
M1 adapter — calls climateM1 service-layer functions in-process.

Calls
-----
* climateM1.services.projections.fetch_scenarios(location)
    Has its own per-model cache (with stale fallback) inside the service layer.
* climateM1.services.history.fetch_history(location, start, end)
    Uses the service-layer source-response cache, including for in-process M4 calls.
* climateM1.services.model_registry / climateM1.services.locations
    Registry lookups used to validate scenario ids, years and location ids.

Every payload is validated with M1's own response models, so M4 sees exactly
the shape the M1 HTTP API would return.
"""

from __future__ import annotations

from datetime import date

from climateM1.models.climate import HistoryResponse, ScenarioResponse

from intelligenceM4.providers import safe_call_async
from intelligenceM4.schemas import ModuleStatus, ProviderResult

SCENARIOS_CALL = "climateM1.services.projections.fetch_scenarios"
HISTORY_CALL = "climateM1.services.history.fetch_history"

# Mirrors the defaults of M1's GET /api/climate/history route.
HISTORY_DEFAULT_START = date(2021, 1, 1)
HISTORY_DEFAULT_END = date(2025, 12, 31)


# ---------------------------------------------------------------------------
# Registry lookups (return None when M1's registry cannot be read)
# ---------------------------------------------------------------------------

def registered_scenarios() -> dict[str, str] | None:
    """Scenario id -> label (e.g. "ssp370" -> "SSP3-7.0") from M1's registry."""
    try:
        from climateM1.services.model_registry import get_scenarios
        return {str(s["id"]): str(s.get("label", s["id"])) for s in get_scenarios()}
    except Exception:
        return None


def registered_scenario_ids() -> set[str] | None:
    scenarios = registered_scenarios()
    return None if scenarios is None else set(scenarios)


def registered_projection_years() -> set[int] | None:
    try:
        from climateM1.services.model_registry import get_projection_years
        return {int(y) for y in get_projection_years()}
    except Exception:
        return None


def registered_location_ids() -> set[str] | None:
    try:
        from climateM1.services.locations import LOCATIONS
        return set(LOCATIONS)
    except Exception:
        return None


def _get_location(location_id: str):
    from climateM1.services.locations import LOCATIONS

    location = LOCATIONS.get(location_id)
    if location is None:
        raise LookupError(f"Unknown M1 location: {location_id}")
    return location


# ---------------------------------------------------------------------------
# Status — read straight from M1's own completeness flags
# ---------------------------------------------------------------------------

def scenario_status(response: ScenarioResponse) -> ModuleStatus:
    incomplete = (
        response.provenance.missing_data
        or not response.ensemble
        or any(model.status != "success" for model in response.model_results)
    )
    return "partial" if incomplete else "ok"


def history_status(response: HistoryResponse) -> ModuleStatus:
    if not response.timeseries or any(p.missing_data for p in response.provenance):
        return "partial"
    return "ok"


# ---------------------------------------------------------------------------
# Provider calls
# ---------------------------------------------------------------------------

async def get_scenarios(location_id: str, timeout: float | None = None) -> ProviderResult:
    async def _call() -> ScenarioResponse:
        from climateM1.services.projections import fetch_scenarios

        payload = await fetch_scenarios(_get_location(location_id))
        return ScenarioResponse.model_validate(payload)

    return await safe_call_async("M1", SCENARIOS_CALL, _call, scenario_status, timeout)


async def get_history(
    location_id: str,
    start: date = HISTORY_DEFAULT_START,
    end: date = HISTORY_DEFAULT_END,
    timeout: float | None = None,
) -> ProviderResult:
    async def _call() -> HistoryResponse:
        from climateM1.services.history import fetch_history

        if end < start:
            raise ValueError("History end date must be on or after the start date")
        payload = await fetch_history(
            _get_location(location_id),
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
        )
        return HistoryResponse.model_validate(payload)

    return await safe_call_async("M1", HISTORY_CALL, _call, history_status, timeout)
