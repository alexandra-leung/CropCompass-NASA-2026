
from agricultureM2.water_budget import evaluate_water_budget

# Hypothetical test inputs, not NASA observations.
ASSUMPTIONS = {
    "field_area_ha": 1.0,
    "daily_et0_mm": 4.0,
    "effective_rainfall_mm_per_day": 1.0,
    "irrigation_efficiency": 0.80,
}


def run_scenario(budget):
    return evaluate_water_budget(
        water_budget_m3=budget,
        **ASSUMPTIONS,
    )


def by_name(result):
    return {
        r["rotation_name"]: r
        for r in result["rotations"]
    }


# Three irrigation-budget scenarios.
baseline = by_name(run_scenario(15000))
moderate = by_name(run_scenario(11000))
severe = by_name(run_scenario(6000))

print("\nCROPCOMPASS FINAL VALIDATION")
print("=" * 66)
print(
    f"{'Rotation':<23}"
    f"{'Demand m3':>12}"
    f"{'15,000':>10}"
    f"{'11,000':>10}"
    f"{'6,000':>10}"
)

for name in baseline:
    demand = baseline[name]["irrigation_required_m3"]

    statuses = [
        "PASS" if scenario[name]["water_feasible"] else "FAIL"
        for scenario in [baseline, moderate, severe]
    ]

    print(
        f"{name:<23}"
        f"{demand:>12,.2f}"
        f"{statuses[0]:>10}"
        f"{statuses[1]:>10}"
        f"{statuses[2]:>10}"
    )


# Test 1: Exactly three rotations.
assert len(baseline) == 3

# Test 2: Demand never changes if only budget changes.
for name in baseline:
    assert (
        baseline[name]["irrigation_required_m3"]
        == moderate[name]["irrigation_required_m3"]
        == severe[name]["irrigation_required_m3"]
    )

# Test 3: All rotations fit baseline water budget.
assert all(
    r["water_feasible"]
    for r in baseline.values()
)

# Test 4: Moderate restriction excludes the current plan
# but retains the two alternatives.
assert moderate["Current rotation"]["water_feasible"] is False
assert moderate["Alternative A"]["water_feasible"] is True
assert moderate["Alternative B"]["water_feasible"] is True

# Test 5: Severe restriction excludes all rotations.
assert all(
    r["water_feasible"] is False
    for r in severe.values()
)

# Test 6: All results must have explanations.
for scenario in [baseline, moderate, severe]:
    assert all(r["reason"] for r in scenario.values())

# Test 7: Check invalid input is rejected.
try:
    run_scenario(-100)
    raise AssertionError("Negative budget was accepted")
except ValueError:
    pass

print("\nALL FINAL VALIDATION TESTS PASSED")
