"""Phase 2 — Evidence Passport and POST /api/intelligence/evidence.

All upstream data comes from REAL M1/M2 fixtures. Where a test needs a state
the real data does not have (e.g. a failed model), it copies a real fixture
and changes one flag — clearly marked below.
"""

import copy

import pytest
from fastapi.testclient import TestClient

from app import app
from intelligenceM4 import blind_spot_detector
from intelligenceM4.evidence_passport import (
    CLAIMS,
    TraceabilityError,
    build_passport,
    resolve_field_path,
    verify_traceability,
)
from intelligenceM4.fixtures import load_fixture
from intelligenceM4.providers import climate_provider
from intelligenceM4.schemas import (
    UPSTREAM_MODULES,
    AnalysisBundle,
    EvidencePassport,
    claim_has_disallowed_digits,
)

SCENARIOS = "m1_scenarios__pamplemousses-04.json"
HISTORY = "m1_history__pamplemousses-04.json"
ROTATION = "m2_rotation__maize-cowpea-cabbage.json"
GENERATE = "m2_generate__maize-maize-maize__max3.json"
SUIT_COWPEA = "m2_suitability__cowpea__no-inputs.json"


def bundle_json(**overrides):
    data = {
        "analysis_id": "test-evidence",
        "farm": {"location_id": "pamplemousses-04"},
        "selected_scenario": "ssp370",
        "selected_year": 2050,
        "climate": {"scenarios": load_fixture(SCENARIOS), "history": load_fixture(HISTORY)},
        "agriculture": {
            "rotation": load_fixture(ROTATION),
            "alternatives": load_fixture(GENERATE),
            "suitability": [load_fixture(SUIT_COWPEA)],
        },
    }
    data.update(overrides)
    return data


def make_passport(**overrides):
    bundle = AnalysisBundle.model_validate(bundle_json(**overrides))
    return bundle, build_passport(bundle)


def by_id(passport):
    return {e.id: e for e in passport.evidence}


# ---------------------------------------------------------------------------
# Traceability
# ---------------------------------------------------------------------------

def test_every_upstream_value_resolves_to_the_bundle_field_it_cites():
    bundle, passport = make_passport()
    data = bundle.model_dump(by_alias=True, mode="json")
    checked = 0
    for record in passport.evidence:
        if record.provenance.source_module in UPSTREAM_MODULES and record.value is not None:
            assert resolve_field_path(data, record.provenance.field_path) == record.value
            checked += 1
    assert checked >= 15


def test_traceability_guard_rejects_a_value_not_in_the_bundle():
    bundle, passport = make_passport()
    tampered = passport.model_copy(deep=True)
    rain = next(e for e in tampered.evidence if e.id == "ev-proj-rain-mean")
    rain.value = rain.value + 1
    with pytest.raises(TraceabilityError):
        verify_traceability(tampered, bundle.model_dump(by_alias=True, mode="json"))


def test_no_claim_contains_a_measured_number():
    _, passport = make_passport()
    for record in passport.evidence:
        assert not claim_has_disallowed_digits(record.claim), record.claim
    for template in CLAIMS.values():
        assert not claim_has_disallowed_digits(template.format(context=""))


# ---------------------------------------------------------------------------
# M2 rotation evidence (the plan's cowpea example)
# ---------------------------------------------------------------------------

def test_cowpea_is_cited_as_nitrogen_fixing_with_qualifications():
    _, passport = make_passport()
    nfix = by_id(passport)["ev-nfix-cowpea"]
    assert nfix.value == "cowpea"
    assert nfix.status == "supported"
    assert nfix.provenance.source_module == "M2"
    assert nfix.provenance.field_path == "agriculture.rotation.nitrogen_fixing_crops[0]"
    assert nfix.provenance.source_url.startswith("https://www.fao.org/")
    assert any("does not quantify" in q for q in nfix.qualifications)
    assert any("not establish that the crop is suitable" in q for q in nfix.qualifications)


def test_uncalibrated_soil_score_is_not_invented():
    _, passport = make_passport()
    soil = by_id(passport)["ev-soil-score"]
    assert soil.value is None
    assert soil.status == "not_evaluated"
    assert "not_calibrated" in soil.qualifications[0]


