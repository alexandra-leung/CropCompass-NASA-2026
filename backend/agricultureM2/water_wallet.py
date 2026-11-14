
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[3]

COEFFICIENT_PATH = (
    BASE_DIR / "data" / "reference"
    / "crop_water_coefficients.csv"
)


def load_coefficients(crop_id: str):
    if not COEFFICIENT_PATH.exists():
        raise FileNotFoundError(
            "Crop coefficients file not found."
        )

    df = pd.read_csv(COEFFICIENT_PATH)

    matches = df[df["crop_id"] == crop_id]

    if matches.empty:
        raise ValueError(
            f"No verified coefficients for {crop_id}"
        )

    row = matches.iloc[0]

    fields = [
        "kc_initial",
        "kc_mid",
        "kc_end",
        "days_initial",
        "days_development",
        "days_mid",
        "days_late",
    ]

    if row[fields].isna().any():
        raise ValueError(
            f"Incomplete coefficients for {crop_id}"
        )

    values = {
        field: float(row[field])
        for field in fields
    }

    for field in fields[3:]:
        if not values[field].is_integer():
            raise ValueError(
                f"{field} must be a whole number."
            )

    if any(values[k] < 0 for k in fields):
        raise ValueError(
            "Coefficients and stage days cannot be negative."
        )

    if not str(row["source_url"]).startswith(
        ("http://", "https://")
    ):
        raise ValueError("Missing source URL.")

    return values, str(row["source_url"])


def calculate_daily_kc(
    day: int,
    coefficients: dict,
):
    initial = int(coefficients["days_initial"])
    development = int(
        coefficients["days_development"]
    )
    mid = int(coefficients["days_mid"])
    late = int(coefficients["days_late"])

    kc_initial = coefficients["kc_initial"]
    kc_mid = coefficients["kc_mid"]
    kc_end = coefficients["kc_end"]

    if day < initial:
        return kc_initial

    day -= initial

    if day < development:
        fraction = (day + 1) / development
        return (
            kc_initial
            + (kc_mid - kc_initial) * fraction
        )

    day -= development

    if day < mid:
        return kc_mid

    day -= mid

    if day < late:
        fraction = (day + 1) / late
        return (
            kc_mid
            + (kc_end - kc_mid) * fraction
        )

    raise ValueError(
        "Day exceeds the crop growth period."
    )


def calculate_crop_water_demand(
    crop_id: str,
    daily_et0_mm: list[float],
):
    coefficients, source_url = (
        load_coefficients(crop_id)
    )

    total_days = sum(
        int(coefficients[key])
        for key in [
            "days_initial",
            "days_development",
            "days_mid",
            "days_late",
        ]
    )

    if len(daily_et0_mm) != total_days:
        raise ValueError(
            f"Expected {total_days} daily ET0 values, "
            f"received {len(daily_et0_mm)}."
        )

    if any(
        value is None or value < 0
        for value in daily_et0_mm
    ):
        raise ValueError(
            "ET0 must contain nonnegative daily values."
        )

    daily_etc = []

    for day, et0 in enumerate(daily_et0_mm):
        kc = calculate_daily_kc(
            day,
            coefficients,
        )

        daily_etc.append(et0 * kc)

    total_etc = sum(daily_etc)

    return {
        "crop_id": crop_id,
        "growth_days": total_days,
        "crop_evapotranspiration_mm": round(
            total_etc, 2
        ),
        "daily_etc_mm": [
            round(value, 3)
            for value in daily_etc
        ],
        "coefficient_source": source_url,
        "method": "FAO-style Kc multiplied by ET0",
        "irrigation_requirement_mm": None,
        "note": (
            "Crop evapotranspiration is not the "
            "same as irrigation requirement. "
            "Effective rainfall, soil water and "
            "irrigation efficiency are not yet included."
        ),
    }
