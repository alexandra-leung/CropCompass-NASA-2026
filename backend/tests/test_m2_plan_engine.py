"""M2 plan engine: water need, suitability, feasibility, scoring and the /plans route."""

import pytest
from fastapi.testclient import TestClient

from agricultureM2.plan_engine import build_plans, candidate_rotations, crops, kc_at, monthly_climate

SEASONAL = [{"period": f"2023-{s}", "temperatureC": t, "rainfallMm": r} for s, t, r in
            [("DJF", 27.0, 220.0), ("MAM", 25.5, 180.0), ("JJA", 22.5, 90.0), ("SON", 23.5, 60.0)]]


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("M3_FARM_STORE", str(tmp_path / "farms.json"))


def test_reference_data_loads_for_all_crops():
    cat = crops()
    assert set(cat) == {"maize", "tomato", "onion", "cabbage", "cowpea", "groundnut", "sweet_potato"}
    assert all(c["kc"] and c["range"] for c in cat.values())
    assert cat["cowpea"]["legume"] and not cat["maize"]["legume"]


def test_kc_curve_follows_fao56_stages():
    kc = crops()["maize"]["kc"]
    assert kc_at(kc, 0) == kc["ini"] and kc_at(kc, 70) == kc["mid"] and kc_at(kc, 999) == kc["end"]


def test_monthly_climate_needs_all_four_seasons():
    assert monthly_climate(SEASONAL[:3]) is None
    m = monthly_climate(SEASONAL)
    assert len(m) == 12 and m[0]["temperature_c"] == 27.0
    hotter = monthly_climate(SEASONAL, d_temp=2)
    assert hotter[0]["et0_mm"] > m[0]["et0_mm"]
    drier = monthly_climate(SEASONAL, d_rain_pct=-20)
    assert drier[0]["rain_mm"] < m[0]["rain_mm"]


def test_candidates_change_family_and_include_a_legume():
    cat = crops()
    for r in candidate_rotations(["maize", "maize", "maize"]):
        fams = [cat[c]["family"] for c in r]
        assert all(fams[i] != fams[i - 1] for i in range(3))
        assert any(cat[c]["legume"] for c in r)


def test_water_budget_decides_feasibility():
    big = build_plans(current=["maize", "cowpea", "sweet_potato"], seasonal=SEASONAL, budget_mm=2000, area_ha=1, soil_ph=None, priorities=None)
    small = build_plans(current=["maize", "cowpea", "sweet_potato"], seasonal=SEASONAL, budget_mm=10, area_ha=1, soil_ph=None, priorities=None)
    assert big["plans"][0]["feasible"] is True
    assert small["plans"][0]["feasible"] is False
    assert small["plans"][0]["failed_constraints"][0]["constraint"] == "water"


def test_monoculture_ranks_below_a_legume_rotation():
    out = build_plans(current=["maize", "maize", "maize"], seasonal=SEASONAL, budget_mm=2000, area_ha=0.6, soil_ph=None,
                      priorities={"water": 0.2, "soil": 0.6, "climate": 0.2})
    today = out["plans"][0]
    assert today["dna"]["repeated_family_seasons"] and not today["dna"]["legumes"]
    assert today["rank"] > 1 and out["best_plan_id"] != "current"
    assert len(out["plans"]) == 4 and {p["rank"] for p in out["plans"]} == {1, 2, 3, 4}


def test_no_climate_means_no_water_numbers_not_invented():
    out = build_plans(current=["maize", "cowpea", "cabbage"], seasonal=None, budget_mm=100, area_ha=1, soil_ph=None, priorities=None)
    p = out["plans"][0]
    assert out["status"] == "no_climate" and p["water"]["total_mm"] is None and p["scores"]["climate"] is None
    assert p["crops"][0]["suitability"] == "unknown"


def test_hot_scenario_can_make_a_crop_marginal():
    base = build_plans(current=["cabbage", "cowpea", "maize"], seasonal=SEASONAL, budget_mm=2000, area_ha=1, soil_ph=None, priorities=None)
    assert base["plans"][0]["crops"][0]["suitability"] in ("marginal", "unsuitable")   # cabbage in 27 °C


