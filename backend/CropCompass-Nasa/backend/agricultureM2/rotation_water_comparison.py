
from .water_wallet import (
    load_coefficients,
    calculate_crop_water_demand,
)

# Initial demonstration rotations.
# These are examples, not validated recommendations.
DEMO_ROTATIONS = {
    "Current rotation": [
        "maize", "maize", "maize"
    ],
    "Alternative A": [
        "maize", "cowpea", "sweet_potato"
    ],
    "Alternative B": [
        "cowpea", "sweet_potato", "groundnut"
    ],
}


def compare_rotation_water(
    rotations=None,
    daily_et0_mm=4.0,
    field_area_ha=1.0,
):
    """Compare gross crop evapotranspiration across rotations.

    daily_et0_mm is a hypothetical constant for the MVP.
    It is not NASA-observed reference evapotranspiration.
    """

    if rotations is None:
        rotations = DEMO_ROTATIONS

    if not 0 <= daily_et0_mm <= 20:
        raise ValueError(
            "Daily ET0 must be between 0 and 20 mm/day."
        )

    if not 0 < field_area_ha <= 10000:
        raise ValueError(
            "Field area must be positive and realistic."
        )

    comparisons = []

    for rotation_name, crop_ids in rotations.items():
        crops = []
        total_etc = 0.0
        total_days = 0

        for crop_id in crop_ids:
            coefficients, source = load_coefficients(
                crop_id
            )

            growth_days = sum(
                int(coefficients[key])
                for key in [
                    "days_initial",
                    "days_development",
                    "days_mid",
                    "days_late",
                ]
            )

            et0_series = (
                [daily_et0_mm] * growth_days
            )

            result = calculate_crop_water_demand(
                crop_id=crop_id,
                daily_et0_mm=et0_series,
            )

            etc = result[
                "crop_evapotranspiration_mm"
            ]

            crops.append({
                "crop_id": crop_id,
                "growth_days": growth_days,
                "etc_mm": etc,
                "source_url": source,
            })

            total_etc += etc
            total_days += growth_days

        # 1 mm over 1 hectare = 10 cubic metres.
        water_volume_m3 = (
            total_etc * field_area_ha * 10
        )

        comparisons.append({
            "rotation_name": rotation_name,
            "crops": crops,
            "total_growth_days": total_days,
            "total_etc_mm": round(total_etc, 2),
            "gross_crop_water_volume_m3": round(
                water_volume_m3, 2
            ),
            "average_etc_mm_per_day": round(
                total_etc / total_days, 3
            ),
        })

    return {
        "field_area_ha": field_area_ha,
        "daily_et0_assumption_mm": daily_et0_mm,
        "et0_source_type": "hypothetical_test_input",
        "rotations": comparisons,
        "method": "FAO-style Kc x ET0",
        "limitations": [
            "ET0 is a constant hypothetical input.",
            "Rainfall has not been deducted.",
            "Irrigation efficiency is not included.",
            "Rotations have different growing durations.",
            "Results are not actual irrigation requirements.",
        ],
    }
