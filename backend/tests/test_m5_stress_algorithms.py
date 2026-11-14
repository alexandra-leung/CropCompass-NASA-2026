from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from resilienceM5 import routes as m5_routes
from resilienceM5.rescue_mode import build_rescue_shortlist
from resilienceM5.routes import router
from resilienceM5.scenario_engine import MonthlyClimate
from resilienceM5.stress_test import M2NotConnected, evaluate_scenarios


def climate(temperature: float, precipitation: float) -> MonthlyClimate:
    return MonthlyClimate(
        (temperature,) * 12,
        (precipitation,) * 12,
        {"source_urls": ["https://test.invalid/climate"], "data_type": "test_only"},
    )


def test_scenario_orchestration_passes_reduced_budget_and_independent_requests():
    request = {"rotations": [{"id": "current", "crops": ["maize", "cowpea"]}]}
    received = []

    def evaluator(rotation_request, monthly, water_budget):
        received.append((deepcopy(rotation_request), water_budget, monthly.temperature_c[0]))
        rotation_request["rotations"][0]["id"] = "mutated"
        passes = water_budget >= 80 and monthly.temperature_c[0] < 30
        return {
            "rotations": [
                {"id": "rotation_1", "feasible": passes, "score": None, "failed_constraints": []},
                {"id": "rotation_2", "feasible": True, "score": None, "failed_constraints": []},
                {"id": "rotation_3", "feasible": False, "score": None, "failed_constraints": ["test_constraint"]},
            ]
        }

    output = evaluate_scenarios(
        request, climate(25, 100), climate(35, 40), 100, 0.3, evaluator
    )
    assert [scenario["water_budget_m3"] for scenario in output["scenarios"]] == [100, 100, 70, 70]
    assert [call[1] for call in received] == [100, 100, 70, 70]
    assert all(call[0] == request for call in received)
    assert [scenario["scenario_id"] for scenario in output["scenarios"]] == [
        "historical_baseline",
        "projected_future",
        "historical_restricted_irrigation",
        "future_restricted_irrigation",
    ]
    assert output["monthly_climate_differences_vs_historical"][0] == {
        "month": 1,
        "temperature_change_c": 10,
        "precipitation_change_mm": -60,
    }


def test_missing_budget_and_invalid_reduction_are_rejected():
    evaluator = lambda *_: {"rotations": []}
    with pytest.raises(ValueError, match="water budget"):
        evaluate_scenarios({"rotations": []}, climate(20, 50), climate(20, 50), evaluator=evaluator)
    with pytest.raises(ValueError, match="strictly between"):
        evaluate_scenarios(
            {"rotations": []},
            climate(20, 50),
            climate(20, 50),
            100,
            1.0,
            evaluator,
        )


def test_inconsistent_rotation_ids_fail_instead_of_dropping_results():
    calls = 0

    def evaluator(*_):
        nonlocal calls
        calls += 1
        suffix = "a" if calls == 1 else "b"
        return {
            "rotations": [
                {"id": f"rotation_{suffix}", "feasible": True, "score": None},
                {"id": "rotation_2", "feasible": True, "score": None},
                {"id": "rotation_3", "feasible": True, "score": None},
            ]
        }

    with pytest.raises(ValueError, match="same rotation IDs"):
        evaluate_scenarios(
            {}, climate(20, 50), climate(21, 60), 100, evaluator=evaluator
        )


def test_score_and_rank_deltas_require_comparable_scale():
    def evaluator(_, monthly, __):
        future = monthly.temperature_c[0] > 25
        scores = [70, 85, 20] if future else [80, 50, 20]
        ranks = [2, 1, 3] if future else [1, 2, 3]
        return {
            "score_scale": "test-scale-0-100",
            "rotations": [
                {
                    "id": f"rotation_{index}",
                    "feasible": True,
                    "score": scores[index - 1],
                    "score_scale": "test-scale-0-100",
                    "rank": ranks[index - 1],
                }
                for index in range(1, 4)
            ],
        }

    output = evaluate_scenarios(
        {}, climate(25, 100), climate(26, 100), 100, evaluator=evaluator
    )
    first = output["differences_vs_baseline"][0]["changes"][0]
    assert first["score_comparable"] is True
    assert first["score_change"] == -10
    assert first["rank_change"] == 1


def test_rescue_mode_marks_missing_and_unknown_results_without_scoring_them():
    result = build_rescue_shortlist({
        "scenarios": [
            {
                "scenario_id": "historical",
                "type": "historical",
                "water_budget_m3": 100,
                "rotations": {
                    "rotation_a": {"feasible": True, "score": None, "failed_constraints": []},
                    "rotation_b": {"feasible": None, "score": None, "failed_constraints": []},
                },
            },
            {
                "scenario_id": "future",
                "type": "projected",
                "water_budget_m3": 100,
                "rotations": {
                    "rotation_a": {"feasible": False, "score": None, "failed_constraints": ["water_budget"]},
                },
            },
        ]
    })
    assert result["scenario_set_complete"] is False
    assert result["candidates"][0]["rotation_id"] == "rotation_a"
    assert result["candidates"][0]["scenarios_passed"] == 1
    assert result["candidates"][0]["failed_scenarios"][0]["failed_constraints"] == ["water_budget"]
    assert result["candidates"][0]["score_comparisons"] == []
    assert result["candidates"][1]["scenarios_unknown"] == 2
    assert result["adaptation_pathway"]["status"] == "pending_verified_m2_agronomic_logic"
    assert "probability" in result["explanation"]


def test_rescue_mode_does_not_compare_scores_when_a_scale_is_missing():
    result = build_rescue_shortlist({
        "scenarios": [
            {
                "scenario_id": "historical",
                "rotations": {
                    "rotation_a": {
                        "feasible": True,
                        "score": 80,
                        "score_scale": "unitless-demo-score",
                    },
                },
            },
            {
                "scenario_id": "future",
                "rotations": {
                    "rotation_a": {"feasible": True, "score": 75},
                },
            },
        ]
    })
    candidate = result["candidates"][0]
    assert candidate["score_comparison_status"] == "scores_missing_or_scales_not_comparable"
    assert candidate["score_comparisons"] == []


def test_api_requires_budget_and_returns_m2_dependency_error(monkeypatch):
    client = TestClient(FastAPI())
    client.app.include_router(router)
    body = {
        "latitude": -20.2,
        "longitude": 57.5,
        "rotation_request": {"rotations": []},
    }
    missing_budget = client.post("/api/resilience/stress-test", json=body)
    assert missing_budget.status_code == 422

    body["baseline_water_budget_m3"] = 100
    body["irrigation_reduction_fraction"] = 1.0
    invalid_reduction = client.post("/api/resilience/stress-test", json=body)
    assert invalid_reduction.status_code == 422

    body.pop("irrigation_reduction_fraction")

    def no_m2():
        raise M2NotConnected("M2 evaluator is not registered")

    monkeypatch.setattr(m5_routes, "get_m2_evaluator", no_m2)
    unavailable = client.post("/api/resilience/stress-test", json=body)
    assert unavailable.status_code == 503
    assert "M2 evaluator" in unavailable.json()["detail"]
