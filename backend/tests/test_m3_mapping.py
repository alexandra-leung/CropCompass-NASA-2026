"""M3 - farm profile, soil, water units, field boundaries and routes."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("M3_FARM_STORE", str(tmp_path / "farms_store.json"))


@pytest.fixture
def client():
    from app import app
    return TestClient(app)


# ----------------------------------------------------------------- units

def test_mm_m3_round_trip():
    from mappingM3.units import m3_to_mm, mm_to_m3
    assert mm_to_m3(150, 0.6) == 900.0          # 150 mm on 0.6 ha
    assert m3_to_mm(900, 0.6) == 150.0
    assert mm_to_m3(None, 0.6) is None and mm_to_m3(150, None) is None
    with pytest.raises(ValueError):
        mm_to_m3(10, 0)


# ----------------------------------------------------------------- soil

def test_soil_unknown_values_stay_null_and_are_listed():
    from mappingM3.soil_inputs import SoilInputs
    s = SoilInputs()
    assert s.ph is None and s.confidence() == "unknown"
    assert s.missing() == ["soil.texture", "soil.ph", "soil.drainage"]


def test_soil_value_needs_a_source():
    from mappingM3.soil_inputs import SoilInputs
    with pytest.raises(ValueError):
        SoilInputs(ph=6.5)
    assert SoilInputs(ph=6.5, ph_source="farmer").ph_source == "farmer"


def test_soil_confidence_levels():
    from mappingM3.soil_inputs import SoilInputs
    farmer = SoilInputs(texture="loam", texture_source="farmer", ph=6.2, ph_source="farmer", drainage="good", drainage_source="farmer")
    assert farmer.confidence() == "farmer_confirmed"
    assert SoilInputs(texture="clay", texture_source="map_estimate").confidence() == "partial"


# ----------------------------------------------------------------- boundaries

def test_square_boundary_has_requested_area():
    from mappingM3.field_boundaries import centroid, polygon_area_ha, square_boundary
    g = square_boundary(-20.103, 57.575, 0.6)
    assert abs(polygon_area_ha(g) - 0.6) < 0.01
    lat, lon = centroid(g)
    assert abs(lat + 20.103) < 1e-4 and abs(lon - 57.575) < 1e-4


@pytest.mark.parametrize("bad", [
    {"type": "Point", "coordinates": [57.5, -20.1]},
    {"type": "Polygon", "coordinates": [[[57.5, -20.1], [57.51, -20.1], [57.5, -20.1]]]},
    {"type": "Polygon", "coordinates": [[[57.5, -20.1], [57.51, -20.1], [57.51, -20.11], [57.5, -20.11]]]},
    {"type": "Polygon", "coordinates": [[[2.35, 48.85], [2.36, 48.85], [2.36, 48.86], [2.35, 48.85]]]},
    {"type": "Polygon", "coordinates": [[[-20.1, 57.5], [-20.1, 57.51], [-20.11, 57.51], [-20.1, 57.5]]]},
])
def test_invalid_polygons_rejected(bad):
    from mappingM3.field_boundaries import validate_polygon
    with pytest.raises(ValueError):
        validate_polygon(bad)


def test_nearest_location_uses_m1_registry():
    from mappingM3.field_boundaries import nearest_location
    assert nearest_location(-20.19, 57.71)["location_id"] == "flacq-02"
    assert nearest_location(-20.38, 57.38)["location_id"] == "black-river-01"


def test_auto_outline_is_not_invented():
    from mappingM3.field_boundaries import suggest_boundary
    s = suggest_boundary(-20.1, 57.57)
    assert s["status"] == "unavailable" and s["geometry"] is None


# ----------------------------------------------------------------- profile + M4 contract

def test_demo_farms_sit_on_registered_locations():
    from climateM1.services.locations import LOCATIONS
    from mappingM3.farm_profile import list_farms
    farms = list_farms()
    assert {f.farm_id for f in farms} >= {"pamplemousses-04", "flacq-02", "black-river-01"}
    assert all(f.location_id in LOCATIONS for f in farms)


def test_get_farm_profile_matches_m4_contract():
    from intelligenceM4.schemas import FarmContext
    from mappingM3.farm_profile import get_farm_profile
    ctx = get_farm_profile("pamplemousses-04")
    assert set(ctx) == {"farm_id", "location_id", "soil_ph", "field_area_ha", "irrigation_budget_m3", "current_rotation", "source"}
    assert ctx["source"] == "M3" and ctx["irrigation_budget_m3"] == 3600.0
    assert ctx["soil_ph"] is None               # unknown stays unknown
    FarmContext.model_validate(ctx)


def test_unknown_farm_raises():
    from mappingM3.farm_profile import get_farm_profile
    with pytest.raises(KeyError):
        get_farm_profile("nope")


def test_priorities_are_normalised():
    from mappingM3.farm_profile import Priorities
    p = Priorities(water=2, soil=1, climate=1, income=0)
    assert (p.water, p.soil, p.income) == (0.5, 0.25, 0.0)
    with pytest.raises(ValueError):
        Priorities(water=0, soil=0, climate=0, income=0)


def test_rain_only_means_zero_budget():
    from mappingM3.farm_profile import Irrigation
    assert Irrigation(water_source="rain_only").budget_mm_per_season == 0.0


def test_unknown_crop_and_location_rejected():
    from mappingM3.farm_profile import FarmProfileIn
    with pytest.raises(ValueError):
        FarmProfileIn(name="x", location_id="paris-01")
    with pytest.raises(ValueError):
        FarmProfileIn(name="x", location_id="flacq-02", current_rotation=["banana"])


def test_validation_lists_missing_and_contradictions():
    from mappingM3.farm_profile import FarmProfileIn, validate_profile
    from mappingM3.field_boundaries import FieldBoundary, square_boundary
    p = FarmProfileIn(name="x", location_id="flacq-02", field_area_ha=2.0,
                      boundary=FieldBoundary(geometry=square_boundary(-20.189, 57.714, 0.5)))
    r = validate_profile(p)
    fields = {m["field"] for m in r["missing"]}
    assert {"current_rotation", "irrigation.budget_mm_per_season", "soil.ph"} <= fields
    assert not r["ready_for_analysis"]
    assert any(w["field"] == "field_area_ha" for w in r["warnings"])


# ----------------------------------------------------------------- routes

def test_routes_list_get_context(client):
    farms = client.get("/api/farms").json()["farms"]
    assert farms[0]["demo"] is True and len(farms) >= 3
    full = client.get("/api/farms/flacq-02").json()
    assert full["irrigation_budget_m3"] == 5200.0 and full["validation"]["complete"] is True
    assert client.get("/api/farms/flacq-02/context").json()["source"] == "M3"
    assert client.get("/api/farms/missing").status_code == 404


def test_routes_locations_and_nearest(client):
    locs = client.get("/api/farms/locations").json()["locations"]
    assert {l["location_id"] for l in locs} == {"pamplemousses-04", "flacq-02", "black-river-01"}
    assert client.get("/api/farms/nearest-location?lat=-20.1&lon=57.57").json()["location_id"] == "pamplemousses-04"


def test_routes_create_patch_delete(client):
    body = {"name": "Test plot", "location_id": "flacq-02", "field_area_ha": 0.5,
            "current_rotation": ["maize", "cowpea"], "irrigation": {"water_source": "tank", "budget_mm_per_season": 100}}
    r = client.post("/api/farms", json=body)
    assert r.status_code == 201
    created = r.json()
    assert created["farm_id"] == "test-plot" and created["boundary"]["method"] == "default_square"
    assert created["irrigation_budget_m3"] == 500.0
    r = client.patch("/api/farms/test-plot", json={"irrigation": {"budget_mm_per_season": 75}})
    assert r.json()["irrigation"]["budget_mm_per_season"] == 75 and r.json()["irrigation"]["water_source"] == "tank"
    assert client.patch("/api/farms/test-plot", json={"current_rotation": ["banana"]}).status_code == 422
    assert client.delete("/api/farms/test-plot").status_code == 204
    assert client.delete("/api/farms/flacq-02").status_code == 403


def test_routes_boundary_measure_and_save(client):
    from mappingM3.field_boundaries import square_boundary
    g = square_boundary(-20.375, 57.381, 1.2)
    m = client.post("/api/farms/boundary/measure", json={"geometry": g}).json()
    assert abs(m["area_ha"] - 1.2) < 0.02 and m["nearest_location"]["location_id"] == "black-river-01"
    assert client.post("/api/farms/boundary/measure", json={"geometry": {"type": "Point"}}).status_code == 422
    r = client.put("/api/farms/black-river-01/boundary", json={"geometry": g, "method": "manual"})
    assert r.json()["boundary"]["method"] == "manual"


def test_m4_analyze_uses_m3_profile(client, monkeypatch):
    from intelligenceM4.providers import farm_provider
    res = farm_provider.get_farm_context("black-river-01")
    assert res.status == "ok" and res.data.current_rotation == ["maize", "cowpea", "sweet_potato"]
