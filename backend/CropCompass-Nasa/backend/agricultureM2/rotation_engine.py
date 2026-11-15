
from .crop_catalog import get_crop


def evaluate_rotation(crop_ids: list[str]):
    if len(crop_ids) < 2:
        raise ValueError(
            "A rotation requires at least two crops."
        )

    sequence = []
    repeated_families = []
    nitrogen_fixing_crops = []

    previous_family = None

    for season, crop_id in enumerate(
        crop_ids,
        start=1,
    ):
        crop = get_crop(crop_id)
        family = crop["family"]

        sequence.append({
            "season": season,
            "crop_id": crop_id,
            "crop_name": crop["crop_name"],
            "family": family,
            "source_url": crop["source_url"],
        })

        if previous_family == family:
            repeated_families.append({
                "season": season,
                "crop_family": family,
            })

        if crop["nitrogen_fixing"]:
            nitrogen_fixing_crops.append(crop_id)

        previous_family = family

    return {
        "rotation": crop_ids,
        "sequence": sequence,
        "crop_count": len(crop_ids),
        "repeated_families": repeated_families,
        "nitrogen_fixing_crops": (
            nitrogen_fixing_crops
        ),
        "has_adjacent_family_repetition": (
            len(repeated_families) > 0
        ),
        "soil_health_score": None,
        "score_status": "not_calibrated",
    }


def compare_rotations(rotations):
    if len(rotations) < 3:
        raise ValueError(
            "At least three rotations are required."
        )

    results = []

    for index, crops in enumerate(
        rotations,
        start=1,
    ):
        result = evaluate_rotation(crops)

        results.append({
            "rotation_id": f"rotation_{index}",
            "analysis": result,
        })

    return {
        "rotations_compared": len(results),
        "results": results,
        "ranking": None,
        "ranking_status": (
            "Awaiting suitability and "
            "water-budget evaluation"
        ),
    }
