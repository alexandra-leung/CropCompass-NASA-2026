"""Thin adapter from M5 scenario inputs to the existing M2 callables."""
from __future__ import annotations

import math
from typing import Any

from agricultureM2.scoring import score_rotations
from agricultureM2.suitability import check_crop_suitability

from .scenario_engine import MonthlyClimate


def evaluate_m2_scenario(
    rotation_request: dict[str, Any],
    climate: MonthlyClimate,
    water_budget_m3: float | None,
) -> dict[str, Any]:
    """Run M2's rotation scorer and monthly temperature suitability checks.

    M2 currently does not accept precipitation or a water budget in either
    callable. Those dimensions are reported as unevaluated, never inferred.
    """
    if not isinstance(rotation_request, dict):
        raise ValueError("rotation_request must be an object")

    rotations = rotation_request.get("rotations")
    if not isinstance(rotations, list) or len(rotations) < 3:
        raise ValueError("rotation_request.rotations must contain at least three rotations")

    rotation_ids: list[str] = []
    crop_sequences: list[list[str]] = []
    for rotation in rotations:
        if not isinstance(rotation, dict):
            raise ValueError("Each rotation must contain an id and crops array")
        rotation_id = rotation.get("id")
        crops = rotation.get("crops")
        if not isinstance(rotation_id, str) or not rotation_id.strip():
            raise ValueError("Each rotation id must be a non-empty string")
        if rotation_id in rotation_ids:
            raise ValueError(f"Duplicate rotation id: {rotation_id}")
        if not isinstance(crops, list) or len(crops) < 2 or any(
            not isinstance(crop_id, str) or not crop_id.strip()
            for crop_id in crops
        ):
            raise ValueError(f"Rotation {rotation_id} must have at least two crop ids")
        rotation_ids.append(rotation_id)
        crop_sequences.append(crops)

    soil_ph = rotation_request.get("soil_ph")
    if soil_ph is not None and (
        isinstance(soil_ph, bool)
        or not isinstance(soil_ph, (int, float))
        or not math.isfinite(soil_ph)
    ):
        raise ValueError("rotation_request.soil_ph must be a finite number or null")

    if water_budget_m3 is None or not math.isfinite(water_budget_m3) or water_budget_m3 < 0:
        raise ValueError("A finite, nonnegative farmer water budget in m3 is required")

    scored = score_rotations(crop_sequences)
    m2_results = scored.get("results")
    if not isinstance(m2_results, list) or len(m2_results) != len(rotations):
        raise ValueError("M2 returned an inconsistent rotation result count")

    normalized = []
    for index, result in enumerate(m2_results):
        expected_m2_id = f"rotation_{index + 1}"
        if not isinstance(result, dict) or result.get("rotation_id") != expected_m2_id:
            raise ValueError("M2 returned rotation identities in an unexpected order")
        analysis = result.get("analysis")
        if not isinstance(analysis, dict) or analysis.get("rotation") != crop_sequences[index]:
            raise ValueError(f"M2 returned an inconsistent rotation for {rotation_ids[index]}")

        monthly_crop_suitability = []
        for season_index, crop_id in enumerate(crop_sequences[index], start=1):
            monthly_crop_suitability.append({
                "sequence_position": season_index,
                "crop_id": crop_id,
                "calendar_month_checks": [
                    {
                        "month": month,
                        **check_crop_suitability(
                            crop_id=crop_id,
                            temperature_c=temperature,
                            soil_ph=soil_ph,
                        ),
                    }
                    for month, temperature in enumerate(climate.temperature_c, start=1)
                ],
            })

        temperature_calculation_available = any(
            check["factor"] == "temperature_c"
            for crop in monthly_crop_suitability
            for month_check in crop["calendar_month_checks"]
            for check in month_check["checks"]
        )
        normalized.append({
            "id": rotation_ids[index],
            "feasible": None,
            "score": result.get("score"),
            "score_scale": result.get("score_scale"),
            "rank": result.get("rank"),
            "failed_constraints": [],
            "water_requirement_m3": None,
            "water_requirement_status": "not_calculated_by_m2",
            "details": {
                "m2_rotation_id": result["rotation_id"],
                "analysis": analysis,
                "monthly_crop_suitability": monthly_crop_suitability,
                "feasibility_status": "not_calculated_by_m2",
                "water_budget_m3": water_budget_m3,
                "water_budget_applied": False,
                "precipitation_applied": False,
                "temperature_calculation_available": temperature_calculation_available,
                "score_status": scored.get("score_status"),
            },
        })

    return {
        "rotations": normalized,
        "ranking": scored.get("ranking"),
        "score_scale": None,
        "score_status": scored.get("score_status"),
        "climate_inputs_used": {
            "temperature_values_supplied_to_m2": True,
            "temperature_suitability_calculation_available": any(
                rotation["details"]["temperature_calculation_available"]
                for rotation in normalized
            ),
            "precipitation_water_balance": False,
            "water_budget_feasibility": False,
        },
    }
