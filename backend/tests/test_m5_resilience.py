"""Deterministic math contract tests. Fixtures are only unit-test vectors,
not NASA observations. Live/demo climate data must be downloaded from NASA.
"""
from __future__ import annotations

import asyncio
import calendar
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from resilienceM5.climate_twin import compare_climates, find_climate_twins
from resilienceM5 import routes as m5_routes
from resilienceM5.m1_adapter import _to_monthly_climate, _validate_m1_provenance
from resilienceM5.rescue_mode import build_rescue_shortlist
from resilienceM5.routes import router
from resilienceM5.scenario_engine import (
    CANDIDATE_SITES,
    DataUnavailable,
    MonthlyClimate,
    PowerClient,
    assemble_climatology,
)
from resilienceM5 import scenario_engine
from resilienceM5.stress_test import evaluate_scenarios
from climateM1.services.history import normalize_power_monthly
from climateM1.services.projections import _aggregate_projection_year


def climate(t=25.0, p=100.0, source="unit-test-only"):
    return MonthlyClimate(tuple([float(t)] * 12), tuple([float(p)] * 12),
                          {"source_urls": [source], "data_type": "unit_test_only"})


def test_rejects_incomplete_climate():
    with pytest.raises(ValueError):
        MonthlyClimate((25.,) * 11, (100.,) * 12, {"source_urls": ["unit-test"]})


def test_rejects_climate_without_source():
    with pytest.raises(ValueError):
        MonthlyClimate((25.,) * 12, (100.,) * 12, {})


def test_rejects_negative_precipitation():
    with pytest.raises(ValueError):
        climate(p=-1)


def test_climate_twin_identical_candidate_wins():
    sites = [({"id": str(i)}, climate(t, p)) for i, (t, p) in enumerate(
        [(25, 100), (27, 200), (20, 80), (30, 300)])]
    ranked = compare_climates(climate(25, 100), sites, top_k=3)
    assert ranked[0]["location"]["id"] == "0"
    assert ranked[0]["distance_index"] == 0


def test_candidate_rank_uses_monthly_standardized_distance_and_stable_ties():
    target = climate(25, 100)
    candidates = [
        ({"id": "z"}, climate(25, 100)),
        ({"id": "b"}, climate(27, 200)),
        ({"id": "a"}, climate(27, 200)),
    ]
    ranked = compare_climates(target, candidates, top_k=3)
    assert [entry["location"]["id"] for entry in ranked] == ["z", "a", "b"]
    assert ranked[0]["temperature_distance_component"] == 0
    assert ranked[0]["precipitation_distance_component"] == 0


def test_rejects_too_few_candidates():
    with pytest.raises(DataUnavailable):
        compare_climates(climate(), [({"id": "a"}, climate())])


def test_rejects_duplicate_candidate_ids():
    with pytest.raises(ValueError):
        compare_climates(climate(), [({"id": "a"}, climate()) for _ in range(4)])


def test_nasa_monthly_units_and_leap_year():
    # Emulates a NASA response shape for a parser test only; no production payload.
    saved = {
        "url": "unit-test-parser-fixture", "retrieved_at": "test",
        "payload": {"properties": {"parameter": {
            "T2M": {f"2024{m:02d}": 25.0 for m in range(1, 13)},
            "PRECTOTCORR": {f"2024{m:02d}": 1.0 for m in range(1, 13)},
        }}, "parameters": {"T2M": {"units": "C"}, "PRECTOTCORR": {"units": "mm/day"}}},
    }
    result = assemble_climatology(saved, 2024, 2024)
    assert result.precipitation_mm[1] == 29.0
    assert result.precipitation_mm[0] == calendar.monthrange(2024, 1)[1]


def test_candidate_normalization_rejects_an_incomplete_month():
    saved = {
        "url": "unit-test-parser-fixture",
        "retrieved_at": "test",
        "payload": {
            "properties": {
                "parameter": {
                    "T2M": {
                        f"{year}{month:02d}": 25.0
                        for year in (2023, 2024)
                        for month in range(1, 13)
                        if not (year == 2024 and month == 2)
                    },
                    "PRECTOTCORR": {
                        f"{year}{month:02d}": 1.0
                        for year in (2023, 2024)
                        for month in range(1, 13)
                    },
                }
            },
            "parameters": {
                "T2M": {"units": "C"},
                "PRECTOTCORR": {"units": "mm/day"},
            },
        },
    }
    with pytest.raises(DataUnavailable, match="Incomplete"):
        assemble_climatology(saved, 2023, 2024)


