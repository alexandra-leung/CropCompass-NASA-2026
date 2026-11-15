"""Phase 3 — Blind-Spot Detector and POST /api/intelligence/blind-spots.

Upstream data comes from REAL M1/M2 fixtures. Where a test needs a state the
real data does not have, it copies a real fixture and changes one flag, or
supplies clearly marked test-only values.
"""

import copy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import app
from intelligenceM4 import blind_spot_detector as bsd
from intelligenceM4.evidence_passport import build_passport
from intelligenceM4.fixtures import load_fixture
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
    claim_has_disallowed_digits,
)
from intelligenceM4.traceability import TraceabilityError, verify_citations

SCENARIOS = "m1_scenarios__pamplemousses-04.json"
HISTORY = "m1_history__pamplemousses-04.json"
ROTATION = "m2_rotation__maize-cowpea-cabbage.json"
SUIT_COWPEA = "m2_suitability__cowpea__no-inputs.json"
WITHIN = "https://www.fao.org/4/x0490e/x0490e0b.htm"

client = TestClient(app)


def bundle_json(**overrides):
    data = {
        "analysis_id": "test-blind-spots",
        "farm": {"location_id": "pamplemousses-04"},
        "selected_scenario": "ssp370",
        "selected_year": 2050,
        "climate": {"scenarios": load_fixture(SCENARIOS), "history": load_fixture(HISTORY)},
        "agriculture": {"rotation": load_fixture(ROTATION),
                        "suitability": [load_fixture(SUIT_COWPEA)]},
    }
    data.update(overrides)
    return data


def complete_bundle_json():
    """Every warning resolved. Suitability/water/soil values are TEST-ONLY."""
    return bundle_json(
        farm={"location_id": "pamplemousses-04", "soil_ph": 6.2,
              "irrigation_budget_m3": 12000},
        agriculture={
            "rotation": load_fixture(ROTATION),
            "suitability": [{"crop_id": c, "status": "within_checked_ranges",
                             "checks": [], "missing": [], "source_url": WITHIN}
                            for c in ("maize", "cowpea", "cabbage")],
            "water": {"assumption_status": "test_only"},
        },
    )


def detect(**overrides):
    return {s.code: s for s in bsd.detect_blind_spots(
        AnalysisBundle.model_validate(bundle_json(**overrides)))}


# ---------------------------------------------------------------------------
# Real data
# ---------------------------------------------------------------------------

def test_real_data_blind_spots():
    spots = detect()
    # cowpea screened without inputs; maize/cabbage not screened; no farmer inputs.
    assert set(spots) == {
        bsd.SUITABILITY_INPUT_NOT_PASSED, bsd.CROP_SUITABILITY_NOT_SCREENED,
        bsd.SOIL_PH_MISSING, bsd.IRRIGATION_BUDGET_MISSING,
        bsd.WATER_DEMAND_NOT_IMPLEMENTED, bsd.CLIMATE_RESOLUTION,
        bsd.M5_NOT_IMPLEMENTED,
    }
    # Without inputs M2 never consults its catalog, so no catalog gap is claimed.
    assert bsd.CROP_REFERENCE_INCOMPLETE not in spots


def test_real_data_module_status():
    report = bsd.build_report(AnalysisBundle.model_validate(bundle_json()))
    assert report.module_status == {
        "M1": "ok", "M2": "partial", "M3": "unavailable", "M5": "not_implemented"}


# ---------------------------------------------------------------------------
# Farmer inputs
# ---------------------------------------------------------------------------

def test_missing_soil_ph():
    spot = detect()[bsd.SOIL_PH_MISSING]
    assert (spot.category, spot.severity) == ("soil", "warning")
    assert "soil pH" in spot.farmer_action and "soil test" in spot.farmer_action
    assert spot.affects == ["maize", "cowpea", "cabbage"]
    assert bsd.SOIL_PH_MISSING not in detect(
        farm={"location_id": "pamplemousses-04", "soil_ph": 6.2})


def test_missing_irrigation_budget():
    spot = detect()[bsd.IRRIGATION_BUDGET_MISSING]
    assert (spot.category, spot.severity) == ("water", "warning")
    assert spot.farmer_action
    assert bsd.IRRIGATION_BUDGET_MISSING not in detect(
        farm={"location_id": "pamplemousses-04", "irrigation_budget_m3": 0})


