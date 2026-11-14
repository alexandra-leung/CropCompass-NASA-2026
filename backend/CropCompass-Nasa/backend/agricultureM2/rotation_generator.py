
from itertools import product

from .crop_catalog import load_crop_catalog
from .rotation_engine import evaluate_rotation


def generate_rotation_candidates(
    current_rotation: list[str],
    max_alternatives: int = 5,
):
    if not 1 <= max_alternatives <= 20:
        raise ValueError(
            "max_alternatives must be between 1 and 20"
        )

    # Validate the farmer's existing rotation
    current = evaluate_rotation(current_rotation)

    catalog = load_crop_catalog()
    crop_ids = catalog["crop_id"].tolist()

    candidates = []
    length = len(current_rotation)

    for sequence in product(
        crop_ids,
        repeat=length,
    ):
        sequence = list(sequence)

        if sequence == current_rotation:
            continue

        result = evaluate_rotation(sequence)

        # Preliminary diversification filter only.
        # This does not establish agronomic feasibility.
        if result["has_adjacent_family_repetition"]:
            continue

        candidates.append(result)

        if len(candidates) >= max_alternatives:
            break

    return {
        "current_rotation": current,
        "alternative_rotations": candidates,
        "alternatives_found": len(candidates),
        "selection_method": (
            "Catalog-order enumeration with "
            "adjacent-family diversification filter"
        ),
        "agronomic_feasibility": "not_evaluated",
        "ranking_status": "not_calibrated",
        "note": (
            "Candidates are exploratory sequences. "
            "Planting season, soil suitability, "
            "water and climate constraints "
            "must be checked before recommendation."
        ),
    }
