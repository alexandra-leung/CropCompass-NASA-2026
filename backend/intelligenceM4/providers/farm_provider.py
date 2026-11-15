"""M3 farm-context adapter. Existing profiles retain demo and input provenance;
unknown IDs degrade to unavailable and callers may supply their own context.
"""

from __future__ import annotations

from intelligenceM4.providers import not_implemented, safe_call
from intelligenceM4.schemas import FarmContext, ProviderResult

FARM_CALL = "mappingM3.farm_profile.get_farm_profile"


def _m3_function():
    try:
        from mappingM3 import farm_profile
        return getattr(farm_profile, "get_farm_profile", None)
    except Exception:
        return None


def farm_profile_implemented() -> bool:
    """Capability probe: does M3 expose the agreed function? (Does not call it.)"""
    return _m3_function() is not None


def get_farm_context(farm_id: str) -> ProviderResult:
    m3_get = _m3_function()
    if m3_get is None:
        return not_implemented(
            "M3", FARM_CALL,
            "M3 has not published get_farm_profile yet (contract pending).",
        )

    return safe_call("M3", FARM_CALL, lambda: FarmContext.model_validate(m3_get(farm_id)))
