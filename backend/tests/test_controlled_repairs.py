import asyncio
import copy
import json
from pathlib import Path
import pytest
from agricultureM2.plan_engine import build_plans

def test_missing_inputs_never_claim_success_or_economics():
    out = build_plans(current=["maize"], seasonal=None, budget_mm=None, area_ha=None, soil_ph=None, priorities=None)
    for plan in out["plans"]:
        assert plan["feasible"] is None
        assert plan["income"]["area_ha"] is None
        assert plan["income"]["profit_rs"] is None
        assert plan["scores"]["income"] is None
    assert out["weights"]["income"] == 0

@pytest.mark.parametrize("field,value", [("source", "unverified"), ("precipitation_unit", "mm/day"), ("scenario", "ssp999"), ("source_urls", ["https://example.invalid/not-NASA"]), ("temperature_unit", "K"), ("period_start", "1900-01"), ("requested_coordinates", {"latitude":0,"longitude":0})])
def test_processed_cache_validates_like_m1(monkeypatch, field, value):
    from resilienceM5 import scenario_engine as se
    saved = json.loads(se.FARM_CLIMATE_CACHE.read_text(encoding="utf-8"))
    key = next(iter(saved))
    coords, scenario, period = key.split("|")
    lat, lon = map(float, coords.split(","))
    start, end = map(int, period.split("-"))
    saved[key]["future"]["provenance"][field] = value
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(se, "_farm_climate_cache", lambda: saved)
    monkeypatch.setattr(se, "_registered_m1", lambda *args: None)
    with pytest.raises(se.DataUnavailable, match="Invalid processed"):
        asyncio.run(se.get_farm_climate(lat, lon, scenario, start, end))

def test_m3_demo_provenance_survives_contract():
    from mappingM3.farm_profile import get_farm_profile
    from intelligenceM4.schemas import FarmContext
    raw = get_farm_profile("pamplemousses-04")
    parsed = FarmContext.model_validate(raw)
    assert parsed.demo is True
    assert parsed.input_provenance == raw["input_provenance"]
    assert parsed.input_provenance["field_area_ha"] == "illustrative_seed"


def test_boundary_seasons_excluded_and_rain_conserved():
    from agricultureM2.plan_engine import monthly_climate
    complete = [{"period": "2023-" + s, "temperatureC": 25, "rainfallMm": 300,
                 "completenessStatus": "complete", "completenessPct": 100} for s in ("DJF", "MAM", "JJA", "SON")]
    boundary = {**complete[0], "period": "2021-DJF", "rainfallMm": 50, "completenessStatus": "incomplete", "completenessPct": 65.6}
    rows = monthly_climate([boundary] + complete)
    assert rows[0]["rain_mm"] == 100
    assert sum(row["rain_mm"] for row in rows) == 1200
    assert monthly_climate([boundary] + complete[1:]) is None


def test_production_adapter_forwarding_and_rescue():
    from resilienceM5.m2_adapter import evaluate_with_plan_engine
    from resilienceM5.scenario_engine import MonthlyClimate
    from resilienceM5.stress_test import evaluate_scenarios
    from resilienceM5.rescue_mode import build_rescue_shortlist
    req = {"rotations": [{"id": str(i), "crops": ["maize"]} for i in range(3)], "field_area_ha": 2,
           "latitude": 40, "longitude": 10, "demo": True, "input_provenance": {"area": "QA"},
           "rotation_calendar": [{"crop_id": "maize", "start_month": 5, "end_month": 10}]}
    climate = MonthlyClimate((25.,)*12, (100.,)*12, {"source_urls": ["https://example.invalid/test-only"]})
    out = evaluate_with_plan_engine(req, climate, 2000)
    first = out["rotations"][0]
    assert first["details"]["coordinates"] == {"latitude": 40, "longitude": 10}
    assert first["details"]["water"]["budget_mm_per_season"] == 100
    assert first["details"]["crops"][0]["months"] == ["May", "Jun", "Jul", "Aug", "Sep", "Oct"]
    assert first["details"]["input_provenance"] == {"area": "QA"}
    stress = evaluate_scenarios(req, climate, climate, 2000, .5, evaluate_with_plan_engine)
    for scenario in stress["differences_vs_baseline"]:
        for rotation in scenario["changes"]:
            assert rotation["score_comparable"] is False
            assert rotation["score_change"] is None
    rescue = build_rescue_shortlist(stress)
    assert all(item["rotation_sequence"] == ["maize"] for item in rescue["candidates"])


