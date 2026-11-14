"""M5 scenario orchestration over the existing M2 evaluator."""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Callable
from .scenario_engine import MonthlyClimate

# Protocol: adapter(rotation_request: dict, climate: MonthlyClimate,
#                    water_budget_m3: float|None) -> normalized M2 comparison dict.
M2Evaluator = Callable[[dict, MonthlyClimate, float | None], dict]
_registered_evaluator: M2Evaluator | None = None


class M2NotConnected(RuntimeError):
    pass


def register_m2_evaluator(evaluator: M2Evaluator) -> None:
    """Call once in backend/app.py AFTER checking M2's actual function signature."""
    global _registered_evaluator
    if not callable(evaluator):
        raise TypeError("M2 evaluator must be callable")
    _registered_evaluator = evaluator


def get_m2_evaluator() -> M2Evaluator:
    if _registered_evaluator is None:
        raise M2NotConnected("M2 evaluator is not registered in the unified backend")
    return _registered_evaluator


def _extract_rotations(m2_result: dict) -> dict:
    """Normalized M2 output contract; adapt at the interface, not in M5 science."""
    if not isinstance(m2_result, dict):
        raise ValueError("M2 result must be a dictionary")
    rotations = m2_result.get("rotations")
    if not isinstance(rotations, list) or len(rotations) < 3:
        raise ValueError("M2 normalized response must have >=3 rotations (current + >=2 options)")
    result = {}
    for r in rotations:
        if not isinstance(r, dict):
            raise ValueError("M2 rotation must be an object")
        rot_id, feasible = r.get("id"), r.get("feasible")
        if not isinstance(rot_id, str) or not rot_id or rot_id in result or (
            feasible is not None and not isinstance(feasible, bool)
        ):
            raise ValueError("M2 rotations need unique string ids and boolean-or-null feasibility")
        score = r.get("score")
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score)):
            raise ValueError("M2 score must be finite numeric or null")
        score_scale = r.get("score_scale")
        if score_scale is not None and (not isinstance(score_scale, str) or not score_scale.strip()):
            raise ValueError("M2 score_scale must be a non-empty string or null")
        failed = r.get("failed_constraints", [])
        if not isinstance(failed, list):
            raise ValueError("M2 failed_constraints must be an array")
        details = r.get("details", r)
        if not isinstance(details, dict):
            raise ValueError("M2 rotation details must be an object")
        water_requirement = r.get("water_requirement_m3")
        if water_requirement is not None and (
            isinstance(water_requirement, bool)
            or not isinstance(water_requirement, (int, float))
            or not math.isfinite(water_requirement)
            or water_requirement < 0
        ):
            raise ValueError("M2 water requirement must be finite nonnegative m3 or null")
        rank = r.get("rank")
        if rank is not None and (isinstance(rank, bool) or not isinstance(rank, int) or rank < 1):
            raise ValueError("M2 rank must be a positive integer or null")
        result[rot_id] = {
            "feasible": feasible,
            "score": score,
            "score_scale": score_scale,
            "rank": rank,
            "water_requirement_m3": water_requirement,
            "failed_constraints": deepcopy(failed),
            "details": deepcopy(details),
        }
    return result


def _temperature_screens(rotations: dict) -> dict:
    return {
        rotation_id: rotation["details"].get("monthly_crop_suitability")
        for rotation_id, rotation in rotations.items()
        if "monthly_crop_suitability" in rotation["details"]
    }


