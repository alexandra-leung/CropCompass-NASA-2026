import json
from functools import lru_cache
from typing import Any

from climateM1.core.config import MODEL_REGISTRY_PATH


@lru_cache(maxsize=1)
def load_model_registry() -> dict[str, Any]:
    if not MODEL_REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"Model registry not found: {MODEL_REGISTRY_PATH}"
        )

    with MODEL_REGISTRY_PATH.open("r", encoding="utf-8") as file:
        registry = json.load(file)

    required = [
        "source",
        "scenarios",
        "projection_years",
        "variables",
        "models",
    ]

    for key in required:
        if key not in registry:
            raise ValueError(
                f"Model registry is missing required field: {key}"
            )

    if not registry["models"]:
        raise ValueError("No climate models are configured")

    return registry


def get_enabled_models() -> list[dict[str, Any]]:
    registry = load_model_registry()

    return [
        model
        for model in registry["models"]
        if model.get("enabled", True)
    ]


def get_scenarios() -> list[dict[str, Any]]:
    return load_model_registry()["scenarios"]


def get_projection_years() -> list[int]:
    return load_model_registry()["projection_years"]