# ---------------------------------------------------------------------------
# M2
# ---------------------------------------------------------------------------

def test_water_demand_not_implemented(monkeypatch):
    spot = detect()[bsd.WATER_DEMAND_NOT_IMPLEMENTED]
    assert (spot.category, spot.severity) == ("water", "warning")
    assert spot.team_action.startswith("M2:")
    assert bsd.M2_WATER_DATA_MISSING not in detect()

    monkeypatch.setattr(agriculture_provider, "water_demand_implemented", lambda: True)
    assert bsd.WATER_DEMAND_NOT_IMPLEMENTED not in detect()


def test_m2_water_service_exists_but_no_water_data(monkeypatch):
    monkeypatch.setattr(agriculture_provider, "water_demand_implemented", lambda: True)
    spot = detect()[bsd.M2_WATER_DATA_MISSING]
    assert (spot.category, spot.severity, spot.source_module) == ("water", "warning", "M2")
    assert spot.team_action.startswith("M4:")
    assert spot.affects == ["maize", "cowpea", "cabbage"]

    with_water = detect(agriculture={"rotation": load_fixture(ROTATION),
                                     "water": {"assumption_status": "test_only"}})
    assert bsd.M2_WATER_DATA_MISSING not in with_water


def test_m5_stress_tests_exist_but_no_resilience_data(monkeypatch):
    assert bsd.M5_RESILIENCE_DATA_MISSING not in detect()  # M5 not implemented today

    monkeypatch.setattr(resilience_provider, "resilience_implemented", lambda: True)
    spot = detect()[bsd.M5_RESILIENCE_DATA_MISSING]
    assert (spot.severity, spot.source_module) == ("warning", "M5")
    assert spot.team_action.startswith("M4:")
    assert bsd.M5_NOT_IMPLEMENTED not in detect()

    with_resilience = detect(resilience={"scenario": "ssp370", "year": 2050})
    assert bsd.M5_RESILIENCE_DATA_MISSING not in with_resilience


def test_new_data_missing_rules_block_supported(monkeypatch):
    monkeypatch.setattr(agriculture_provider, "water_demand_implemented", lambda: True)
    monkeypatch.setattr(resilience_provider, "resilience_implemented", lambda: True)
    data = complete_bundle_json()
    del data["agriculture"]["water"]
    passport = build_passport(AnalysisBundle.model_validate(data))
    codes = {s.code for s in passport.blind_spots}
    assert {bsd.M2_WATER_DATA_MISSING, bsd.M5_RESILIENCE_DATA_MISSING} <= codes
    assert passport.recommendation_status == "requires_further_validation"


# ---------------------------------------------------------------------------
# M2 suitability: `missing` split by meaning
# ---------------------------------------------------------------------------

def suit_only(*results, **farm):
    return detect(agriculture={"rotation": load_fixture(ROTATION),
                               "suitability": list(results)},
                  farm={"location_id": "pamplemousses-04", **farm})


def test_reference_ranges_absent_from_catalog_are_m2_gaps():
    # Real M2 output for cowpea called WITH temperature and pH.
    suit = load_fixture("m2_suitability__cowpea__temp25-ph6.5.json")
    spots = suit_only(suit, soil_ph=6.5)
    gap = spots[bsd.CROP_REFERENCE_INCOMPLETE]
    assert (gap.category, gap.severity, gap.source_module) == ("crop_reference", "warning", "M2")
    assert gap.affects == ["cowpea"]
    assert gap.team_action.startswith("M2:")
    assert [(c.value, c.field_path) for c in gap.citations] == [
        ("temperature_c_reference_range", "agriculture.suitability[0].missing[0]"),
        ("soil_ph_reference_range", "agriculture.suitability[0].missing[1]"),
    ]
    assert bsd.SUITABILITY_INPUT_NOT_PASSED not in spots


def test_missing_temperature_input_is_m4_wiring_not_m2():
    # Real M2 output for cowpea called WITHOUT inputs; farmer gave no pH.
    spots = suit_only(load_fixture(SUIT_COWPEA))
    spot = spots[bsd.SUITABILITY_INPUT_NOT_PASSED]
    assert (spot.severity, spot.source_module) == ("warning", "M4")
    assert spot.team_action.startswith("M4:") and "temperature" in spot.team_action
    assert [(c.value, c.field_path) for c in spot.citations] == [
        ("temperature_c", "agriculture.suitability[0].missing[0]")]
    assert bsd.SOIL_PH_MISSING in spots           # soil_ph handled as farmer input
    assert bsd.CROP_REFERENCE_INCOMPLETE not in spots


