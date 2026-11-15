"""Conservative 2050 Rescue Mode derived exclusively from stress-test outputs."""
from __future__ import annotations

import math


def _validate_score(score, rotation_id: str, scenario_id: str):
    if score is not None and (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
    ):
        raise ValueError(f"Invalid score for {rotation_id} in {scenario_id}")


def _rotation_sequence(outcome: dict):
    details = outcome.get("details")
    analysis = details.get("analysis") if isinstance(details, dict) else None
    sequence = analysis.get("sequence") if isinstance(analysis, dict) else None
    if sequence is None and isinstance(details, dict):
        sequence = details.get("rotation")
    if isinstance(sequence, list) and sequence:
        return sequence
    return None


def build_rescue_shortlist(stress_output: dict) -> dict:
    if not isinstance(stress_output, dict):
        raise ValueError("Rescue Mode requires a stress-test result object")
    scenarios = stress_output.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("Rescue Mode requires at least one evaluated scenario")

    scenario_ids = []
    normalized_scenarios = []
    rotation_ids = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("Each stress-test scenario must be an object")
        scenario_id = scenario.get("scenario_id")
        rotations = scenario.get("rotations")
        if not isinstance(scenario_id, str) or not scenario_id.strip() or scenario_id in scenario_ids:
            raise ValueError("Stress-test scenarios need unique non-empty ids")
        if not isinstance(rotations, dict):
            raise ValueError(f"Scenario {scenario_id} must contain a rotations object")
        scenario_ids.append(scenario_id)
        normalized = {}
        for rotation_id, outcome in rotations.items():
            if not isinstance(rotation_id, str) or not rotation_id:
                raise ValueError(f"Scenario {scenario_id} contains an invalid rotation id")
            if not isinstance(outcome, dict):
                raise ValueError(f"Rotation {rotation_id} in {scenario_id} must be an object")
            feasible = outcome.get("feasible")
            if feasible is not None and not isinstance(feasible, bool):
                raise ValueError(f"Rotation {rotation_id} feasibility must be boolean or null")
            score = outcome.get("score")
            _validate_score(score, rotation_id, scenario_id)
            score_scale = outcome.get("score_scale")
            if score_scale is not None and (
                not isinstance(score_scale, str) or not score_scale.strip()
            ):
                raise ValueError(f"Invalid score scale for {rotation_id} in {scenario_id}")
            failed_constraints = outcome.get("failed_constraints", [])
            if not isinstance(failed_constraints, list):
                raise ValueError(f"Rotation {rotation_id} failed_constraints must be an array")
            normalized[rotation_id] = outcome
            rotation_ids.add(rotation_id)
        normalized_scenarios.append((scenario, normalized))

    if not rotation_ids:
        raise ValueError("Stress-test scenarios contain no rotation results")

    shortlist = []
    for rotation_id in sorted(rotation_ids):
        outcomes = [
            (scenario, rotations.get(rotation_id))
            for scenario, rotations in normalized_scenarios
        ]
        passed = sum(1 for _, outcome in outcomes if outcome and outcome.get("feasible") is True)
        failed = sum(1 for _, outcome in outcomes if outcome and outcome.get("feasible") is False)
        unknown = len(scenarios) - passed - failed

        score_scales = [
            outcome.get("score_scale") if outcome is not None else None
            for _, outcome in outcomes
        ]
        scores_comparable = (
            all(
                outcome is not None
                and outcome.get("score") is not None
                and isinstance(outcome.get("score_scale"), str)
                and bool(outcome.get("score_scale").strip())
                for _, outcome in outcomes
            )
            and len(set(score_scales)) == 1
        )
        score_comparisons = [
            {"scenario_id": scenario["scenario_id"], "score": outcome.get("score")}
            for scenario, outcome in outcomes
            if outcome is not None and outcome.get("score") is not None
        ]
        failed_scenarios = [
            {
                "scenario_id": scenario["scenario_id"],
                "scenario_type": scenario.get("type"),
                "water_budget_m3": scenario.get("water_budget_m3"),
                "failed_constraints": outcome.get("failed_constraints", []),
            }
            for scenario, outcome in outcomes
            if outcome is not None and outcome.get("feasible") is False
        ]
        unknown_scenarios = [
            scenario["scenario_id"]
            for scenario, outcome in outcomes
            if outcome is None or outcome.get("feasible") is None
        ]
        sequence = None
        for _, outcome in outcomes:
            if outcome is not None:
                sequence = _rotation_sequence(outcome)
                if sequence is not None:
                    break

        shortlist.append({
            "rotation_id": rotation_id,
            "scenarios_passed": passed,
            "scenarios_failed": failed,
            "scenarios_unknown": unknown,
            "scenario_count": len(scenarios),
            "feasible_in_all_tested_scenarios": passed == len(scenarios) and len(scenarios) >= 2,
            "failed_scenarios": failed_scenarios,
            "unknown_scenarios": unknown_scenarios,
            "scenario_results": [
                {
                    "scenario_id": scenario["scenario_id"],
                    "scenario_type": scenario.get("type"),
                    "water_budget_m3": scenario.get("water_budget_m3"),
                    "feasible": outcome.get("feasible") if outcome is not None else None,
                    "failed_constraints": outcome.get("failed_constraints", []) if outcome is not None else [],
                    "score": outcome.get("score") if outcome is not None else None,
                    "score_scale": outcome.get("score_scale") if outcome is not None else None,
                    "water_requirement_m3": outcome.get("water_requirement_m3") if outcome is not None else None,
                }
                for scenario, outcome in outcomes
            ],
            "score_comparisons": score_comparisons if scores_comparable else [],
            "score_comparison_status": (
                "comparable_scale"
                if scores_comparable
                else "scores_missing_or_scales_not_comparable"
            ),
            "rotation_sequence": sequence,
            "sequence_status": (
                "M2_sequence_only_no_calendar_or_interventions"
                if sequence is not None
                else "pending_verified_m2_sequence"
            ),
        })

    scenario_rotation_sets = [set(rotations) for _, rotations in normalized_scenarios]
    shortlist.sort(key=lambda item: (
        -item["scenarios_passed"],
        item["scenarios_unknown"],
        item["scenarios_failed"],
        item["rotation_id"],
    ))
    complete_scenario_set = (
        len(scenarios) in (2, 4)
        and all(rotation_set == scenario_rotation_sets[0] for rotation_set in scenario_rotation_sets)
    )
    return {
        "candidates": shortlist,
        "tested_scenario_count": len(scenarios),
        "scenario_set_complete": complete_scenario_set,
        "scenario_conditions": [
            {
                "scenario_id": scenario["scenario_id"],
                "scenario_type": scenario.get("type"),
                "water_budget_m3": scenario.get("water_budget_m3"),
                "temperature_annual_mean_c": scenario.get("temperature_annual_mean_c"),
                "precipitation_annual_total_mm": scenario.get("precipitation_annual_total_mm"),
                "climate_provenance": scenario.get("climate_provenance"),
            }
            for scenario in scenarios
        ],
        "explanation": (
            "Candidates are ordered by known feasibility passes, then unknown and failed outcomes. "
            "Unknown M2 feasibility is not counted as a pass; scores are compared only when every "
            "scenario supplies a non-null score on the same declared scale. This is not a survival probability."
        ),
        "adaptation_pathway": {
            "status": "verified_rotation_sequences_only" if any(item["rotation_sequence"] for item in shortlist) else "pending_verified_m2_agronomic_logic",
            "note": "M2 season sequence labels can be shown, but no dates, planting calendar, or interventions are inferred.",
        },
        "recommended_action": "Review only confirmed model outputs with the farmer and a local agronomist; unknown feasibility requires further M2 agronomic logic.",
        "limitations": [
            "Results cover only supplied stress-test scenarios and do not guarantee future yield, survival, soil recovery, or viability.",
            "Incomplete scenario coverage or unknown M2 feasibility prevents a robust-across-scenarios conclusion.",
            "No new crop predictions, scores, or survival probabilities are generated here.",
        ],
    }
