"""Phase 5 — Orchestrator and POST /api/intelligence/analyze (end to end).

No network: the `warm_m1` fixture
  * treats M1's existing cached NEX-GDDP-CMIP6 rows as fresh (M1's TTL setting is
    raised in-process; no M1 code changes, and the tracked cache file is never
    rewritten),
  * blocks every outgoing async HTTP request,
  * serves M1 history from M1's recorded real output.
M2 runs for real.
"""

import asyncio
import copy

import pytest
from fastapi.testclient import TestClient

from app import app
from intelligenceM4.fixtures import load_fixture
from intelligenceM4.schemas import AnalyzeResponse
from intelligenceM4.traceability import resolve_field_path

client = TestClient(app)
HISTORY = "m1_history__pamplemousses-04.json"
ROTATION = ["maize", "cowpea", "cabbage"]
UPSTREAM = {"M1", "M2", "M3", "M5"}


@pytest.fixture
def warm_m1(monkeypatch):
    import httpx

    import climateM1.services.cache as cache
    import climateM1.services.history as history

    monkeypatch.setattr(cache, "CACHE_TTL_SECONDS", 10**12)

    async def no_network(self, *args, **kwargs):
        raise httpx.ConnectError("network disabled in tests")

    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)

    async def recorded_history(location, start, end):
        assert location.id == "pamplemousses-04"
        return load_fixture(HISTORY)

    monkeypatch.setattr(history, "fetch_history", recorded_history)