def power_monthly_fixture(year=2024):
    return {
        "parameters": {
            "T2M": {"units": "C"},
            "PRECTOTCORR": {"units": "mm/day"},
        },
        "properties": {
            "parameter": {
                "T2M": {f"{year}{month:02d}": 25.0 for month in range(1, 13)},
                "PRECTOTCORR": {
                    f"{year}{month:02d}": 1.0 for month in range(1, 13)
                },
            }
        },
    }


def test_m1_power_monthly_conversion_and_m5_normalization():
    response = normalize_power_monthly(
        power_monthly_fixture(),
        -20.103,
        57.575,
        2024,
        2024,
        "https://power.larc.nasa.gov/test",
        "2026-01-01T00:00:00+00:00",
    )
    climate_record = _to_monthly_climate(response)
    assert climate_record.temperature_c == (25.0,) * 12
    assert climate_record.precipitation_mm[0] == 31.0
    assert climate_record.precipitation_mm[1] == 29.0
    assert climate_record.provenance["source_urls"] == [
        "https://power.larc.nasa.gov/test"
    ]


def test_m1_adapter_preserves_and_checks_future_source_identity():
    provenance = {
        "source": "NASA NEX-GDDP-CMIP6",
        "source_urls": ["https://ds.nccs.nasa.gov/thredds/ncss/grid/fixture"],
        "requested_coordinates": {"latitude": -20.103, "longitude": 57.575},
        "period_start": "2041-01",
        "period_end": "2060-12",
        "scenario": "ssp245",
        "data_type": "bias_corrected_climate_projection",
        "climate_adjustment": "NASA NEX; no additional delta adjustment",
        "model_series": [
            {"id": f"model-{index}", "variant": "r1i1p1f1"}
            for index in range(3)
        ],
        "model_uncertainty": [{"month": month} for month in range(1, 13)],
    }
    climate_record = MonthlyClimate((25.0,) * 12, (100.0,) * 12, provenance)
    _validate_m1_provenance(
        climate_record,
        "NASA NEX-GDDP-CMIP6",
        -20.103,
        57.575,
        "2041-01",
        "2060-12",
        "ssp245",
    )
    with pytest.raises(DataUnavailable, match="scenario"):
        _validate_m1_provenance(
            climate_record,
            "NASA NEX-GDDP-CMIP6",
            -20.103,
            57.575,
            "2041-01",
            "2060-12",
            "ssp370",
        )


def test_m1_power_rejects_missing_values_and_incomplete_period():
    response = power_monthly_fixture()
    response["properties"]["parameter"]["T2M"]["202402"] = -999
    with pytest.raises(ValueError, match="incomplete"):
        normalize_power_monthly(
            response,
            -20.103,
            57.575,
            2024,
            2024,
            "https://power.larc.nasa.gov/test",
            "2026-01-01T00:00:00+00:00",
        )


def test_m1_power_rejects_unexpected_precipitation_units():
    response = power_monthly_fixture()
    response["parameters"]["PRECTOTCORR"]["units"] = "mm/month"
    with pytest.raises(ValueError, match="Unexpected NASA POWER PRECTOTCORR unit"):
        normalize_power_monthly(
            response,
            -20.103,
            57.575,
            2024,
            2024,
            "https://power.larc.nasa.gov/test",
            "2026-01-01T00:00:00+00:00",
        )


def test_m1_nex_daily_units_convert_to_calendar_month_totals():
    precipitation = []
    temperature = []
    for month in range(1, 13):
        days = calendar.monthrange(2024, month)[1]
        for day in range(1, days + 1):
            timestamp = f"2024-{month:02d}-{day:02d} 12:00:00"
            for rows, value, units in (
                (precipitation, 1 / 86400, "kg m-2 s-1"),
                (temperature, 300.0, "K"),
            ):
                rows.append({
                    "time": timestamp,
                    "latitude": -20.0,
                    "longitude": 57.5,
                    "value": value,
                    "calendar": "standard",
                    "units": units,
                })
    normalized = _aggregate_projection_year(
        precipitation, temperature, -20.103, 57.575, 2024
    )
    assert normalized["temperature_c"][0] == pytest.approx(26.85)
    assert normalized["precipitation_mm"][0] == pytest.approx(31.0)
    assert normalized["precipitation_mm"][1] == pytest.approx(29.0)


