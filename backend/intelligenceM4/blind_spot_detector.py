"""
Blind-Spot Detector — deterministic rules for missing or incomplete evidence.

Every rule reads only what M1/M2/M3/M5 or the farmer supplied in the
AnalysisBundle, plus read-only capability probes that report whether an
upstream function exists (they never execute upstream code).

Guarantees
----------
* The bundle is never modified and no default value is ever filled in.
* Message / action text comes from fixed templates (TEMPLATES) and follows the
  evidence claim rule: no measured numbers. Specific values (grid resolution,
  model ids, missing inputs) go into `affects` and traceable `citations`.
* One blind spot per code; sorted critical -> warning -> info, then rule order.
* The Evidence Passport calls detect_blind_spots(), so /evidence and
  /blind-spots always report the same blind spots for the same bundle.
"""

from __future__ import annotations

from typing import Any

from intelligenceM4.providers import (
    agriculture_provider,
    climate_provider,
    farm_provider,
    resilience_provider,
)
from intelligenceM4.schemas import (
    AnalysisBundle,
    BlindSpot,
    BlindSpotReport,
    Citation,
    ModuleStatus,
    UpstreamModule,
)
from intelligenceM4.traceability import verify_citations

# ---------------------------------------------------------------------------
# Codes and templates
# ---------------------------------------------------------------------------

ROTATION_UNAVAILABLE = "ROTATION_UNAVAILABLE"
CLIMATE_PROJECTIONS_UNAVAILABLE = "CLIMATE_PROJECTIONS_UNAVAILABLE"
CLIMATE_PROJECTIONS_PARTIAL = "CLIMATE_PROJECTIONS_PARTIAL"
CLIMATE_HISTORY_UNAVAILABLE = "CLIMATE_HISTORY_UNAVAILABLE"
CLIMATE_HISTORY_PARTIAL = "CLIMATE_HISTORY_PARTIAL"
CROP_REFERENCE_INCOMPLETE = "CROP_REFERENCE_INCOMPLETE"
SUITABILITY_INPUT_NOT_PASSED = "SUITABILITY_INPUT_NOT_PASSED"
CROP_SUITABILITY_NOT_SCREENED = "CROP_SUITABILITY_NOT_SCREENED"
SOIL_PH_MISSING = "SOIL_PH_MISSING"
IRRIGATION_BUDGET_MISSING = "IRRIGATION_BUDGET_MISSING"
WATER_DEMAND_NOT_IMPLEMENTED = "WATER_DEMAND_NOT_IMPLEMENTED"
M2_WATER_DATA_MISSING = "M2_WATER_DATA_MISSING"
M5_RESILIENCE_DATA_MISSING = "M5_RESILIENCE_DATA_MISSING"

# M2 suitability `missing` entries ending with this suffix are catalog gaps;
# any other entry is an input the suitability call did not receive.
REFERENCE_RANGE_SUFFIX = "_reference_range"
REGISTRY_UNREADABLE = "M1_REGISTRY_UNREADABLE"
CLIMATE_RESOLUTION = "CLIMATE_RESOLUTION"
M3_NOT_IMPLEMENTED = "M3_NOT_IMPLEMENTED"
M5_NOT_IMPLEMENTED = "M5_NOT_IMPLEMENTED"

