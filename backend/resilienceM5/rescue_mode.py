"""Conservative 2050 Rescue Mode derived exclusively from stress-test outputs."""
from __future__ import annotations


def build_rescue_shortlist(stress_output: dict) -> dict:
    scenarios = stress_output.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) < 2:
        raise ValueError("Rescue Mode requires an actual baseline + future M2 stress-test result")
    ids = set(scenarios[0]["rotations"])
    if not ids or any(set(s["rotations"]) != ids for s in scenarios):
        raise ValueError("Rotation IDs differ between scenario evaluations")
    shortlist = []
    for rid in ids:
        outcomes = [(s["scenario_id"], s["rotations"][rid]) for s in scenarios]
        feasible = sum(1 for _, o in outcomes if o["feasible"])
        worst_score = min((o["score"] for _, o in outcomes if o["feasible"] and o["score"] is not None), default=None)
        shortlist.append({
            "rotation_id": rid, "scenarios_feasible": feasible,
            "scenario_count": len(scenarios),
            "feasible_in_all_tested_scenarios": feasible == len(scenarios),
            "worst_feasible_score": worst_score,
            "failed_scenarios": [
                {"scenario_id": name, "failed_constraints": out["failed_constraints"]}
                for name, out in outcomes if not out["feasible"]
            ],
        })
    shortlist.sort(key=lambda x: (-x["scenarios_feasible"],
                                  -float(x["worst_feasible_score"] or 0), x["rotation_id"]))
    return {
        "candidates": shortlist,
        "explanation": "Ordering by the number of modeled scenario feasibility passes, then worst available feasible score. These are not survival probabilities.",
        "recommended_action": "Review promising rotations with the farmer and a local agronomist; planting calendars and crop choices must come from the verified M2 engine.",
        "limitations": ["Resilience is assessed only against the tested scenarios; no guarantee of future yield, soil recovery or viability"],
    }