@pytest.mark.parametrize("rotation", [[], ["unknown"], ["maize"]*4, ["maize"]*6, [None]])
def test_invalid_rotation_rejected(rotation):
    with pytest.raises(ValueError):
        build_plans(current=rotation, seasonal=None, budget_mm=None, area_ha=None, soil_ph=None, priorities=None)


def test_calendar_overlap_mismatch_and_long_crop():
    from resilienceM5.m2_adapter import calendar_months
    with pytest.raises(ValueError, match="match"):
        calendar_months(["maize"], [{"crop_id": "cowpea", "start_month":1, "end_month":4}])
    with pytest.raises(ValueError, match="overlaps"):
        calendar_months(["maize", "cowpea"], [{"crop_id":"maize", "start_month":1,"end_month":6}, {"crop_id":"cowpea","start_month":5,"end_month":8}])
    assert calendar_months(["maize"], [{"crop_id":"maize","start_month":11,"end_month":4}]) == [[11,12,1,2,3,4]]
    out = build_plans(current=["cabbage","cowpea","maize"], seasonal=None, budget_mm=100, area_ha=1, soil_ph=None, priorities=None)
    assert out["plans"][0]["calendar_complete"] is False
    assert any(c["constraint"] == "calendar" for c in out["plans"][0]["failed_constraints"])


@pytest.mark.parametrize("patch", [
    {"rotations": []}, {"rotations": [["unknown"]]}, {"rotations": [["maize"]*4]},
    {"water_budget_mm": -1}, {"prices_rs_per_kg": {"maize": -1}},
])
def test_plans_invalid_requests_are_422_before_climate(monkeypatch, patch):
    from app import app
    from fastapi.testclient import TestClient
    import agricultureM2.plans_routes as routes
    async def forbidden(*args):
        pytest.fail("Invalid input reached climate retrieval")
    monkeypatch.setattr(routes, "_seasonal", forbidden)
    response = TestClient(app).post("/api/agriculture/plans", json={"farm_id":"pamplemousses-04", **patch})
    assert response.status_code == 422


@pytest.mark.parametrize("patch", [
    {"field_area_ha": None}, {"field_area_ha": 0}, {"field_area_ha": -1},
    {"rotations": [{"id": str(i), "crops": ["unknown"]} for i in range(3)]},
    {"rotations": [{"id": "duplicate", "crops": ["maize"]} for i in range(3)]},
    {"rotations": ["bad"]*3}, {"soil_ph": "NaN"},
])
def test_stress_invalid_requests_are_422_before_climate(monkeypatch, patch):
    from app import app
    from fastapi.testclient import TestClient
    from resilienceM5 import routes
    async def forbidden(*args):
        pytest.fail("Invalid input reached climate retrieval")
    monkeypatch.setattr(routes, "get_farm_climate", forbidden)
    req = {"rotations":[{"id":str(i),"crops":["maize"]} for i in range(3)], "field_area_ha":1, **patch}
    response = TestClient(app).post("/api/resilience/stress-test", json={"latitude":-20,"longitude":57,"baseline_water_budget_m3":100,"rotation_request":req})
    assert response.status_code == 422


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_values_rejected(value):
    from resilienceM5.m2_adapter import validate_plan_request
    req = {"rotations":[{"id":str(i),"crops":["maize"]} for i in range(3)], "field_area_ha":value}
    with pytest.raises(ValueError, match="finite"):
        validate_plan_request(req, 100)


