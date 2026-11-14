
from .rotation_water_comparison import compare_rotation_water


def evaluate_water_budget(
    water_budget_m3,
    field_area_ha=1.0,
    daily_et0_mm=4.0,
    effective_rainfall_mm_per_day=1.0,
    irrigation_efficiency=0.80,
):
    """
    Evaluate three rotations against an irrigation budget.

    All climate values are hypothetical test assumptions
    until verified climate and rainfall processing are added.

    Water budget covers the COMPLETE rotation sequence,
    not a single month or growing season.
    """

    if water_budget_m3 < 0:
        raise ValueError("Water budget cannot be negative.")

    if not 0 < irrigation_efficiency <= 1:
        raise ValueError(
            "Irrigation efficiency must be greater "
            "than 0 and at most 1."
        )

    if effective_rainfall_mm_per_day < 0:
        raise ValueError(
            "Effective rainfall cannot be negative."
        )

    comparison = compare_rotation_water(
        daily_et0_mm=daily_et0_mm,
        field_area_ha=field_area_ha,
    )

    results = []

    for rotation in comparison["rotations"]:
        total_net_irrigation_mm = 0.0
        crop_results = []

        for crop in rotation["crops"]:
            growth_days = crop["growth_days"]
            etc_mm = crop["etc_mm"]

            effective_rainfall_mm = (
                effective_rainfall_mm_per_day
                * growth_days
            )

            net_irrigation_mm = max(
                0.0,
                etc_mm - effective_rainfall_mm,
            )

            total_net_irrigation_mm += net_irrigation_mm

            crop_results.append({
                "crop_id": crop["crop_id"],
                "growth_days": growth_days,
                "etc_mm": etc_mm,
                "assumed_effective_rainfall_mm": round(
                    effective_rainfall_mm, 2
                ),
                "net_irrigation_mm": round(
                    net_irrigation_mm, 2
                ),
            })

        gross_irrigation_mm = (
            total_net_irrigation_mm
            / irrigation_efficiency
        )

        # 1 mm over 1 ha = 10 m3.
        irrigation_volume_m3 = (
            gross_irrigation_mm
            * field_area_ha
            * 10
        )

        feasible = (
            irrigation_volume_m3
            <= water_budget_m3
        )

        remaining_m3 = (
            water_budget_m3
            - irrigation_volume_m3
        )

        results.append({
            "rotation_name": rotation["rotation_name"],
            "total_growth_days": rotation[
                "total_growth_days"
            ],
            "crops": crop_results,
            "net_irrigation_mm": round(
                total_net_irrigation_mm, 2
            ),
            "gross_irrigation_mm": round(
                gross_irrigation_mm, 2
            ),
            "irrigation_required_m3": round(
                irrigation_volume_m3, 2
            ),
            "water_budget_m3": water_budget_m3,
            "water_remaining_m3": round(
                remaining_m3, 2
            ),
            "water_feasible": feasible,
            "reason": (
                "Within illustrative irrigation budget"
                if feasible
                else "Estimated irrigation exceeds budget"
            ),
        })

    return {
        "field_area_ha": field_area_ha,
        "water_budget_m3": water_budget_m3,
        "daily_et0_mm": daily_et0_mm,
        "effective_rainfall_mm_per_day":
            effective_rainfall_mm_per_day,
        "irrigation_efficiency":
            irrigation_efficiency,
        "assumption_status": "hypothetical_demo",
        "budget_period": "complete_rotation_sequence",
        "rotations": results,
        "limitations": [
            "Daily ET0 is a hypothetical constant.",
            "Effective rainfall is a hypothetical "
            "constant, not observed rainfall.",
            "Rainfall timing and soil storage are "
            "not modeled.",
            "Rotations have different total "
            "growing durations.",
            "Feasibility checks irrigation only; "
            "other agronomic constraints are "
            "not yet evaluated.",
        ],
    }