def test_repeated_family_rotation_is_reported():
    _, passport = make_passport(agriculture={
        "rotation": load_fixture("m2_rotation__maize-maize-maize.json")})
    repeat = by_id(passport)["ev-family-repeat"]
    assert repeat.value is True
    assert repeat.claim == CLAIMS["family_repeat"]
    assert "ev-nfix-none" in by_id(passport)


def test_alternatives_are_reported_as_not_evaluated():
    _, passport = make_passport()
    records = by_id(passport)
    assert records["ev-alt-feasibility"].value == "not_evaluated"
    assert records["ev-alt-feasibility"].status == "not_evaluated"
    assert records["ev-alt-ranking"].value == "not_calibrated"


# ---------------------------------------------------------------------------
# M2 suitability
# ---------------------------------------------------------------------------

def test_every_rotation_crop_has_a_suitability_record():
    _, passport = make_passport()
    records = by_id(passport)
    cowpea = records["ev-suit-cowpea"]
    assert cowpea.value == "insufficient_data"
    assert cowpea.status == "not_evaluated"          # M2 ran no checks
    assert {"Missing for screening: temperature_c",
            "Missing for screening: soil_ph"} <= set(cowpea.qualifications)
    for crop in ("maize", "cabbage"):                # M2 not asked -> not screened
        assert records[f"ev-suit-{crop}"].status == "not_evaluated"
        assert records[f"ev-suit-{crop}"].value is None


# ---------------------------------------------------------------------------
# M1 climate evidence
# ---------------------------------------------------------------------------

def test_selected_projection_values_are_copied_from_m1():
    _, passport = make_passport()
    records = by_id(passport)
    ensemble = next(e for e in load_fixture(SCENARIOS)["ensemble"] if e["id"] == "ssp370")
    point = next(v for v in ensemble["values"] if v["year"] == 2050)

    assert records["ev-proj-rain-mean"].value == point["rainfallMm"]["mean"]
    assert records["ev-proj-rain-mean"].unit == "mm/year"
    assert records["ev-proj-temp-spread"].value == point["temperatureC"]["spread"]
    assert records["ev-proj-models"].value == point["rainfallMm"]["count"]
    assert records["ev-proj"].provenance.dataset == "NASA NEX-GDDP-CMIP6"
    assert records["ev-proj"].provenance.grid_resolution.startswith("0.25")
    # Registry identifiers make the claim readable; numbers stay in value.
    assert records["ev-proj-rain-mean"].claim.endswith("for 2050 under SSP3-7.0")


def test_spread_is_copied_from_m1_not_computed_by_m4():
    # Real fixture with M1's spread deliberately set inconsistent with max-min.
    # If M4 ever computed max-min itself, the passport would show 1.75, not 9.99.
    scen = copy.deepcopy(load_fixture(SCENARIOS))
    ens = next(e for e in scen["ensemble"] if e["id"] == "ssp370")
    point = next(v for v in ens["values"] if v["year"] == 2050)
    point["temperatureC"]["spread"] = 9.99
    point["rainfallMm"]["spread"] = 999.9

    _, passport = make_passport(climate={"scenarios": scen})
    records = by_id(passport)
    for rec_id, alias, expected in (("ev-proj-temp-spread", "temperatureC", 9.99),
                                    ("ev-proj-rain-spread", "rainfallMm", 999.9)):
        record = records[rec_id]
        assert record.value == expected
        assert record.provenance.source_module == "M1"
        assert record.provenance.field_path.endswith(f".{alias}.spread")


def test_m1_caveats_are_copied_verbatim_into_limitations():
    _, passport = make_passport()
    texts = [l.text for l in passport.limitations]
    for caveat in load_fixture(SCENARIOS)["caveats"]:
        assert caveat in texts
    assert len(texts) == len(set(texts))


def test_incomplete_climate_is_not_presented_as_complete():
    # Real fixture, one flag changed to simulate a failed model.
    scen = copy.deepcopy(load_fixture(SCENARIOS))
    scen["modelResults"][0]["status"] = "failed"
    scen["provenance"]["missingData"] = True
    _, passport = make_passport(climate={"scenarios": scen})
    records = by_id(passport)
    assert records["ev-proj"].status == "partial"
    assert records["ev-proj-rain-mean"].status == "partial"
    assert passport.recommendation_status != "supported"