def test_plans_route_uses_m3_farm(monkeypatch):
    import agricultureM2.plans_routes as pr

    async def fake(_loc):
        return SEASONAL, None
    monkeypatch.setattr(pr, "_seasonal", fake)
    from app import app
    c = TestClient(app)
    r = c.post("/api/agriculture/plans", json={"farm_id": "pamplemousses-04"})
    assert r.status_code == 200
    d = r.json()
    assert d["farm_id"] == "pamplemousses-04" and d["plans"][0]["rotation"] == ["maize", "maize", "maize"]
    assert d["scenario"]["budget_mm_per_season"] == 600
    hot = c.post("/api/agriculture/plans", json={"farm_id": "pamplemousses-04", "temperature_change_c": 2, "water_budget_mm": 100}).json()
    assert hot["scenario"]["budget_mm_per_season"] == 100 and not any(p["feasible"] for p in hot["plans"])
    assert c.post("/api/agriculture/plans", json={"farm_id": "nope"}).status_code == 404


def test_fixed_rotations_are_evaluated_in_order():
    from agricultureM2.plan_engine import build_plans
    rots = [["cowpea", "cabbage", "maize"], ["maize", "tomato", "cowpea"]]
    out = build_plans(current=["maize", "maize", "maize"], seasonal=None, budget_mm=600, area_ha=1,
                      soil_ph=6.5, priorities=None, fixed_rotations=rots)
    assert [p["rotation"] for p in out["plans"][1:]] == rots


def test_harvest_value_and_income_score():
    from agricultureM2.plan_engine import build_plans, climate_from_monthly
    rows = climate_from_monthly([25] * 12, [100] * 12)
    out = build_plans(current=["maize", "maize", "maize"], seasonal=None, budget_mm=900, area_ha=1.0, soil_ph=6.5,
                      priorities={"income": 1}, fixed_rotations=[["cabbage", "tomato", "cowpea"]], climate_rows=rows)
    today, alt = out["plans"]
    assert today["income"]["harvest_value_rs"] > 0 and alt["income"]["harvest_value_rs"] > 0
    assert max(today["scores"]["income"], alt["scores"]["income"]) == 1.0
    priced = build_plans(current=["maize", "maize", "maize"], seasonal=None, budget_mm=900, area_ha=1.0, soil_ph=6.5,
                         priorities=None, climate_rows=rows, fixed_rotations=[["cabbage", "tomato", "cowpea"]], prices={"maize": 50})
    assert priced["plans"][0]["income"]["harvest_value_rs"] == 2 * today["income"]["harvest_value_rs"]


def test_m5_evaluator_uses_plan_engine():
    from resilienceM5.m2_adapter import evaluate_with_plan_engine
    from resilienceM5.scenario_engine import MonthlyClimate
    clim = MonthlyClimate(tuple([25.0] * 12), tuple([100.0] * 12), {"source": "test", "source_urls": ["https://power.larc.nasa.gov/test"]})
    req = {"rotations": [{"id": "a", "crops": ["maize", "maize", "maize"]}, {"id": "b", "crops": ["cowpea", "cabbage", "maize"]},
                         {"id": "c", "crops": ["cowpea", "tomato", "maize"]}], "field_area_ha": 1.0}
    out = evaluate_with_plan_engine(req, clim, 6000)
    assert [r["id"] for r in out["rotations"]] == ["a", "b", "c"]
    assert all(isinstance(r["feasible"], bool) for r in out["rotations"])
    small = evaluate_with_plan_engine(req, clim, 10)
    assert not any(r["feasible"] for r in small["rotations"])


def test_shap_values_add_up_to_score():
    from agricultureM2.plan_engine import build_plans, climate_from_monthly
    out = build_plans(current=["maize", "maize", "maize"], seasonal=None, budget_mm=900, area_ha=1.0, soil_ph=6.5,
                      priorities={"water": 1, "soil": 2, "climate": 1, "income": 1}, climate_rows=climate_from_monthly([25] * 12, [100] * 12))
    for p in out["plans"]:
        total = p["shap"]["base_value"] + sum(p["shap"]["values"].values())
        assert abs(total - p["score"]) < 0.01
        assert p["income"]["profit_rs"] == p["income"]["harvest_value_rs"] - p["income"]["cost_rs"]