# code -> category, severity, source_module, message, farmer_action, team_action
TEMPLATES: dict[str, dict[str, Any]] = {
    ROTATION_UNAVAILABLE: dict(
        category="module", severity="critical", source_module="M2",
        message=("No crop rotation analysis from M2 is available, so the rotation "
                 "cannot be explained or assessed."),
        farmer_action="Confirm the crops in your current rotation.",
        team_action="M2: rotation evaluation did not return a result for this analysis.",
    ),
    CLIMATE_PROJECTIONS_UNAVAILABLE: dict(
        category="module", severity="critical", source_module="M1",
        message=("No future climate projections from M1 are available, so future "
                 "climate constraints cannot be assessed."),
        team_action="M1: scenario projections could not be retrieved for this location.",
    ),
    CLIMATE_PROJECTIONS_PARTIAL: dict(
        category="climate", severity="warning", source_module="M1",
        message=("M1 reports that the climate projections are incomplete. Ensemble "
                 "values rest on fewer models or fewer days than configured; the "
                 "affected models are listed."),
        team_action="M1: retry or refresh the incomplete model results.",
    ),
    CLIMATE_HISTORY_UNAVAILABLE: dict(
        category="climate", severity="warning", source_module="M1",
        message=("No historical climate observations from M1 are available, so "
                 "recent observed conditions cannot be compared with projections."),
        team_action=("M1: historical observations could not be retrieved; NASA POWER "
                     "may be unreachable and history caching is only in the M1 route."),
    ),
    CLIMATE_HISTORY_PARTIAL: dict(
        category="climate", severity="warning", source_module="M1",
        message="M1 reports missing days in the historical climate record.",
        team_action="M1: check NASA POWER coverage for the requested period.",
    ),
    CROP_REFERENCE_INCOMPLETE: dict(
        category="crop_reference", severity="warning", source_module="M2",
        message=("M2's crop catalog has no reference range for one or more factors, "
                 "so suitability could not be screened for the affected crops. The "
                 "absent ranges reported by M2 are cited."),
        team_action=("M2: add verified temperature, rainfall and soil pH reference "
                     "ranges to the crop catalog."),
    ),
    SUITABILITY_INPUT_NOT_PASSED: dict(
        category="module", severity="warning", source_module="M4",
        message=("M2 suitability screening was run without inputs that should have "
                 "been supplied to it, so those factors were not checked and any "
                 "catalog gaps for them stay hidden. The inputs M2 reports as "
                 "missing are cited."),
        team_action=("M4: the orchestrator must pass M1's projected temperature for "
                     "the selected scenario and year, and the farmer's soil pH when "
                     "provided, into M2 suitability."),
    ),
    CROP_SUITABILITY_NOT_SCREENED: dict(
        category="crop_reference", severity="warning", source_module="M4",
        message=("No M2 suitability screening was supplied for the affected crops, "
                 "so their suitability for this field is unknown."),
        team_action="M4: the orchestrator must request M2 suitability for every rotation crop.",
    ),
    SOIL_PH_MISSING: dict(
        category="soil", severity="warning", source_module="farmer",
        message=("Soil pH was not provided, so crop soil requirements cannot be "
                 "checked for this field."),
        farmer_action=("Provide the soil pH from a recent soil test of this field "
                       "(laboratory test or calibrated field kit)."),
    ),
    IRRIGATION_BUDGET_MISSING: dict(
        category="water", severity="warning", source_module="farmer",
        message=("No irrigation water budget was provided, so the rotation cannot "
                 "be checked against the water you have available."),
        farmer_action=("Provide the irrigation water available for the whole "
                       "rotation, in cubic metres."),
    ),
    WATER_DEMAND_NOT_IMPLEMENTED: dict(
        category="water", severity="warning", source_module="M2",
        message=("Crop water demand has not been calculated, because M2 does not yet "
                 "provide a water-demand service in the unified backend."),
        team_action=("M2: provide a water-demand service function (the coefficient "
                     "file path in the water wallet needs fixing) and agree a "
                     "reference evapotranspiration source with M1."),
    ),
    M2_WATER_DATA_MISSING: dict(
        category="water", severity="warning", source_module="M2",
        message=("M2 provides a water-demand service, but this analysis contains no "
                 "water results, so crop water demand has not been assessed."),
        team_action=("M4: the orchestrator must include M2's water-demand result for "
                     "this rotation; if the M2 call failed, its error is in the "
                     "module status."),
    ),
    M5_RESILIENCE_DATA_MISSING: dict(
        category="module", severity="warning", source_module="M5",
        message=("M5 provides climate stress tests, but this analysis contains no "
                 "resilience results, so resilience has not been assessed."),
        team_action=("M4: the orchestrator must include M5's stress-test results for "
                     "the selected scenario and year; if the M5 call failed, its "
                     "error is in the module status."),
    ),
    REGISTRY_UNREADABLE: dict(
        category="module", severity="warning", source_module="M1",
        message=("The selected scenario/year could not be validated against M1's "
                 "registry because the registry could not be read. The identifiers "
                 "were passed through unchanged and may not match any M1 projection."),
        team_action=("M1: check that the model registry and the location registry "
                     "are present and readable."),
    ),
    CLIMATE_RESOLUTION: dict(
        category="resolution", severity="info", source_module="M1",
        message=("Climate values describe regional model-grid conditions, not "
                 "field-level forecasts. M1's reported grid resolution and caveat "
                 "are cited."),
    ),
    M3_NOT_IMPLEMENTED: dict(
        category="module", severity="info", source_module="M3",
        message=("M3 does not yet provide farm profiles, so farm details come only "
                 "from what was entered directly."),
        team_action="M3: publish the agreed farm profile function.",
    ),
    M5_NOT_IMPLEMENTED: dict(
        category="module", severity="info", source_module="M5",
        message=("M5 does not yet provide climate stress tests, so resilience under "
                 "future scenarios has not been assessed."),
        team_action="M5: publish the agreed stress-test function.",
    ),
}