def test_missing_projections_give_insufficient_evidence_and_no_numbers():
    _, passport = make_passport(climate={})
    records = by_id(passport)
    assert records["ev-proj"].status == "unavailable"
    assert records["ev-hist"].status == "unavailable"
    assert not any(k.startswith("ev-proj-rain") for k in records)
    assert passport.recommendation_status == "insufficient_evidence"


def test_selected_year_missing_from_ensemble_is_unavailable():
    # Real fixture with the ssp370 2050 point removed.
    scen = copy.deepcopy(load_fixture(SCENARIOS))
    for e in scen["ensemble"]:
        e["values"] = [v for v in e["values"] if v["year"] != 2050]
    _, passport = make_passport(climate={"scenarios": scen})
    assert by_id(passport)["ev-proj-selection"].status == "unavailable"


def test_history_evidence_is_cited():
    _, passport = make_passport()
    records = by_id(passport)
    hist = load_fixture(HISTORY)
    assert records["ev-hist"].value == "NASA POWER"
    assert records["ev-hist-completeness"].value == hist["metrics"]["dataCompleteness"]
    assert records["ev-hist-rain-trend"].value == hist["metrics"]["annualRainfallTrend"]["direction"]


# ---------------------------------------------------------------------------
# Missing modules / recommendation status
# ---------------------------------------------------------------------------

def test_missing_water_and_resilience_are_unavailable_not_invented():
    _, passport = make_passport()
    records = by_id(passport)
    assert records["ev-water"].status == "unavailable" and records["ev-water"].value is None
    assert records["ev-resilience"].status == "unavailable"
    assert records["ev-resilience"].value is None


def test_m5_outputs_are_preserved_and_traceable_through_the_evidence_api():
    climate_twin = {
        "scenario": "ssp245",
        "period": {"start_year": 2041, "end_year": 2060},
        "projected_target": {
            "provenance": {
                "dataset": "NASA NEX-GDDP-CMIP6",
                "source_urls": [
                    "https://www.nccs.nasa.gov/data-collections/nex-gddp-cmip6/"
                ],
                "model": "multi-model ensemble",
                "temperature_unit": "degC",
                "precipitation_unit": "mm/month",
            },
        },
        "limitations": ["Regional grid values are not field measurements."],
    }
    stress_test = {
        "baseline_water_budget_m3": 120,
        "irrigation_reduction_fraction": 0.2,
        "scenarios": [
            {"scenario_id": "projected_future", "rotations": [
                {"id": "current", "feasible": None, "score": None, "rank": None,
                 "water_requirement_m3": None, "failed_constraints": []},
            ]},
        ],
        "limitations": ["M2 does not calculate irrigation feasibility."],
    }
    request_bundle = bundle_json(resilience={
        "scenario": "ssp245",
        "climate_twin": climate_twin,
        "stress_tests": [stress_test],
    })

    response = client.post("/api/intelligence/evidence", json=request_bundle)
    assert response.status_code == 200, response.text
    body = response.json()
    records = {record["id"]: record for record in body["evidence"]}

    twin = records["ev-resilience-climate-twin"]
    assert twin["value"] == climate_twin
    assert twin["provenance"]["source_module"] == "M5"
    assert twin["provenance"]["field_path"] == "resilience.climate_twin"
    stress = records["ev-resilience-stress-tests"]
    assert stress["value"] == [stress_test]
    assert stress["provenance"]["field_path"] == "resilience.stress_tests"
    assert stress["qualifications"]
    assert "Regional grid values are not field measurements." in {
        item["text"] for item in body["limitations"]
    }
    assert "M2 does not calculate irrigation feasibility." in {
        item["text"] for item in body["limitations"]
    }


def test_missing_rotation_gives_insufficient_evidence():
    _, passport = make_passport(agriculture={})
    assert passport.recommendation_status == "insufficient_evidence"
    assert passport.rotation == []


def test_real_data_requires_further_validation():
    _, passport = make_passport()
    assert passport.recommendation_status == "requires_further_validation"