def analyze(**overrides):
    body = {
        "farm": {"location_id": "pamplemousses-04", "current_rotation": ROTATION},
        "scenario": "ssp370",
        "year": 2050,
        "max_alternatives": 3,
    }
    body.update(overrides)
    response = client.post("/api/intelligence/analyze", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def codes(body):
    return [s["code"] for s in body["blind_spot_report"]["blind_spots"]]


def evidence(body):
    return {e["id"]: e for e in body["passport"]["evidence"]}


def m1_down(monkeypatch):
    import climateM1.services.history as history
    import climateM1.services.projections as projections

    async def down(*args, **kwargs):
        raise RuntimeError("M1 is down")

    monkeypatch.setattr(projections, "fetch_scenarios", down)
    monkeypatch.setattr(history, "fetch_history", down)


def m2_down(monkeypatch):
    import agricultureM2.rotation_engine as engine
    import agricultureM2.rotation_generator as generator
    import agricultureM2.suitability as suitability

    def down(*args, **kwargs):
        raise FileNotFoundError("Verified crop catalog not found.")

    monkeypatch.setattr(engine, "evaluate_rotation", down)
    monkeypatch.setattr(generator, "generate_rotation_candidates", down)
    monkeypatch.setattr(suitability, "check_crop_suitability", down)


def assert_no_upstream_numbers_without_source(body):
    """Every numeric upstream value must resolve to the same value in the bundle."""
    for record in body["passport"]["evidence"]:
        prov = record["provenance"]
        if prov["source_module"] in UPSTREAM and record["value"] is not None:
            assert resolve_field_path(body["bundle"], prov["field_path"]) == record["value"]


# ---------------------------------------------------------------------------
# Real end-to-end run
# ---------------------------------------------------------------------------

def test_end_to_end_analyze(warm_m1):
    body = analyze()
    AnalyzeResponse.model_validate(body)

    assert {m: r["status"] for m, r in body["modules"].items()} == {
        "M1": "ok", "M2": "partial", "M3": "unavailable", "M5": "not_implemented"}
    assert body["blind_spot_report"]["module_status"]["M5"] == "unavailable"
    agri = body["bundle"]["agriculture"]
    assert agri["rotation"]["rotation"] == ROTATION
    assert len(agri["alternatives"]["alternative_rotations"]) == 3
    alt_crops = {c for a in agri["alternatives"]["alternative_rotations"] for c in a["rotation"]}
    assert {s["crop_id"] for s in agri["suitability"]} == set(ROTATION) | alt_crops
    assert body["passport"]["recommendation_status"] == "requires_further_validation"
    assert body["bundle"]["farm"]["soil_ph"] is None
    assert_no_upstream_numbers_without_source(body)


def test_passing_temperature_reveals_catalog_gap(warm_m1):
    body = analyze()
    spots = {s["code"]: s for s in body["blind_spot_report"]["blind_spots"]}

    # M2 received the temperature, so it no longer reports it as a missing input...
    for result in body["bundle"]["agriculture"]["suitability"]:
        assert "temperature_c" not in result["missing"]
        assert "temperature_c_reference_range" in result["missing"]
    assert "SUITABILITY_INPUT_NOT_PASSED" not in spots
    # ...and M2's empty catalog ranges now surface.
    gap = spots["CROP_REFERENCE_INCOMPLETE"]
    assert set(ROTATION) <= set(gap["affects"])
    assert "temperature_c_reference_range" in {c["value"] for c in gap["citations"]}
    # Soil pH was not supplied: still a farmer blind spot, not an M4 wiring one.
    assert "SOIL_PH_MISSING" in spots


def test_temperature_passed_equals_m1_value_at_field_path(warm_m1):
    body = analyze()
    [temperature] = body["bundle"]["agriculture"]["suitability_inputs"]
    assert temperature["factor"] == "temperature_c" and temperature["source_module"] == "M1"
    assert temperature["field_path"].endswith(".temperatureC.mean")
    assert resolve_field_path(body["bundle"], temperature["field_path"]) == temperature["value"]

    ensemble = next(e for e in body["bundle"]["climate"]["scenarios"]["ensemble"]
                    if e["id"] == "ssp370")
    point = next(v for v in ensemble["values"] if v["year"] == 2050)
    assert temperature["value"] == point["temperatureC"]["mean"]

    record = evidence(body)["ev-suit-input-temperature_c"]
    assert record["provenance"]["field_path"] == temperature["field_path"]
    assert any("not a growing-season or field measurement" in q
               for q in record["qualifications"])
    assert any("not a growing-season or field measurement" in l["text"]
               for l in body["passport"]["limitations"])


def test_farmer_soil_ph_is_passed_with_its_field_path(warm_m1):
    body = analyze(farm={"location_id": "pamplemousses-04", "current_rotation": ROTATION,
                         "soil_ph": 6.5})
    inputs = {i["factor"]: i for i in body["bundle"]["agriculture"]["suitability_inputs"]}
    assert inputs["soil_ph"] == {"factor": "soil_ph", "value": 6.5, "unit": "pH",
                                 "source_module": "farmer", "field_path": "farm.soil_ph",
                                 "note": None}
    for result in body["bundle"]["agriculture"]["suitability"]:
        assert "soil_ph_reference_range" in result["missing"]
    assert "SOIL_PH_MISSING" not in codes(body)


# ---------------------------------------------------------------------------
# Failures never fail the request, never invent values
# ---------------------------------------------------------------------------

def test_m1_down(monkeypatch, warm_m1):
    m1_down(monkeypatch)
    body = analyze()
    assert body["modules"]["M1"]["status"] == "unavailable"
    assert "M1 is down" in body["modules"]["M1"]["error"]
    assert body["bundle"]["climate"] == {"scenarios": None, "history": None}
    assert body["bundle"]["agriculture"]["suitability_inputs"] == []
    for result in body["bundle"]["agriculture"]["suitability"]:
        assert "temperature_c" in result["missing"]       # nothing was passed
    assert {"CLIMATE_PROJECTIONS_UNAVAILABLE", "CLIMATE_HISTORY_UNAVAILABLE",
            "SUITABILITY_INPUT_NOT_PASSED"} <= set(codes(body))
    assert body["passport"]["recommendation_status"] == "insufficient_evidence"
    assert not any(k.startswith("ev-proj-") for k in evidence(body))
    assert body["modules"]["M2"]["status"] == "partial"   # M2 still ran


def test_m2_down(monkeypatch, warm_m1):
    m2_down(monkeypatch)
    body = analyze()
    assert body["modules"]["M2"]["status"] == "unavailable"
    assert body["modules"]["M1"]["status"] == "ok"
    agri = body["bundle"]["agriculture"]
    assert agri["rotation"] is None and agri["alternatives"] is None
    assert agri["suitability"] == []
    assert "ROTATION_UNAVAILABLE" in codes(body)
    assert body["passport"]["recommendation_status"] == "insufficient_evidence"
    assert_no_upstream_numbers_without_source(body)


def test_m1_and_m2_down(monkeypatch, warm_m1):
    m1_down(monkeypatch)
    m2_down(monkeypatch)
    body = analyze()
    assert body["modules"]["M1"]["status"] == "unavailable"
    assert body["modules"]["M2"]["status"] == "unavailable"
    assert {"ROTATION_UNAVAILABLE", "CLIMATE_PROJECTIONS_UNAVAILABLE"} <= set(codes(body))
    assert body["blind_spot_report"]["blind_spots"][0]["severity"] == "critical"
    for record in body["passport"]["evidence"]:
        if record["provenance"]["source_module"] in UPSTREAM:
            assert record["value"] is None, record["id"]   # nothing upstream to cite


def test_history_timeout_only_affects_history(monkeypatch, warm_m1):
    import climateM1.services.history as history

    async def slow(*args, **kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(history, "fetch_history", slow)
    monkeypatch.setenv("M4_HISTORY_TIMEOUT_SECONDS", "0.2")
    body = analyze()
    calls = {c["called"]: c for c in body["modules"]["M1"]["calls"]}
    assert calls["climateM1.services.history.fetch_history"]["status"] == "unavailable"
    assert calls["climateM1.services.history.fetch_history"]["error"].startswith("TimeoutError")
    assert calls["climateM1.services.projections.fetch_scenarios"]["status"] == "ok"
    assert body["modules"]["M1"]["status"] == "partial"
    assert body["bundle"]["climate"]["history"] is None
    assert "CLIMATE_HISTORY_UNAVAILABLE" in codes(body)
    assert body["bundle"]["agriculture"]["suitability_inputs"][0]["factor"] == "temperature_c"


def test_unknown_crop_is_an_m2_failure_not_a_4xx(warm_m1):
    body = analyze(farm={"location_id": "pamplemousses-04",
                         "current_rotation": ["maize", "dragonfruit"]})
    calls = body["modules"]["M2"]["calls"]
    # Rotation evaluation and alternatives fail; suitability still works for maize.
    assert body["modules"]["M2"]["status"] == "partial"
    assert {c["called"].rsplit(".", 1)[1]: c["status"] for c in calls[:2]} == {
        "evaluate_rotation": "unavailable", "generate_rotation_candidates": "unavailable"}
    assert "Unknown crop: dragonfruit" in body["modules"]["M2"]["error"]
    assert body["bundle"]["agriculture"]["rotation"] is None
    assert [s["crop_id"] for s in body["bundle"]["agriculture"]["suitability"]] == ["maize"]
    assert "ROTATION_UNAVAILABLE" in codes(body)


@pytest.mark.parametrize("override", [
    {"farm": {"location_id": "atlantis-01", "current_rotation": ROTATION}},
    {"scenario": "ssp999"},
    {"year": 2045},
    {"max_alternatives": 0},
])
def test_invalid_input_is_422(override):
    body = {"farm": {"location_id": "pamplemousses-04", "current_rotation": ROTATION},
            **override}
    assert client.post("/api/intelligence/analyze", json=body).status_code == 422


# ---------------------------------------------------------------------------
# The bundle round-trips to the other endpoints
# ---------------------------------------------------------------------------

def test_analyze_bundle_works_with_the_other_endpoints(warm_m1):
    body = analyze()
    bundle = body["bundle"]

    answer = client.post("/api/intelligence/assistant",
                         json={"question": "Why cowpea?", "analysis": bundle}).json()
    assert answer["mode"] == "template" and answer["intent"] == "why_crop"
    assert "legume" in answer["answer"] and "ev-nfix-cowpea" in answer["cited_evidence"]

    passport = client.post("/api/intelligence/evidence", json=bundle).json()
    report = client.post("/api/intelligence/blind-spots", json=bundle).json()
    for p in (passport, body["passport"]):
        p.pop("generated_at")
    assert passport == body["passport"]
    assert report == body["blind_spot_report"]


def test_all_m4_endpoints_in_swagger():
    paths = client.get("/openapi.json").json()["paths"]
    for endpoint in ("evidence", "blind-spots", "assistant", "analyze"):
        assert f"/api/intelligence/{endpoint}" in paths


def test_saved_analyze_example_is_consistent():
    request = load_fixture("example_analyze_request.json")
    saved = load_fixture("example_analyze_response.json")
    AnalyzeResponse.model_validate(saved)
    assert saved["analysis_id"] == request["analysis_id"]
    # Its bundle reproduces its passport and blind spots through the other endpoints.
    passport = client.post("/api/intelligence/evidence", json=saved["bundle"]).json()
    expected = copy.deepcopy(saved["passport"])
    for p in (passport, expected):
        p.pop("generated_at")
    assert passport == expected
    assert client.post("/api/intelligence/blind-spots",
                       json=saved["bundle"]).json() == saved["blind_spot_report"]


@pytest.mark.parametrize("farm_id,status", [("pamplemousses-04", "ok"), ("unknown-farm", "unavailable"), (None, "unavailable")])
def test_m3_status_and_provenance(warm_m1, farm_id, status):
    farm = {"location_id":"pamplemousses-04", "current_rotation": ROTATION}
    if farm_id:
        farm["farm_id"] = farm_id
    body = analyze(farm=farm)
    assert body["modules"]["M3"]["status"] == status
    if status == "ok":
        assert body["bundle"]["farm"]["demo"] is True
        records = evidence(body)
        assert records["ev-farm-demo"]["value"] is True
        assert records["ev-farm-input-provenance"]["value"] == body["bundle"]["farm"]["input_provenance"]
    else:
        assert body["bundle"]["farm"]["source"] == "farmer"
        assert body["bundle"]["farm"]["field_area_ha"] is None
    assert_no_upstream_numbers_without_source(body)
