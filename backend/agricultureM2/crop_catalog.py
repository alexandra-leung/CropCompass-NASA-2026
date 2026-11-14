
from functools import lru_cache
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]

CATALOG_PATH = (
    BASE_DIR / "data" / "reference" / "crop_catalog.csv"
)

REQUIRED_COLUMNS = [
    "crop_id",
    "crop_name",
    "family",
    "nitrogen_fixing",
    "source_url",
]


@lru_cache(maxsize=1)
def load_crop_catalog():
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(
            "Verified crop catalog not found."
        )

    df = pd.read_csv(
        CATALOG_PATH,
        dtype={
            "crop_id": "string",
            "crop_name": "string",
            "family": "string",
            "source_url": "string",
        },
    )

    missing = set(REQUIRED_COLUMNS) - set(
        df.columns
    )

    if missing:
        raise ValueError(
            f"Missing columns: {sorted(missing)}"
        )

    if df.empty:
        raise ValueError(
            "Crop catalog is empty. "
            "Import verified agricultural records."
        )

    if df[REQUIRED_COLUMNS].isna().any().any():
        raise ValueError(
            "Required crop data contains nulls."
        )

    if df["crop_id"].duplicated().any():
        raise ValueError(
            "Duplicate crop IDs detected."
        )

    values = (
        df["nitrogen_fixing"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df["nitrogen_fixing"] = values.map({
        "true": True,
        "false": False,
    })

    if df["nitrogen_fixing"].isna().any():
        raise ValueError(
            "Invalid nitrogen_fixing values."
        )

    if not df["source_url"].str.startswith(
        ("https://", "http://")
    ).all():
        raise ValueError(
            "Source URLs are missing or invalid."
        )

    return df


def get_crop(crop_id: str):
    df = load_crop_catalog()

    matches = df[df["crop_id"] == crop_id]

    if matches.empty:
        raise ValueError(
            f"Unknown crop: {crop_id}"
        )

    return matches.iloc[0].to_dict()
