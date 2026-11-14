"""
Blind-Spot Detector — deterministic rules for missing or incomplete evidence.

Phase 2 ships the first rule (M1 registry unreadable), because the Evidence
Passport depends on it. Phase 3 adds the remaining rules and the
POST /api/intelligence/blind-spots endpoint.

Blind spots describe what is missing. They never supply a replacement value.
"""

from __future__ import annotations

from intelligenceM4.providers import climate_provider
from intelligenceM4.schemas import AnalysisBundle, BlindSpot

REGISTRY_UNREADABLE = "M1_REGISTRY_UNREADABLE"


def registry_blind_spots(bundle: AnalysisBundle) -> list[BlindSpot]:
    """Identifiers that passed through unvalidated because M1's registry was unreadable."""
    unvalidated: list[str] = []

    scenarios = [bundle.selected_scenario]
    years = [bundle.selected_year]
    if bundle.resilience is not None:
        scenarios.append(bundle.resilience.scenario)
        years.append(bundle.resilience.year)

    if climate_provider.registered_scenario_ids() is None:
        unvalidated += [f"scenario:{s}" for s in dict.fromkeys(scenarios) if s is not None]
    if climate_provider.registered_projection_years() is None:
        unvalidated += [f"year:{y}" for y in dict.fromkeys(years) if y is not None]
    if climate_provider.registered_location_ids() is None:
        unvalidated.append(f"location:{bundle.farm.location_id}")

    if not unvalidated:
        return []

    return [BlindSpot(
        code=REGISTRY_UNREADABLE,
        category="module",
        severity="warning",
        message=(
            "The selected scenario/year could not be validated against M1's "
            "registry because the registry could not be read. The identifiers "
            "were passed through unchanged and may not match any M1 projection."
        ),
        affects=unvalidated,
        source_module="M1",
        team_action=(
            "M1: check that climateM1/config/model_registry.json and the "
            "location registry are present and readable."
        ),
    )]


def detect_blind_spots(bundle: AnalysisBundle) -> list[BlindSpot]:
    """All blind spots for a bundle. Phase 3 extends this rule list."""
    return [
        *registry_blind_spots(bundle),
    ]