RULE_ORDER: list[str] = list(TEMPLATES)
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _spot(code: str, affects: list[str] | None = None,
          citations: list[Citation] | None = None) -> BlindSpot:
    return BlindSpot(code=code, affects=affects or [], citations=citations or [],
                     **TEMPLATES[code])


def rotation_crops(bundle: AnalysisBundle) -> list[str]:
    """Crops under analysis: M2's rotation, else the farmer's current rotation."""
    if bundle.agriculture.rotation is not None:
        return list(bundle.agriculture.rotation.rotation)
    return list(bundle.farm.current_rotation or [])


# ---------------------------------------------------------------------------
# Rules (each returns 0..n blind spots; none mutates the bundle)
# ---------------------------------------------------------------------------

def _rotation_rule(b: AnalysisBundle) -> list[BlindSpot]:
    if b.agriculture.rotation is None:
        return [_spot(ROTATION_UNAVAILABLE, affects=list(b.farm.current_rotation or []))]
    return []


def _projection_rules(b: AnalysisBundle) -> list[BlindSpot]:
    scen = b.climate.scenarios
    if scen is None:
        return [_spot(CLIMATE_PROJECTIONS_UNAVAILABLE)]

    failed = [(i, m) for i, m in enumerate(scen.model_results) if m.status != "success"]
    if not scen.provenance.missing_data and not failed:
        return []

    citations = [Citation(label="M1 missing-data flag", value=scen.provenance.missing_data,
                          source_module="M1",
                          field_path="climate.scenarios.provenance.missingData")]
    for i, model in failed:
        citations += [
            Citation(label="Model reported by M1", value=model.id, source_module="M1",
                     field_path=f"climate.scenarios.modelResults[{i}].id"),
            Citation(label="Model status reported by M1", value=model.status,
                     source_module="M1",
                     field_path=f"climate.scenarios.modelResults[{i}].status"),
        ]
    return [_spot(CLIMATE_PROJECTIONS_PARTIAL,
                  affects=[f"model:{m.id}" for _, m in failed], citations=citations)]


def _history_rules(b: AnalysisBundle) -> list[BlindSpot]:
    hist = b.climate.history
    if hist is None:
        return [_spot(CLIMATE_HISTORY_UNAVAILABLE)]
    flagged = [(i, p) for i, p in enumerate(hist.provenance) if p.missing_data]
    if not flagged:
        return []
    return [_spot(
        CLIMATE_HISTORY_PARTIAL,
        affects=[f"variable:{p.variable}" for _, p in flagged],
        citations=[Citation(label="M1 missing-data flag", value=True, source_module="M1",
                            field_path=f"climate.history.provenance[{i}].missingData")
                   for i, _ in flagged],
    )]