def test_m1_nex_rejects_incomplete_month():
    precipitation = []
    temperature = []
    for month in range(1, 13):
        days = calendar.monthrange(2024, month)[1]
        if month == 1:
            days -= 1
        for day in range(1, days + 1):
            timestamp = f"2024-{month:02d}-{day:02d} 12:00:00"
            for rows, value, units in (
                (precipitation, 1 / 86400, "kg m-2 s-1"),
                (temperature, 300.0, "K"),
            ):
                rows.append({
                    "time": timestamp,
                    "latitude": -20.0,
                    "longitude": 57.5,
                    "value": value,
                    "calendar": "standard",
                    "units": units,
                })
    with pytest.raises(ValueError, match="Incomplete"):
        _aggregate_projection_year(
            precipitation, temperature, -20.103, 57.575, 2024
        )


def test_offline_candidate_cache_miss_is_explicit(tmp_path):
    client = PowerClient(cache_dir=tmp_path, offline=True)
    with pytest.raises(DataUnavailable, match="cache missing"):
        client.historical(-20.103, 57.575)


def test_climate_twin_reports_offline_candidate_cache_misses(tmp_path, monkeypatch):
    async def provide_climate(*_args):
        return climate(), climate()

    monkeypatch.setattr(scenario_engine, "_registered_m1", provide_climate)
    with pytest.raises(DataUnavailable, match="Excluded candidates: MG_TOAMASINA"):
        asyncio.run(
            find_climate_twins(
                -20.103,
                57.575,
                "ssp245",
                2041,
                2060,
                client=PowerClient(cache_dir=tmp_path, offline=True),
            )
        )


def test_candidate_source_response_is_cached_and_reused_offline(tmp_path, monkeypatch):
    synthetic_response = power_monthly_fixture()
    synthetic_response["geometry"] = {"coordinates": [57.575, -20.103]}

    class SyntheticResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps(synthetic_response).encode("utf-8")

    calls = []

    def synthetic_urlopen(request, timeout):
        calls.append(request.full_url)
        return SyntheticResponse()

    monkeypatch.setattr(scenario_engine, "urlopen", synthetic_urlopen)
    online = PowerClient(cache_dir=tmp_path, offline=False)
    climate_record = online.historical(-20.103, 57.575, 2024, 2024)
    assert climate_record.precipitation_mm[1] == 29.0
    assert climate_record.provenance["cache_status"] == "network"
    assert "power.larc.nasa.gov" in climate_record.provenance["source_urls"][0]
    assert climate_record.provenance["requested_coordinates"] == {
        "latitude": -20.103,
        "longitude": 57.575,
    }

    offline = PowerClient(cache_dir=tmp_path, offline=True)
    cached = offline.historical(-20.103, 57.575, 2024, 2024)
    assert cached.temperature_c == climate_record.temperature_c
    assert cached.provenance["cache_status"] == "fresh_cache"
    assert len(calls) == 1


def test_climate_twin_request_and_response_validation(monkeypatch):
    async def fake_twins(latitude, longitude, scenario, start_year, end_year, top_k, client):
        month = climate().to_dict()
        return {
            "field": {"latitude": latitude, "longitude": longitude},
            "scenario": scenario,
            "period": {"start_year": start_year, "end_year": end_year},
            "historical": month,
            "projected_target": month,
            "analogs": [
                {
                    "location": {**CANDIDATE_SITES[index], "id": f"site-{index}"},
                    "distance_index": float(index),
                    "temperature_rmse_c": 0.0,
                    "precipitation_mae_mm_per_month": 0.0,
                    "temperature_distance_component": 0.0,
                    "precipitation_distance_component": 0.0,
                    "monthly_comparison": [
                        {
                            "month": m + 1,
                            "future_t_c": 25.0,
                            "candidate_t_c": 25.0,
                            "future_p_mm": 100.0,
                            "candidate_p_mm": 100.0,
                        }
                        for m in range(12)
                    ],
                    "candidate_provenance": {"source_urls": ["test-only"]},
                }
                for index in range(3)
            ],
            "candidate_count": 3,
            "excluded_candidates": [],
            "method": {"name": "synthetic fixture"},
            "limitations": ["synthetic fixture; test only"],
        }

    monkeypatch.setattr(m5_routes, "find_climate_twins", fake_twins)
    client = TestClient(FastAPI())
    client.app.include_router(router)
    response = client.post(
        "/api/resilience/climate-twin",
        json={
            "latitude": -20.103,
            "longitude": 57.575,
            "scenario": "ssp245",
            "start_year": 2041,
            "end_year": 2060,
        },
    )
    assert response.status_code == 200
    assert len(response.json()["analogs"]) == 3
    assert response.json()["historical"]["precipitation_mm"] == [100.0] * 12

    invalid = client.post(
        "/api/resilience/climate-twin",
        json={
            "latitude": -20.103,
            "longitude": 57.575,
            "scenario": "ssp126",
            "start_year": 2041,
            "end_year": 2060,
        },
    )
    assert invalid.status_code == 422


