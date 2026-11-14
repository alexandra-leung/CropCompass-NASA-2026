"""
M5 adapter — climate resilience / stress tests.

M5 has no implementation yet. This adapter looks for the PROPOSED service
function `resilienceM5.stress_test.run_stress_test(location_id, scenario,
year, rotation) -> dict` (see intelligenceM4/API_CONTRACT.md). Until it
exists, the result is "not_implemented" and M4 reports the missing resilience
evidence as a blind spot. M4 never fabricates resilience figures.
"""

from __future__ import annotations

from intelligenceM4.providers import not_implemented, safe_call
from intelligenceM4.schemas import ProviderResult, ResilienceInput

RESILIENCE_CALL = "resilienceM5.stress_test.run_stress_test"


def get_resilience(
    location_id: str,
    scenario: str,
    year: int,
    rotation: list[str],
) -> ProviderResult:
    try:
        from resilienceM5 import stress_test
        m5_run = getattr(stress_test, "run_stress_test", None)
    except Exception:
        m5_run = None

    if m5_run is None:
        return not_implemented(
            "M5", RESILIENCE_CALL,
            "M5 has not published run_stress_test yet (contract pending).",
        )

    return safe_call(
        "M5", RESILIENCE_CALL,
        lambda: ResilienceInput.model_validate(
            m5_run(location_id, scenario, year, list(rotation))
        ),
    )