def _suitability_rules(b: AnalysisBundle) -> list[BlindSpot]:
    """Split M2's `missing` list by meaning (see REFERENCE_RANGE_SUFFIX).

    * "<factor>_reference_range" -> CROP_REFERENCE_INCOMPLETE (M2 catalog gap)
    * "soil_ph" with no farmer pH  -> already SOIL_PH_MISSING (farmer); not repeated
    * any other input             -> SUITABILITY_INPUT_NOT_PASSED (M4 wiring)
    * rotation crop with no result -> CROP_SUITABILITY_NOT_SCREENED (M4 wiring)
    Each cited item points at its exact position in M2's `missing` list.
    """
    results = b.agriculture.suitability
    gaps: dict[str, list[Citation]] = {}
    inputs: dict[str, list[Citation]] = {}

    for i, res in enumerate(results):
        for j, item in enumerate(res.missing):
            path = f"agriculture.suitability[{i}].missing[{j}]"
            if item.endswith(REFERENCE_RANGE_SUFFIX):
                gaps.setdefault(res.crop_id, []).append(Citation(
                    label="Reference range absent from M2 crop catalog", value=item,
                    source_module="M2", field_path=path))
            elif item == "soil_ph" and b.farm.soil_ph is None:
                continue  # farmer has not provided it: SOIL_PH_MISSING covers this
            else:
                inputs.setdefault(res.crop_id, []).append(Citation(
                    label="Input M2 reports it did not receive", value=item,
                    source_module="M2", field_path=path))

    spots = []
    if gaps:
        spots.append(_spot(CROP_REFERENCE_INCOMPLETE, affects=list(gaps),
                           citations=[c for cs in gaps.values() for c in cs]))
    if inputs:
        spots.append(_spot(SUITABILITY_INPUT_NOT_PASSED, affects=list(inputs),
                           citations=[c for cs in inputs.values() for c in cs]))
    screened = {r.crop_id for r in results}
    unscreened = [c for c in dict.fromkeys(rotation_crops(b)) if c not in screened]
    if unscreened:
        spots.append(_spot(CROP_SUITABILITY_NOT_SCREENED, affects=unscreened))
    return spots


def _farm_rules(b: AnalysisBundle) -> list[BlindSpot]:
    spots = []
    if b.farm.soil_ph is None:
        spots.append(_spot(SOIL_PH_MISSING, affects=list(dict.fromkeys(rotation_crops(b)))))
    if b.farm.irrigation_budget_m3 is None:
        spots.append(_spot(IRRIGATION_BUDGET_MISSING))
    return spots


def _water_rule(b: AnalysisBundle) -> list[BlindSpot]:
    if b.agriculture.water is not None:
        return []
    code = (M2_WATER_DATA_MISSING if agriculture_provider.water_demand_implemented()
            else WATER_DEMAND_NOT_IMPLEMENTED)
    return [_spot(code, affects=list(dict.fromkeys(rotation_crops(b))))]


def _resilience_rule(b: AnalysisBundle) -> list[BlindSpot]:
    if b.resilience is None and resilience_provider.resilience_implemented():
        return [_spot(M5_RESILIENCE_DATA_MISSING)]
    return []


def registry_blind_spots(bundle: AnalysisBundle) -> list[BlindSpot]:
    """Identifiers that passed through unvalidated because M1's registry was unreadable."""
    unvalidated: list[str] = []

    scenarios = [bundle.selected_scenario]
    years = [bundle.selected_year]
    if bundle.resilience is not None:
        scenarios.append(bundle.resilience.scenario)
        years.append(bundle.resilience.year)

    if climate_provider.registered_scenario_ids() is None:
        unvalidated += [f"scenario:{s}" for s in dict.fromkeys(scenarios) if s is not None]
    if climate_provider.registered_projection_years() is None:
        unvalidated += [f"year:{y}" for y in dict.fromkeys(years) if y is not None]
    if climate_provider.registered_location_ids() is None:
        unvalidated.append(f"location:{bundle.farm.location_id}")

    return [_spot(REGISTRY_UNREADABLE, affects=unvalidated)] if unvalidated else []


