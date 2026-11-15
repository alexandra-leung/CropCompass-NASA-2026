"""
M2 adapter — calls agricultureM2 service-layer functions in-process.

Calls
-----
* agricultureM2.rotation_engine.evaluate_rotation(crop_ids)
* agricultureM2.rotation_generator.generate_rotation_candidates(current, max)
* agricultureM2.suitability.check_crop_suitability(crop_id, temperature_c, soil_ph)

Water demand is reported as "not_implemented": the live agricultureM2 has no
water route, water_wallet.py cannot locate its coefficient file, and M1 does
not yet provide the daily ET0 series it requires. M4 will not substitute
hypothetical values.
"""

from __future__ import annotations

from intelligenceM4.providers import not_implemented, safe_call
from intelligenceM4.schemas import (
    M2GenerationResult,
    M2RotationResult,
    M2SuitabilityResult,
    ModuleStatus,
    ProviderResult,
)

ROTATION_CALL = "agricultureM2.rotation_engine.evaluate_rotation"
GENERATE_CALL = "agricultureM2.rotation_generator.generate_rotation_candidates"
SUITABILITY_CALL = "agricultureM2.suitability.check_crop_suitability"
WATER_CALL = "agricultureM2.water_wallet.calculate_crop_water_demand"

WATER_NOT_AVAILABLE = (
    "M2 water demand is not available in the unified backend: no water route "
    "is registered, water_wallet.py cannot locate crop_water_coefficients.csv, "
    "and M1 does not provide the daily ET0 series it requires."
)


def suitability_status(result: M2SuitabilityResult) -> ModuleStatus:
    # M2's own flag: "insufficient_data" means the call worked but data is missing.
    return "partial" if result.status == "insufficient_data" else "ok"


def evaluate_rotation(crop_ids: list[str]) -> ProviderResult:
    def _call() -> M2RotationResult:
        from agricultureM2.rotation_engine import evaluate_rotation as m2_evaluate

        return M2RotationResult.model_validate(m2_evaluate(list(crop_ids)))

    return safe_call("M2", ROTATION_CALL, _call)


def generate_alternatives(
    current_rotation: list[str],
    max_alternatives: int = 3,
) -> ProviderResult:
    def _call() -> M2GenerationResult:
        from agricultureM2.rotation_generator import generate_rotation_candidates

        return M2GenerationResult.model_validate(
            generate_rotation_candidates(
                current_rotation=list(current_rotation),
                max_alternatives=max_alternatives,
            )
        )

    return safe_call("M2", GENERATE_CALL, _call)


def check_suitability(
    crop_id: str,
    temperature_c: float | None = None,
    soil_ph: float | None = None,
) -> ProviderResult:
    def _call() -> M2SuitabilityResult:
        from agricultureM2.suitability import check_crop_suitability

        return M2SuitabilityResult.model_validate(
            check_crop_suitability(
                crop_id=crop_id,
                temperature_c=temperature_c,
                soil_ph=soil_ph,
            )
        )

    return safe_call("M2", SUITABILITY_CALL, _call, suitability_status)


def water_demand_implemented() -> bool:
    """Capability probe (no M2 code is executed). False until M2 ships a
    canonical water-demand service in the unified backend."""
    return False


def get_water_demand(crop_ids: list[str]) -> ProviderResult:
    return not_implemented("M2", WATER_CALL, WATER_NOT_AVAILABLE)
