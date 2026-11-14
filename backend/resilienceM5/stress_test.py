"""M5 scenario orchestration over *the existing M2 evaluator*.

No M2 formulas, crop thresholds, or unverified route names are duplicated here.
An explicit adapter is registered after reading agricultureM2/API_CONTRACT.md.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Callable
from .scenario_engine import MonthlyClimate

# Protocol: adapter(rotation_request: dict, climate: MonthlyClimate,
#                    water_budget_m3: float|None) -> M2 standard comparison dict.
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
        raise M2NotConnected("M2 adapter not registered. Read agricultureM2/API_CONTRACT.md; register a wrapper in backend/app.py")
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
        if not isinstance(rot_id, str) or not rot_id or rot_id in result or not isinstance(feasible, bool):
            raise ValueError("M2 rotations need unique string id and boolean feasible")
        score = r.get("score")
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score)):
            raise ValueError("M2 score must be finite numeric or null")
        failed = r.get("failed_constraints", [])
        if not isinstance(failed, list):
            raise ValueError("M2 failed_constraints must be an array")
        result[rot_id] = {"feasible": feasible, "score": score, "failed_constraints": failed,
                          "details": deepcopy(r)}
    return result


def evaluate_scenarios(rotation_request: dict, historical: MonthlyClimate, future: MonthlyClimate,
                       baseline_water_budget_m3: float | None = None,
                       irrigation_reduction_fraction: float | None = None,
                       evaluator: M2Evaluator | None = None) -> dict:
    """Run the *same* M2 engine on actual NASA climate arrays; don't fabricate results."""
    engine = evaluator or get_m2_evaluator()
    if irrigation_reduction_fraction is not None:
        if not 0 < irrigation_reduction_fraction < 1:
            raise ValueError("Irrigation reduction fraction must be strictly between 0 and 1")
        if baseline_water_budget_m3 is None or baseline_water_budget_m3 < 0:
            raise ValueError("Reducing irrigation requires farmer-entered baseline water budget in m3")
    if baseline_water_budget_m3 is not None and baseline_water_budget_m3 < 0:
        raise ValueError("Water budget cannot be negative")
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
        reduced = round(baseline_water_budget_m3 * (1 - irrigation_reduction_fraction), 4)
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
                        "climate_provenance": climate.provenance, "rotations": rotations})
    baseline = results[0]["rotations"]
    if any(set(s["rotations"]) != set(baseline) for s in results):
        raise ValueError("The M2 adapter must preserve the same rotation IDs, including infeasible plans, across all scenarios")
    differences = []
    for result in results[1:]:
        differences.append({"scenario_id": result["scenario_id"], "changes": [
            {"rotation_id": rid, "baseline_feasible": prev["feasible"], "scenario_feasible": result["rotations"][rid]["feasible"],
             "feasibility_changed": prev["feasible"] != result["rotations"][rid]["feasible"],
             "baseline_score": prev["score"], "scenario_score": result["rotations"][rid]["score"],
             "failed_constraints": result["rotations"][rid]["failed_constraints"]}
            for rid, prev in baseline.items()
        ]})
    return {
        "scenarios": results, "differences_vs_baseline": differences,
        "method": "Identical M2 rotation evaluation rerun under M1 historical and NASA NEX monthly climates",
        "verified_m2_climate_sensitivity": False,
        "verification_required": "Manually confirm M2 uses both temperature and precipitation inputs, not only the scenario label",
        "limitations": ["Scores and feasibility are modeled decision indicators, not measured farm outcomes",
                        "Restricted irrigation is a farmer-defined hypothetical, not NASA rainfall",
                        "Climate grid resolution and CMIP6 ensemble uncertainty affect interpretation",
                        "NASA NEX-GDDP-CMIP6 is bias-corrected/downscaled; M5 adds no climate-delta adjustment"],
    }
