
from agricultureM2.water_budget import evaluate_water_budget


def show_results(budget):
    result = evaluate_water_budget(
        water_budget_m3=budget,
        field_area_ha=1.0,
        daily_et0_mm=4.0,
        effective_rainfall_mm_per_day=1.0,
        irrigation_efficiency=0.80,
    )

    print("\n" + "=" * 60)
    print(f"WATER BUDGET: {budget} m3")
    print("=" * 60)

    for rotation in result["rotations"]:
        print("\n", rotation["rotation_name"])

        print(
            "Growing days:",
            rotation["total_growth_days"]
        )

        print(
            "Estimated irrigation:",
            rotation["irrigation_required_m3"],
            "m3"
        )

        print(
            "Remaining water:",
            rotation["water_remaining_m3"],
            "m3"
        )

        print(
            "Feasible:",
            rotation["water_feasible"]
        )

        print("Reason:", rotation["reason"])

    return result


# Scenario 1: Baseline irrigation budget
baseline = show_results(15000)

# Scenario 2: Restricted irrigation budget
restricted = show_results(6000)

# Test 1: Exactly three rotation results
assert len(baseline["rotations"]) == 3

# Test 2: Irrigation cannot be negative
assert all(
    rotation["irrigation_required_m3"] >= 0
    for rotation in baseline["rotations"]
)

# Test 3: Lower budget must never make a
# previously infeasible rotation feasible.
for original, reduced in zip(
    baseline["rotations"],
    restricted["rotations"],
):
    assert not (
        reduced["water_feasible"]
        and not original["water_feasible"]
    )

# Test 4: Demand must stay unchanged when
# only the budget changes.
for original, reduced in zip(
    baseline["rotations"],
    restricted["rotations"],
):
    assert (
        original["irrigation_required_m3"]
        == reduced["irrigation_required_m3"]
    )

print("\nALL WATER WALLET TESTS PASSED")