def test_soil_ph_known_to_farmer_but_not_passed_to_m2_is_m4_wiring():
    spots = suit_only(load_fixture(SUIT_COWPEA), soil_ph=6.5)
    assert bsd.SOIL_PH_MISSING not in spots
    cited = [c.value for c in spots[bsd.SUITABILITY_INPUT_NOT_PASSED].citations]
    assert cited == ["temperature_c", "soil_ph"]


def test_mixed_missing_from_live_m2_call_is_split():
    # Live M2 call with temperature only -> one catalog gap + one missing input.
    suit = agriculture_provider.check_suitability("cowpea", temperature_c=25.0)
    assert suit.data.missing == ["temperature_c_reference_range", "soil_ph"]
    spots = suit_only(suit.data.model_dump(mode="json"))
    assert [c.value for c in spots[bsd.CROP_REFERENCE_INCOMPLETE].citations] == [
        "temperature_c_reference_range"]
    assert bsd.SOIL_PH_MISSING in spots
    assert bsd.SUITABILITY_INPUT_NOT_PASSED not in spots


def test_unscreened_crops_are_m4_wiring():
    spot = suit_only(load_fixture(SUIT_COWPEA))[bsd.CROP_SUITABILITY_NOT_SCREENED]
    assert (spot.category, spot.severity, spot.source_module) == (
        "crop_reference", "warning", "M4")
    assert spot.affects == ["maize", "cabbage"]
    assert spot.team_action.startswith("M4:")


def test_rotation_unavailable_is_critical():
    spot = detect(agriculture={},
                  farm={"location_id": "pamplemousses-04",
                        "current_rotation": ["maize", "cowpea"]})[bsd.ROTATION_UNAVAILABLE]
    assert (spot.category, spot.severity) == ("module", "critical")
    assert spot.affects == ["maize", "cowpea"]


# ---------------------------------------------------------------------------
# M1
# ---------------------------------------------------------------------------

def test_projections_unavailable_is_critical_and_consistent_with_passport():
    bundle = AnalysisBundle.model_validate(bundle_json(climate={}))
    spots = {s.code: s for s in bsd.detect_blind_spots(bundle)}
    spot = spots[bsd.CLIMATE_PROJECTIONS_UNAVAILABLE]
    assert (spot.category, spot.severity) == ("module", "critical")
    assert build_passport(bundle).recommendation_status == "insufficient_evidence"


def test_failed_model_is_named_via_affects_and_citations():
    # Real fixture, one model status changed.
    scen = copy.deepcopy(load_fixture(SCENARIOS))
    scen["modelResults"][2]["status"] = "failed"
    spot = detect(climate={"scenarios": scen,
                           "history": load_fixture(HISTORY)})[bsd.CLIMATE_PROJECTIONS_PARTIAL]
    model_id = scen["modelResults"][2]["id"]
    assert (spot.category, spot.severity) == ("climate", "warning")
    assert spot.affects == [f"model:{model_id}"]
    cited = {c.field_path: c.value for c in spot.citations}
    assert cited["climate.scenarios.modelResults[2].id"] == model_id
    assert cited["climate.scenarios.modelResults[2].status"] == "failed"
    assert model_id not in spot.message


def test_missing_data_flag_alone_triggers_partial():
    scen = copy.deepcopy(load_fixture(SCENARIOS))
    scen["provenance"]["missingData"] = True
    spot = detect(climate={"scenarios": scen})[bsd.CLIMATE_PROJECTIONS_PARTIAL]
    assert spot.affects == []
    assert spot.citations[0].value is True


def test_complete_projections_have_no_partial_blind_spot():
    assert bsd.CLIMATE_PROJECTIONS_PARTIAL not in detect()


def test_history_unavailable_is_warning():
    spot = detect(climate={"scenarios": load_fixture(SCENARIOS)})[bsd.CLIMATE_HISTORY_UNAVAILABLE]
    assert (spot.category, spot.severity) == ("climate", "warning")


