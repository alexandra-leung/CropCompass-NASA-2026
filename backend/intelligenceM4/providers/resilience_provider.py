"""M4's resilience integration uses the separate M5 HTTP endpoints.

The endpoints need explicit coordinates, periods, rotations, and farmer water
constraints, so /analyze does not invoke them. Their unchanged responses can
be added to the /analyze bundle and submitted to /evidence.
"""

from __future__ import annotations

from intelligenceM4.providers import not_implemented
from intelligenceM4.schemas import ProviderResult

RESILIENCE_CALL = (
    "M5 separate /api/resilience/climate-twin and /api/resilience/stress-test calls"
)


def resilience_implemented() -> bool:
    """Whether /analyze automatically invokes M5 (it intentionally does not)."""
    return False


def get_resilience(
    location_id: str,
    scenario: str,
    year: int,
    rotation: list[str],
) -> ProviderResult:
    return not_implemented(
        "M5",
        RESILIENCE_CALL,
        "M5 is implemented as separate endpoints; run them with explicit "
        "coordinates, period, rotation, and farmer water budget, then submit "
        "their unchanged outputs through M4 /evidence.",
    )
