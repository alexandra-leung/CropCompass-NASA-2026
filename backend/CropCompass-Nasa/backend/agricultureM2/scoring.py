
from .rotation_engine import (
    compare_rotations,
)


def score_rotations(
    rotations: list[list[str]],
):
    result = compare_rotations(rotations)

    return {
        **result,
        "overall_score": None,
        "recommended_rotation": None,
        "score_status": (
            "Scientific scoring rules and "
            "farmer priorities not yet configured."
        ),
        "required_inputs": [
            "Validated crop suitability",
            "Crop water calculations",
            "Farmer priorities",
            "Soil and rotation constraints",
        ],
    }