def test_history_missing_data_flag():
    hist = copy.deepcopy(load_fixture(HISTORY))
    hist["provenance"][1]["missingData"] = True
    spot = detect(climate={"scenarios": load_fixture(SCENARIOS),
                           "history": hist})[bsd.CLIMATE_HISTORY_PARTIAL]
    assert spot.severity == "warning"
    assert spot.affects == ["variable:T2M"]


def test_resolution_cites_m1_values_verbatim_without_own_threshold():
    spot = detect()[bsd.CLIMATE_RESOLUTION]
    assert (spot.category, spot.severity) == ("resolution", "info")
    cited = {c.field_path: c.value for c in spot.citations}
    scen, hist = load_fixture(SCENARIOS), load_fixture(HISTORY)
    assert cited["climate.scenarios.provenance.gridResolution"] == scen["provenance"]["gridResolution"]
    assert cited["climate.scenarios.provenance.caveat"] == scen["provenance"]["caveat"]
    assert cited["climate.history.provenance[0].gridResolution"] == hist["provenance"][0]["gridResolution"]

    # Whatever M1 reports is cited as-is; M4 applies no "coarse" threshold.
    changed = copy.deepcopy(scen)
    changed["provenance"]["gridResolution"] = "a much finer grid"
    spot = detect(climate={"scenarios": changed})[bsd.CLIMATE_RESOLUTION]
    assert spot.severity == "info"
    assert spot.citations[0].value == "a much finer grid"


def test_no_resolution_blind_spot_without_any_climate_data():
    assert bsd.CLIMATE_RESOLUTION not in detect(climate={})


def test_registry_unreadable_rule_kept(monkeypatch):
    monkeypatch.setattr(climate_provider, "registered_scenarios", lambda: None)
    spot = detect()[bsd.REGISTRY_UNREADABLE]
    assert (spot.category, spot.severity) == ("module", "warning")
    assert spot.affects == ["scenario:ssp370"]


# ---------------------------------------------------------------------------
# M3 / M5
# ---------------------------------------------------------------------------

def test_m3_m5_not_implemented_are_info(monkeypatch):
    monkeypatch.setattr(farm_provider, "farm_profile_implemented", lambda: False)
    spots = detect()
    for code, module in ((bsd.M3_NOT_IMPLEMENTED, "M3"), (bsd.M5_NOT_IMPLEMENTED, "M5")):
        assert (spots[code].category, spots[code].severity) == ("module", "info")
        assert spots[code].team_action.startswith(f"{module}:")

    monkeypatch.setattr(farm_provider, "farm_profile_implemented", lambda: True)
    monkeypatch.setattr(resilience_provider, "resilience_implemented", lambda: True)
    spots = detect()
    assert bsd.M3_NOT_IMPLEMENTED not in spots and bsd.M5_NOT_IMPLEMENTED not in spots


# ---------------------------------------------------------------------------
# Guarantees
# ---------------------------------------------------------------------------

def test_detection_never_modifies_bundle_or_fills_defaults():
    bundle = AnalysisBundle.model_validate(bundle_json())
    before = bundle.model_dump(by_alias=True, mode="json")
    bsd.detect_blind_spots(bundle)
    bsd.build_report(bundle)
    build_passport(bundle)
    assert bundle.model_dump(by_alias=True, mode="json") == before
    assert bundle.farm.soil_ph is None
    assert bundle.farm.irrigation_budget_m3 is None
    assert bundle.agriculture.water is None


def test_templates_follow_the_claim_rule():
    for code, template in bsd.TEMPLATES.items():
        for key in ("message", "farmer_action", "team_action"):
            text = template.get(key)
            assert text is None or not claim_has_disallowed_digits(text), (code, key)


def test_blind_spot_text_with_measured_number_is_rejected():
    with pytest.raises(ValidationError, match="must not contain numbers"):
        BlindSpot(code="X", category="climate", severity="info", source_module="M1",
                  message="Grid resolution is 0.25 degrees")


def test_upstream_citation_without_field_path_is_rejected():
    with pytest.raises(ValidationError, match="requires field_path"):
        BlindSpot(code="X", category="climate", severity="info", source_module="M1",
                  message="Cited", citations=[{"label": "grid", "value": "0.25",
                                               "source_module": "M1"}])