def test_stale_m1_fallback_disclosed_without_rewriting_cache(tmp_path, monkeypatch):
    import sqlite3
    from climateM1.services import cache
    monkeypatch.setattr(cache, "DATABASE_PATH", tmp_path / "cache.sqlite3")
    monkeypatch.setattr(cache, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_TTL_SECONDS", 1)
    payload = {"provenance": [{"source":"NASA POWER", "caveat":"Original source caveat"}]}
    cache.save_cached("test", payload)
    with sqlite3.connect(cache.DATABASE_PATH) as conn:
        conn.execute("UPDATE climate_cache SET retrieved_at = '2000-01-01T00:00:00+00:00'")
    assert cache.get_cached("test") is None
    result = cache.get_cached("test", allow_stale=True)
    assert "Stale cache fallback" in result["provenance"][0]["caveat"]
    with sqlite3.connect(cache.DATABASE_PATH) as conn:
        assert json.loads(conn.execute("SELECT payload FROM climate_cache").fetchone()[0]) == payload


@pytest.mark.parametrize("invalid_metadata", ["expired", "signature", "legacy"])
def test_processed_cache_invalidation_uses_provider(tmp_path, monkeypatch, invalid_metadata):
    from datetime import datetime, timezone
    from resilienceM5 import scenario_engine as se
    saved = json.loads(se.FARM_CLIMATE_CACHE.read_text(encoding="utf-8"))
    key = next(iter(saved))
    coords, scenario, period = key.split("|")
    lat, lon = map(float, coords.split(","))
    start, end = map(int, period.split("-"))
    record = saved[key]
    record["saved_at"] = datetime.now(timezone.utc).isoformat()
    record["method_signature"] = se._farm_cache_signature()
    if invalid_metadata == "expired":
        record["saved_at"] = "2000-01-01T00:00:00+00:00"
    elif invalid_metadata == "signature":
        record["method_signature"] = "old-method"
    else:
        record.pop("method_signature")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(se, "_farm_climate_cache", lambda: saved)
    monkeypatch.setattr(se, "_save_farm_climate", lambda *args: None)
    calls = []
    async def provider(*args):
        calls.append(args)
        return tuple(se.MonthlyClimate(tuple(record[k]["temperature_c"]),tuple(record[k]["precipitation_mm"]),record[k]["provenance"]) for k in ("observed","future"))
    monkeypatch.setattr(se, "_registered_m1", provider)
    asyncio.run(se.get_farm_climate(lat,lon,scenario,start,end))
    assert len(calls) == 1


@pytest.mark.parametrize("missing", ["area_ha", "budget_mm", "soil_ph", "climate_rows"])
def test_independently_missing_inputs_keep_agricultural_feasibility_unknown(missing):
    from agricultureM2.plan_engine import climate_from_monthly
    args = dict(current=["maize"], seasonal=None, budget_mm=1000, area_ha=1, soil_ph=6.5, priorities=None,
                climate_rows=climate_from_monthly([25]*12, [100]*12))
    args[missing] = None
    out = build_plans(**args)
    assert all(p["feasible"] is None for p in out["plans"])
    assert all(p["income"]["profit_rs"] is None for p in out["plans"])


def test_validated_current_processed_cache_hit(monkeypatch):
    from datetime import datetime, timezone
    from resilienceM5 import scenario_engine as se
    saved = json.loads(se.FARM_CLIMATE_CACHE.read_text(encoding="utf-8"))
    key = next(iter(saved))
    coords, scenario, period = key.split("|")
    lat, lon = map(float, coords.split(","))
    start, end = map(int, period.split("-"))
    saved[key]["saved_at"] = datetime.now(timezone.utc).isoformat()
    saved[key]["method_signature"] = se._farm_cache_signature()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(se, "_farm_climate_cache", lambda: saved)
    async def forbidden(*args):
        pytest.fail("Valid current cache was not reused")
    monkeypatch.setattr(se, "_registered_m1", forbidden)
    observed, future = asyncio.run(se.get_farm_climate(lat,lon,scenario,start,end))
    assert future.provenance["scenario"] == scenario
    assert future.provenance["m5_cache"] == "validated_saved_M1_result"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_numbers_return_4xx(value):
    from app import app
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    for path, body in (
        ("/api/agriculture/plans", '{"farm_id":"pamplemousses-04","water_budget_mm":' + value + '}'),
        ("/api/resilience/stress-test", '{"latitude":-20,"longitude":57,"rotation_request":{},"baseline_water_budget_m3":' + value + '}'),
    ):
        response = client.post(path, content=body, headers={"content-type":"application/json"})
        assert response.status_code == 422, response.text