def _resolution_rule(b: AnalysisBundle) -> list[BlindSpot]:
    citations: list[Citation] = []
    scen, hist = b.climate.scenarios, b.climate.history
    if scen is not None:
        citations.append(Citation(
            label="M1 reported projection grid resolution",
            value=scen.provenance.grid_resolution, source_module="M1",
            field_path="climate.scenarios.provenance.gridResolution"))
        if scen.provenance.caveat:
            citations.append(Citation(
                label="M1 projection caveat", value=scen.provenance.caveat,
                source_module="M1", field_path="climate.scenarios.provenance.caveat"))
    if hist is not None and hist.provenance:
        citations.append(Citation(
            label="M1 reported observation grid resolution",
            value=hist.provenance[0].grid_resolution, source_module="M1",
            field_path="climate.history.provenance[0].gridResolution"))
    return [_spot(CLIMATE_RESOLUTION, citations=citations)] if citations else []


def _module_rules(b: AnalysisBundle) -> list[BlindSpot]:
    spots = []
    if not farm_provider.farm_profile_implemented():
        spots.append(_spot(M3_NOT_IMPLEMENTED))
    if not resilience_provider.resilience_implemented():
        spots.append(_spot(M5_NOT_IMPLEMENTED))
    return spots


RULES = (
    _rotation_rule,
    _projection_rules,
    _history_rules,
    _suitability_rules,
    _farm_rules,
    _water_rule,
    _resilience_rule,
    registry_blind_spots,
    _resolution_rule,
    _module_rules,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_blind_spots(bundle: AnalysisBundle) -> list[BlindSpot]:
    """All blind spots for a bundle: deduplicated by code, sorted by severity."""
    by_code: dict[str, BlindSpot] = {}
    for rule in RULES:
        for spot in rule(bundle):
            by_code.setdefault(spot.code, spot)
    return sorted(
        by_code.values(),
        key=lambda s: (SEVERITY_ORDER[s.severity], RULE_ORDER.index(s.code)),
    )


def module_status(bundle: AnalysisBundle) -> dict[UpstreamModule, ModuleStatus]:
    """Status of each upstream module as reflected in the bundle (always 4 keys)."""
    scen, hist = bundle.climate.scenarios, bundle.climate.history
    agri = bundle.agriculture

    if scen is None and hist is None:
        m1: ModuleStatus = "unavailable"
    elif (scen is None or hist is None
          or scen.provenance.missing_data
          or any(m.status != "success" for m in scen.model_results)
          or any(p.missing_data for p in hist.provenance)):
        m1 = "partial"
    else:
        m1 = "ok"

    if agri.rotation is None:
        m2: ModuleStatus = (
            "partial" if (agri.alternatives or agri.suitability or agri.water) else "unavailable")
    elif (agri.water is None
          or any(r.status == "insufficient_data" for r in agri.suitability)
          or set(rotation_crops(bundle)) - {r.crop_id for r in agri.suitability}):
        m2 = "partial"
    else:
        m2 = "ok"

    if not farm_provider.farm_profile_implemented():
        m3: ModuleStatus = "not_implemented"
    else:
        m3 = "ok" if bundle.farm.source == "M3" else "unavailable"

    if not resilience_provider.resilience_implemented():
        m5: ModuleStatus = "not_implemented"
    else:
        m5 = "ok" if bundle.resilience is not None else "unavailable"

    return {"M1": m1, "M2": m2, "M3": m3, "M5": m5}


def build_report(bundle: AnalysisBundle) -> BlindSpotReport:
    blind_spots = detect_blind_spots(bundle)
    verify_citations(blind_spots, bundle.model_dump(by_alias=True, mode="json"))
    return BlindSpotReport(
        analysis_id=bundle.analysis_id,
        blind_spots=blind_spots,
        module_status=module_status(bundle),
    )