def test_tampered_citation_fails_traceability():
    bundle = AnalysisBundle.model_validate(bundle_json())
    spots = bsd.detect_blind_spots(bundle)
    tampered = [s.model_copy(deep=True) for s in spots]
    res = next(s for s in tampered if s.code == bsd.CLIMATE_RESOLUTION)
    res.citations[0].value = "1 km"
    with pytest.raises(TraceabilityError):
        verify_citations(tampered, bundle.model_dump(by_alias=True, mode="json"))


def test_deduplicated_by_code_and_sorted_by_severity(monkeypatch):
    monkeypatch.setattr(bsd, "RULES", bsd.RULES + (bsd._farm_rules, bsd._rotation_rule))
    bundle = AnalysisBundle.model_validate(bundle_json(agriculture={}))
    spots = bsd.detect_blind_spots(bundle)
    codes = [s.code for s in spots]
    assert len(codes) == len(set(codes))
    order = [bsd.SEVERITY_ORDER[s.severity] for s in spots]
    assert order == sorted(order)
    assert spots[0].severity == "critical"


@pytest.mark.parametrize("overrides", [
    {},
    {"climate": {}, "agriculture": {}},
    {"farm": {"location_id": "flacq-02", "source": "M3"}},
])
def test_module_status_always_has_four_keys(overrides):
    report = bsd.build_report(AnalysisBundle.model_validate(bundle_json(**overrides)))
    assert list(report.module_status) == ["M1", "M2", "M3", "M5"]


def test_module_status_unavailable_when_modules_missing():
    report = bsd.build_report(AnalysisBundle.model_validate(
        bundle_json(climate={}, agriculture={})))
    assert report.module_status["M1"] == "unavailable"
    assert report.module_status["M2"] == "unavailable"


# ---------------------------------------------------------------------------
# recommendation_status: supported only with no critical / warning blind spots
# ---------------------------------------------------------------------------

def test_supported_with_only_info_blind_spots():
    passport = build_passport(AnalysisBundle.model_validate(complete_bundle_json()))
    assert {s.severity for s in passport.blind_spots} == {"info"}
    assert passport.recommendation_status == "supported"


@pytest.mark.parametrize("remove", ["soil_ph", "irrigation_budget_m3", "water"])
def test_any_warning_blocks_supported(remove):
    data = complete_bundle_json()
    if remove == "water":
        del data["agriculture"]["water"]
    else:
        del data["farm"][remove]
    passport = build_passport(AnalysisBundle.model_validate(data))
    assert any(s.severity == "warning" for s in passport.blind_spots)
    assert passport.recommendation_status == "requires_further_validation"


def test_critical_blocks_supported():
    data = complete_bundle_json()
    data["climate"] = {}
    passport = build_passport(AnalysisBundle.model_validate(data))
    assert passport.recommendation_status == "insufficient_evidence"


# ---------------------------------------------------------------------------
# Endpoint and consistency with /evidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("data", [
    bundle_json(),
    bundle_json(climate={}),
    bundle_json(agriculture={}),
    complete_bundle_json(),
])
def test_evidence_and_blind_spots_endpoints_agree(data):
    evidence = client.post("/api/intelligence/evidence", json=data)
    report = client.post("/api/intelligence/blind-spots", json=data)
    assert evidence.status_code == report.status_code == 200
    assert evidence.json()["blind_spots"] == report.json()["blind_spots"]


def test_blind_spots_endpoint_returns_report():
    response = client.post("/api/intelligence/blind-spots", json=bundle_json())
    assert response.status_code == 200, response.text
    report = BlindSpotReport.model_validate(response.json())
    assert report.analysis_id == "test-blind-spots"


def test_blind_spots_endpoint_rejects_unregistered_year():
    assert client.post("/api/intelligence/blind-spots",
                       json=bundle_json(selected_year=2045)).status_code == 422


def test_blind_spots_endpoint_is_in_swagger():
    assert "/api/intelligence/blind-spots" in client.get("/openapi.json").json()["paths"]


def test_saved_blind_spots_example_matches_current_output():
    request = load_fixture("example_evidence_request.json")
    saved = load_fixture("example_blind_spots_response.json")
    fresh = client.post("/api/intelligence/blind-spots", json=request).json()
    assert fresh == saved, "Regenerate: python -m intelligenceM4.fixtures.build_fixtures --example-only"