def evaluate_scenarios(rotation_request: dict, historical: MonthlyClimate, future: MonthlyClimate,
                       baseline_water_budget_m3: float | None = None,
                       irrigation_reduction_fraction: float | None = None,
                       evaluator: M2Evaluator | None = None) -> dict:
    """Run the *same* M2 engine on actual NASA climate arrays; don't fabricate results."""
    engine = evaluator or get_m2_evaluator()
    if baseline_water_budget_m3 is None:
        raise ValueError("Farmer-entered baseline water budget in m3 is required")
    if (
        isinstance(baseline_water_budget_m3, bool)
        or not isinstance(baseline_water_budget_m3, (int, float))
        or not math.isfinite(baseline_water_budget_m3)
        or baseline_water_budget_m3 < 0
    ):
        raise ValueError("Water budget must be a finite nonnegative value in m3")
    if irrigation_reduction_fraction is not None:
        if not 0 < irrigation_reduction_fraction < 1:
            raise ValueError("Irrigation reduction fraction must be strictly between 0 and 1")
    scenarios = [
        ("historical_baseline", historical, baseline_water_budget_m3, "historical_gridded"),
        (
            "projected_future",
            future,
            baseline_water_budget_m3,
            str(future.provenance.get("data_type", "climate_projection")),
        ),
    ]
    if irrigation_reduction_fraction is not None:
        reduced = baseline_water_budget_m3 * (1 - irrigation_reduction_fraction)
        scenarios.extend([
            ("historical_restricted_irrigation", historical, reduced, "farmer_what_if"),
            ("future_restricted_irrigation", future, reduced, "farmer_what_if_plus_projection"),
        ])
    results = []
    for scenario_id, climate, budget, label in scenarios:
        # Each call receives an independent deep copy of the M2 request.
        # Only the actual M2 adapter defines how climate and budget map to its contract.
        output = engine(deepcopy(rotation_request), climate, budget)
        rotations = _extract_rotations(output)
        results.append({"scenario_id": scenario_id, "type": label, "water_budget_m3": budget,
                        "temperature_annual_mean_c": round(sum(climate.temperature_c) / 12, 4),
                        "precipitation_annual_total_mm": round(sum(climate.precipitation_mm), 4),
                        "monthly_climate": [
                            {"month": month, "temperature_c": climate.temperature_c[month - 1],
                             "precipitation_mm": climate.precipitation_mm[month - 1]}
                            for month in range(1, 13)
                        ],
                        "climate_provenance": deepcopy(climate.provenance),
                        "m2_climate_inputs_used": deepcopy(output.get("climate_inputs_used", {})),
                        "m2_score_status": output.get("score_status"),
                        "m2_score_scale": output.get("score_scale"),
                        "m2_ranking": deepcopy(output.get("ranking")),
                        "rotations": rotations})
    baseline = results[0]["rotations"]
    if any(set(s["rotations"]) != set(baseline) for s in results):
        raise ValueError("The M2 adapter must preserve the same rotation IDs, including infeasible plans, across all scenarios")

    climate_differences = [
        {
            "month": month,
            "temperature_change_c": round(future.temperature_c[month - 1] - historical.temperature_c[month - 1], 4),
            "precipitation_change_mm": round(future.precipitation_mm[month - 1] - historical.precipitation_mm[month - 1], 4),
        }
        for month in range(1, 13)
    ]
    historical_screens = _temperature_screens(results[0]["rotations"])
    future_screens = _temperature_screens(results[1]["rotations"])
    temperature_screen_changed = (
        bool(historical_screens)
        and bool(future_screens)
        and historical_screens != future_screens
    )
    temperature_calculation_available = any(
        scenario["m2_climate_inputs_used"].get("temperature_suitability_calculation_available") is True
        for scenario in results
    )
    precipitation_calculation_available = all(
        scenario["m2_climate_inputs_used"].get("precipitation_water_balance") is True
        for scenario in results
    )

    differences = []
    for result in results[1:]:
        differences.append({"scenario_id": result["scenario_id"], "changes": [
            {
                "rotation_id": rid,
                "baseline_water_budget_m3": results[0]["water_budget_m3"],
                "scenario_water_budget_m3": result["water_budget_m3"],
                "baseline_feasible": prev["feasible"],
                "scenario_feasible": result["rotations"][rid]["feasible"],
                "feasibility_changed": (
                    prev["feasible"] != result["rotations"][rid]["feasible"]
                    if prev["feasible"] is not None and result["rotations"][rid]["feasible"] is not None
                    else None
                ),
                "baseline_score": prev["score"],
                "scenario_score": result["rotations"][rid]["score"],
                "score_comparable": (
                    prev["score_scale"] is not None
                    and prev["score_scale"] == result["rotations"][rid]["score_scale"]
                    and prev["score"] is not None
                    and result["rotations"][rid]["score"] is not None
                ),
                "score_change": (
                    result["rotations"][rid]["score"] - prev["score"]
                    if prev["score_scale"] is not None
                    and prev["score_scale"] == result["rotations"][rid]["score_scale"]
                    and prev["score"] is not None
                    and result["rotations"][rid]["score"] is not None
                    else None
                ),
                "baseline_rank": prev["rank"],
                "scenario_rank": result["rotations"][rid]["rank"],
                "rank_change": (
                    result["rotations"][rid]["rank"] - prev["rank"]
                    if prev["rank"] is not None and result["rotations"][rid]["rank"] is not None
                    else None
                ),
                "baseline_water_requirement_m3": prev["water_requirement_m3"],
                "scenario_water_requirement_m3": result["rotations"][rid]["water_requirement_m3"],
                "failed_constraints": deepcopy(result["rotations"][rid]["failed_constraints"]),
            }
            for rid, prev in baseline.items()
        ]})
    return {
        "scenarios": results, "differences_vs_baseline": differences,
        "baseline_water_budget_m3": baseline_water_budget_m3,
        "irrigation_reduction_fraction": irrigation_reduction_fraction,
        "monthly_climate_differences_vs_historical": climate_differences,
        "m2_climate_sensitivity": {
            "temperature_suitability_screen_changed": temperature_screen_changed,
            "temperature_suitability_screen_available": temperature_calculation_available,
            "precipitation_water_calculation_available": precipitation_calculation_available,
            "overall_verified": temperature_screen_changed and precipitation_calculation_available,
        },
        "verified_m2_climate_sensitivity": temperature_screen_changed and precipitation_calculation_available,
        "method": "M2 score_rotations and check_crop_suitability rerun for identical candidate sequences; M1 monthly climate and farmer budget provenance retained",
        "limitations": ["M2 does not calculate rotation feasibility or an irrigation requirement from this interface; these outputs are null, not inferred",
                        "Monthly temperature suitability checks are not assigned to a crop season because M2 has no crop calendar",
                        "M2 does not consume monthly precipitation or the farmer water budget; precipitation and reduced irrigation do not affect its calculations",
                        "M2 score_rotations currently returns no calibrated scores or ranking",
                        "Scores and feasibility, when an engine supplies them, are modeled decision indicators, not measured farm outcomes",
                        "Restricted irrigation is a farmer-defined hypothetical, not NASA rainfall",
                        "Climate grid resolution and CMIP6 ensemble uncertainty affect interpretation",
                        "NASA NEX-GDDP-CMIP6 is bias-corrected/downscaled; M5 adds no climate-delta adjustment"],
    }