def test_unified_app_mounts_resilience_once_and_registers_m1():
    from app import app

    route_paths = list(app.openapi()["paths"])
    assert route_paths.count("/api/resilience/health") == 1
    assert route_paths.count("/api/resilience/climate-twin") == 1
    response = TestClient(app).get("/api/resilience/health")
    assert response.status_code == 200
    assert response.json()["m1_provider_connected"] is True
    assert response.json()["m2_evaluator_connected"] is True
    assert response.json()["m2_scenario_feasibility_supported"] is False


def mock_m2(payload, month, water_budget):
    # Test adapter only: deterministic fake M2 results used to prove orchestration.
    assert "sentinel" in payload
    assert len(month.temperature_c) == 12
    return {"rotations": [
        {"id": "current", "feasible": water_budget is None or water_budget >= 80, "score": 60,
         "failed_constraints": [] if water_budget is None or water_budget >= 80 else ["water_budget"]},
        {"id": "alternative_a", "feasible": True, "score": 65, "failed_constraints": []},
        {"id": "alternative_b", "feasible": True, "score": 70, "failed_constraints": []},
    ]}


def test_stress_reuses_m2_and_computes_differences():
    output = evaluate_scenarios({"sentinel": 1}, climate(), climate(26, 80),
                                baseline_water_budget_m3=100,
                                irrigation_reduction_fraction=0.5, evaluator=mock_m2)
    assert len(output["scenarios"]) == 4
    assert output["scenarios"][0]["rotations"]["current"]["feasible"]
    assert not output["scenarios"][2]["rotations"]["current"]["feasible"]
    assert output["differences_vs_baseline"][1]["changes"][0]["feasibility_changed"]


def test_rescue_mode_uses_only_stress_results():
    output = evaluate_scenarios({"sentinel": 1}, climate(), climate(26, 80),
                                100, 0.5, evaluator=mock_m2)
    rescue = build_rescue_shortlist(output)
    assert rescue["candidates"][0]["scenarios_passed"] == 4
    current = next(x for x in rescue["candidates"] if x["rotation_id"] == "current")
    assert current["scenarios_passed"] == 2


def test_reduction_requires_water_budget():
    with pytest.raises(ValueError):
        evaluate_scenarios({"sentinel": 1}, climate(), climate(),
                           irrigation_reduction_fraction=0.3, evaluator=mock_m2)


def test_router_and_unconnected_stress_return_503(monkeypatch):
    client = TestClient(FastAPI())
    # TestClient requires a mounted router, not a second production server.
    client.app.include_router(router)
    def no_m2():
        from resilienceM5.stress_test import M2NotConnected
        raise M2NotConnected("M2 adapter not registered")

    monkeypatch.setattr(m5_routes, "get_m2_evaluator", no_m2)
    r = client.post("/api/resilience/stress-test", json={
        "latitude": -20.2, "longitude": 57.5, "baseline_water_budget_m3": 100,
        "rotation_request": {"sentinel": 1},
    })
    assert r.status_code == 503
    assert "M2 adapter not registered" in r.json()["detail"]


def test_invalid_future_year_returns_422():
    client = TestClient(FastAPI())
    client.app.include_router(router)
    r = client.post("/api/resilience/climate-twin", json={
        "latitude": -20.2, "longitude": 57.5,
        "start_year": 2060, "end_year": 2040,
    })
    assert r.status_code == 422
