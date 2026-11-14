from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from resilienceM5 import routes as m5_routes
from resilienceM5.m2_adapter import evaluate_m2_scenario
from resilienceM5.scenario_engine import MonthlyClimate
from resilienceM5.stress_test import evaluate_scenarios


def climate(temperature: float, precipitation: float) -> MonthlyClimate:
    return MonthlyClimate(
        (temperature,) * 12,
        (precipitation,) * 12,
        {
            "source": "test-only fixture",
            "source_urls": ["https://test.invalid/m1-fixture"],
            "data_type": "test_only",
        },
    )


ROTATION_REQUEST = {
    "rotations": [
        {"id": "current", "crops": ["maize", "maize", "maize"]},
        {"id": "alternative_a", "crops": ["maize", "cowpea", "sweet_potato"]},
        {"id": "alternative_b", "crops": ["cowpea", "sweet_potato", "groundnut"]},
    ]
}


def test_actual_m2_engine_preserves_rotation_ids_and_null_decision_outputs():
    result = evaluate_m2_scenario(ROTATION_REQUEST, climate(25, 100), 100)
    assert [rotation["id"] for rotation in result["rotations"]] == [
        "current",
        "alternative_a",
        "alternative_b",
    ]
    assert all(rotation["feasible"] is None for rotation in result["rotations"])
    assert all(rotation["score"] is None for rotation in result["rotations"])
    assert all(rotation["water_requirement_m3"] is None for rotation in result["rotations"])
    assert result["climate_inputs_used"]["water_budget_feasibility"] is False
    assert result["climate_inputs_used"]["precipitation_water_balance"] is False
    assert result["rotations"][0]["details"]["analysis"]["rotation"] == [
        "maize",
        "maize",
        "maize",
    ]


def test_actual_m2_adapter_rejects_invalid_rotation_requests():
    with pytest.raises(ValueError, match="at least three"):
        evaluate_m2_scenario(
            {"rotations": [{"id": "current", "crops": ["maize", "cowpea"]}]},
            climate(25, 100),
            100,
        )

    duplicate_ids = {
        "rotations": [
            {"id": "duplicate", "crops": ["maize", "cowpea"]},
            {"id": "duplicate", "crops": ["maize", "groundnut"]},
            {"id": "third", "crops": ["cowpea", "groundnut"]},
        ]
    }
    with pytest.raises(ValueError, match="Duplicate rotation id"):
        evaluate_m2_scenario(duplicate_ids, climate(25, 100), 100)

    unknown_crop = {
        "rotations": [
            {"id": "current", "crops": ["maize", "cowpea"]},
            {"id": "alternative_a", "crops": ["maize", "groundnut"]},
            {"id": "alternative_b", "crops": ["not_a_crop", "groundnut"]},
        ]
    }
    with pytest.raises(ValueError, match="Unknown crop"):
        evaluate_m2_scenario(unknown_crop, climate(25, 100), 100)


def test_actual_m2_temperature_path_is_unavailable_without_crop_reference_ranges():
    ordinary = evaluate_m2_scenario(ROTATION_REQUEST, climate(25, 100), 100)
    changed = evaluate_m2_scenario(ROTATION_REQUEST, climate(60, 100), 100)
    ordinary_check = ordinary["rotations"][0]["details"]["monthly_crop_suitability"][0]["calendar_month_checks"][0]
    changed_check = changed["rotations"][0]["details"]["monthly_crop_suitability"][0]["calendar_month_checks"][0]
    assert ordinary_check["checks"] == changed_check["checks"] == []
    assert "temperature_c_reference_range" in ordinary_check["missing"]
    assert ordinary_check == changed_check


def test_actual_m2_stress_test_reports_climate_and_irrigation_inputs_without_fabricating_effects():
    result = evaluate_scenarios(
        ROTATION_REQUEST,
        climate(25, 100),
        climate(35, 40),
        baseline_water_budget_m3=100,
        irrigation_reduction_fraction=0.3,
        evaluator=evaluate_m2_scenario,
    )
    assert len(result["scenarios"]) == 4
    ids = set(result["scenarios"][0]["rotations"])
    assert all(set(scenario["rotations"]) == ids for scenario in result["scenarios"])
    assert [scenario["water_budget_m3"] for scenario in result["scenarios"]] == [
        100,
        100,
        70,
        70,
    ]
    assert result["monthly_climate_differences_vs_historical"][0] == {
        "month": 1,
        "temperature_change_c": 10,
        "precipitation_change_mm": -60,
    }
    assert result["m2_climate_sensitivity"] == {
        "temperature_suitability_screen_changed": False,
        "temperature_suitability_screen_available": False,
        "precipitation_water_calculation_available": False,
        "overall_verified": False,
    }
    assert result["verified_m2_climate_sensitivity"] is False
    baseline = result["scenarios"][0]["rotations"]["current"]
    restricted = result["scenarios"][2]["rotations"]["current"]
    assert baseline["details"]["water_budget_m3"] == 100
    assert restricted["details"]["water_budget_m3"] == 70
    assert baseline["details"]["water_budget_applied"] is False
    assert baseline["details"]["analysis"] == restricted["details"]["analysis"]


def test_stress_test_api_keeps_m1_provenance(monkeypatch):
    historical = climate(25, 100)
    future = climate(27, 90)

    async def provide_climate(*_):
        return historical, future

    monkeypatch.setattr(m5_routes, "get_farm_climate", provide_climate)
    monkeypatch.setattr(m5_routes, "get_m2_evaluator", lambda: evaluate_m2_scenario)
    client = TestClient(FastAPI())
    client.app.include_router(m5_routes.router)
    response = client.post(
        "/api/resilience/stress-test",
        json={
            "latitude": -20.2,
            "longitude": 57.5,
            "scenario": "ssp245",
            "start_year": 2041,
            "end_year": 2060,
            "baseline_water_budget_m3": 100,
            "rotation_request": ROTATION_REQUEST,
        },
    )
    assert response.status_code == 200
    output = response.json()
    assert output["scenarios"][0]["climate_provenance"]["source_urls"] == [
        "https://test.invalid/m1-fixture"
    ]
    assert output["scenarios"][1]["climate_provenance"]["data_type"] == "test_only"
    assert output["verified_m2_climate_sensitivity"] is False


def test_stress_test_api_maps_invalid_m2_rotation_data_to_422(monkeypatch):
    async def provide_climate(*_):
        return climate(25, 100), climate(27, 90)

    monkeypatch.setattr(m5_routes, "get_farm_climate", provide_climate)
    monkeypatch.setattr(m5_routes, "get_m2_evaluator", lambda: evaluate_m2_scenario)
    client = TestClient(FastAPI())
    client.app.include_router(m5_routes.router)
    response = client.post(
        "/api/resilience/stress-test",
        json={
            "latitude": -20.2,
            "longitude": 57.5,
            "scenario": "ssp245",
            "start_year": 2041,
            "end_year": 2060,
            "baseline_water_budget_m3": 100,
            "rotation_request": {
                "rotations": [
                    {"id": "current", "crops": ["maize", "cowpea"]},
                    {"id": "alternative_a", "crops": ["maize", "groundnut"]},
                ]
            },
        },
    )
    assert response.status_code == 422
    assert "at least three rotations" in response.json()["detail"]