def test_supported_only_when_every_check_passes():
    # Test-only M2-shaped suitability and water results: the real catalog has
    # no ranges and M2 has no water service yet. Farmer inputs supplied.
    suit = [
        {"crop_id": c, "status": "within_checked_ranges", "checks": [], "missing": [],
         "source_url": "https://www.fao.org/4/x0490e/x0490e0b.htm"}
        for c in ("maize", "cowpea", "cabbage")
    ]
    _, passport = make_passport(
        farm={"location_id": "pamplemousses-04", "soil_ph": 6.2,
              "irrigation_budget_m3": 12000},
        agriculture={"rotation": load_fixture(ROTATION), "suitability": suit,
                     "water": {"assumption_status": "test_only"}},
    )
    assert {s.severity for s in passport.blind_spots} <= {"info"}
    assert passport.recommendation_status == "supported"


def test_farmer_soil_ph_is_cited_when_supplied():
    _, passport = make_passport(farm={"location_id": "pamplemousses-04", "soil_ph": 6.2})
    soil = by_id(passport)["ev-farm-soil-ph"]
    assert soil.value == 6.2 and soil.provenance.source_module == "farmer"


# ---------------------------------------------------------------------------
# Change 2 — unreadable M1 registry produces a blind spot
# ---------------------------------------------------------------------------

def test_unreadable_registry_passes_through_and_emits_blind_spot(monkeypatch):
    monkeypatch.setattr(climate_provider, "registered_scenarios", lambda: None)
    monkeypatch.setattr(climate_provider, "registered_projection_years", lambda: None)
    monkeypatch.setattr(climate_provider, "registered_location_ids", lambda: None)

    bundle, passport = make_passport(selected_scenario="ssp126", selected_year=2070)
    assert (bundle.selected_scenario, bundle.selected_year) == ("ssp126", 2070)

    spot = next(s for s in passport.blind_spots
                if s.code == blind_spot_detector.REGISTRY_UNREADABLE)
    assert spot.category == "module"
    assert spot.severity == "warning"
    assert "could not be validated against M1" in spot.message
    assert {"scenario:ssp126", "year:2070"} <= set(spot.affects)
    # Unvalidated selection is simply not found; no climate value is cited for it.
    assert by_id(passport)["ev-proj-selection"].status == "unavailable"


def test_readable_registry_emits_no_registry_blind_spot():
    _, passport = make_passport()
    assert not any(s.code == blind_spot_detector.REGISTRY_UNREADABLE
                   for s in passport.blind_spots)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

client = TestClient(app)


def test_evidence_endpoint_returns_passport_from_real_fixtures():
    response = client.post("/api/intelligence/evidence", json=bundle_json())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["analysis_id"] == "test-evidence"
    assert body["recommendation_status"] == "requires_further_validation"
    assert any(e["id"] == "ev-nfix-cowpea" for e in body["evidence"])


def test_every_upstream_value_in_http_response_cites_a_resolvable_field():
    request = bundle_json()
    body = client.post("/api/intelligence/evidence", json=request).json()
    for record in body["evidence"]:
        prov = record["provenance"]
        if prov["source_module"] in UPSTREAM_MODULES and record["value"] is not None:
            assert prov["field_path"], f"{record['id']} has no field_path"
            assert resolve_field_path(request, prov["field_path"]) == record["value"]


def test_saved_example_matches_current_endpoint_output():
    """The example M3 builds against must stay in sync with the code."""
    request = load_fixture("example_evidence_request.json")
    saved = load_fixture("example_evidence_response.json")
    EvidencePassport.model_validate(saved)

    fresh = client.post("/api/intelligence/evidence", json=request).json()
    for body in (saved, fresh):
        body.pop("generated_at")
    assert fresh == saved, "Regenerate: python -m intelligenceM4.fixtures.build_fixtures"

    for record in saved["evidence"]:
        prov = record["provenance"]
        if prov["source_module"] in UPSTREAM_MODULES and record["value"] is not None:
            assert resolve_field_path(request, prov["field_path"]) == record["value"]


def test_evidence_endpoint_rejects_unregistered_scenario():
    response = client.post("/api/intelligence/evidence",
                           json=bundle_json(selected_scenario="ssp999"))
    assert response.status_code == 422


def test_evidence_endpoint_is_in_swagger():
    assert "/api/intelligence/evidence" in client.get("/openapi.json").json()["paths"]
