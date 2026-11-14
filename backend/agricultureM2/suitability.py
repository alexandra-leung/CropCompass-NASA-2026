
import pandas as pd

from .crop_catalog import get_crop


def check_crop_suitability(
    crop_id: str,
    temperature_c: float | None = None,
    soil_ph: float | None = None,
):
    crop = get_crop(crop_id)

    checks = []
    missing = []

    def check_range(
        name,
        actual,
        lower_key,
        upper_key,
    ):
        if actual is None:
            missing.append(name)
            return

        lower = crop.get(lower_key)
        upper = crop.get(upper_key)

        if pd.isna(lower) or pd.isna(upper):
            missing.append(
                f"{name}_reference_range"
            )
            return

        passed = float(lower) <= actual <= float(upper)

        checks.append({
            "factor": name,
            "actual": actual,
            "minimum": float(lower),
            "maximum": float(upper),
            "passed": passed,
        })

    check_range(
        "temperature_c",
        temperature_c,
        "temp_min_c",
        "temp_max_c",
    )

    check_range(
        "soil_ph",
        soil_ph,
        "ph_min",
        "ph_max",
    )

    failures = [
        check for check in checks
        if not check["passed"]
    ]

    if failures:
        status = "outside_reference_range"
    elif missing:
        status = "insufficient_data"
    else:
        status = "within_checked_ranges"

    return {
        "crop_id": crop_id,
        "status": status,
        "checks": checks,
        "missing": missing,
        "source_url": crop["source_url"],
        "note": (
            "This is a preliminary screening, "
            "not a complete agronomic suitability "
            "assessment."
        ),
    }
