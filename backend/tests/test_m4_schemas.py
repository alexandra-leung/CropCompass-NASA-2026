"""Phase 1 — M4 schema contracts, validated against REAL M1/M2 fixtures.

Run from backend/:  python -m pytest tests/test_m4_*.py -v
"""

import pytest
from pydantic import ValidationError

from intelligenceM4.fixtures import load_fixture, load_manifest
from intelligenceM4.providers import climate_provider
from intelligenceM4.schemas import (
    AnalysisBundle,
    AnalyzeRequest,
    ClimateInput,
    EvidenceRecord,
    FarmContext,
    HistoryResponse,
    M2GenerationResult,
    M2RotationResult,
    M2SuitabilityCheck,
    M2SuitabilityResult,
    Provenance,
    ResilienceInput,
    ScenarioResponse,
)

SCENARIOS = "m1_scenarios__pamplemousses-04.json"
HISTORY = "m1_history__pamplemousses-04.json"


# ---------------------------------------------------------------------------
# Real fixtures parse into the M4 contracts
# ---------------------------------------------------------------------------

def test_every_fixture_is_listed_in_manifest_with_its_source_call():
    manifest = load_manifest()
    assert SCENARIOS in manifest and HISTORY in manifest
    for name, meta in manifest.items():
        assert meta["called"].startswith(
            ("climateM1.services.", "agricultureM2.", "POST /api/intelligence/"))
        assert meta["provider_status"] in ("ok", "partial")
        load_fixture(name)  # file exists and is valid JSON


def test_real_m1_fixtures_validate_with_m1_models():
    scenarios = ScenarioResponse.model_validate(load_fixture(SCENARIOS))
    history = HistoryResponse.model_validate(load_fixture(HISTORY))
    assert scenarios.provenance.source == "NASA NEX-GDDP-CMIP6"
    assert history.provenance[0].source == "NASA POWER"


def test_real_m2_fixtures_validate_with_m4_mirrors():
    rotation = M2RotationResult.model_validate(
        load_fixture("m2_rotation__maize-cowpea-cabbage.json"))
    assert rotation.nitrogen_fixing_crops == ["cowpea"]
    assert rotation.soil_health_score is None  # M2 has not calibrated it

    generated = M2GenerationResult.model_validate(
        load_fixture("m2_generate__maize-maize-maize__max3.json"))
    assert generated.agronomic_feasibility == "not_evaluated"

    suit = M2SuitabilityResult.model_validate(
        load_fixture("m2_suitability__cowpea__no-inputs.json"))
    assert suit.status == "insufficient_data"
    assert set(suit.missing) == {"temperature_c", "soil_ph"}


def test_m2_mirror_keeps_unknown_upstream_fields():
    raw = load_fixture("m2_rotation__maize-cowpea-cabbage.json")
    raw["new_m2_field"] = "kept"
    assert M2RotationResult.model_validate(raw).model_dump()["new_m2_field"] == "kept"


def test_full_bundle_builds_from_real_fixtures():
    bundle = AnalysisBundle(
        analysis_id="test-001",
        farm=FarmContext(location_id="pamplemousses-04"),
        selected_scenario="ssp370",
        selected_year=2050,
        climate=ClimateInput(
            scenarios=load_fixture(SCENARIOS), history=load_fixture(HISTORY)),
        agriculture={
            "rotation": load_fixture("m2_rotation__maize-cowpea-cabbage.json"),
            "suitability": [load_fixture("m2_suitability__cowpea__no-inputs.json")],
        },
    )
    assert bundle.farm.soil_ph is None  # missing stays missing, never defaulted
    assert bundle.agriculture.water is None


# ---------------------------------------------------------------------------
# Change 1 — suitability checks tolerate one-sided ranges / missing actuals
# ---------------------------------------------------------------------------

def test_suitability_check_allows_none_bounds_and_actual():
    check = M2SuitabilityCheck(factor="soil_ph", passed=False)
    assert check.actual is None and check.minimum is None and check.maximum is None

    one_sided = M2SuitabilityCheck(factor="temperature_c", actual=31.0, maximum=35.0, passed=True)
    assert one_sided.minimum is None


# ---------------------------------------------------------------------------
# Change 2 — upstream values require a field_path (any type)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", ["M1", "M2", "M3", "M5"])
@pytest.mark.parametrize("value", ["cowpea", ["cowpea"], True, 1725.62, 5])
def test_upstream_value_without_field_path_is_rejected(module, value):
    with pytest.raises(ValidationError, match="field_path"):
        EvidenceRecord(
            id="ev-x", claim="A traceable claim", value=value, status="supported",
            provenance=Provenance(source_module=module),
        )


@pytest.mark.parametrize("module", ["M4", "farmer"])
def test_m4_and_farmer_values_are_exempt_from_field_path(module):
    record = EvidenceRecord(
        id="ev-x", claim="Farmer supplied soil acidity", value=6.5, unit="pH",
        status="supported", provenance=Provenance(source_module=module),
    )
    assert record.value == 6.5


def test_upstream_record_without_value_needs_no_field_path():
    record = EvidenceRecord(
        id="ev-x", claim="Soil health score has not been calibrated",
        status="not_evaluated", provenance=Provenance(source_module="M2"),
    )
    assert record.value is None


def test_upstream_value_with_field_path_is_accepted():
    record = EvidenceRecord(
        id="ev-nfix-cowpea", claim="The rotation contains a nitrogen-fixing crop",
        subject="cowpea", value="cowpea", status="supported",
        provenance=Provenance(
            source_module="M2",
            field_path="agriculture.rotation.nitrogen_fixing_crops[0]",
            method="Sourced crop trait lookup",
        ),
    )
    assert record.provenance.field_path.endswith("[0]")


# ---------------------------------------------------------------------------
# Change 3 — claims never contain numbers; numbers go in value + unit
# ---------------------------------------------------------------------------

def _real_ensemble_value():
    scenarios = ScenarioResponse.model_validate(load_fixture(SCENARIOS))
    ensemble = next(e for e in scenarios.ensemble if e.id == "ssp370")
    point = next(v for v in ensemble.values if v.year == 2050)
    return point.rainfall_mm.mean, "climate.scenarios.ensemble[1].values[2].rainfallMm.mean"


def test_claim_with_digits_from_upstream_values_is_rejected():
    mean, path = _real_ensemble_value()
    provenance = Provenance(source_module="M1", field_path=path)

    for claim in (
        f"Projected rainfall is {mean} mm per year",
        f"Projected rainfall for 2050 under SSP3-7.0 is {mean} mm",
        f"Rainfall mean {int(mean)}",                 # integer part of a measured value
        "Projected rainfall for 2045 is available",   # year not in M1 registry
        "Results from M12 are available",             # not an exact module id
        "Projections for the 2050s are available",    # year glued to other text
    ):
        with pytest.raises(ValidationError, match="must not contain numbers"):
            EvidenceRecord(id="ev-rain", claim=claim, value=mean, unit="mm/year",
                           status="supported", provenance=provenance)


@pytest.mark.parametrize("claim", [
    "Projections for 2050 under SSP3-7.0 are available",
    "Projections for 2030 under ssp245 are available",
    "Soil health score has not been calibrated by M2",
    "M1 and M5 results were combined.",
])
def test_claim_allowlist_permits_module_and_registry_identifiers(claim):
    record = EvidenceRecord(id="ev-ok", claim=claim, status="supported",
                            provenance=Provenance(source_module="M4"))
    assert record.claim == claim


def test_registry_identifiers_blocked_when_registry_unreadable(monkeypatch):
    monkeypatch.setattr(climate_provider, "registered_scenarios", lambda: None)
    monkeypatch.setattr(climate_provider, "registered_projection_years", lambda: None)
    with pytest.raises(ValidationError, match="must not contain numbers"):
        EvidenceRecord(id="ev-x", claim="Projections for 2050 under SSP3-7.0 are available",
                       status="supported", provenance=Provenance(source_module="M4"))
    # Module ids stay allowed.
    EvidenceRecord(id="ev-y", claim="Calibrated by M2", status="not_evaluated",
                   provenance=Provenance(source_module="M4"))


def test_number_in_value_and_unit_is_accepted():
    mean, path = _real_ensemble_value()
    record = EvidenceRecord(
        id="ev-rain", claim="Projected annual rainfall ensemble mean",
        subject="climate:ssp370:2050", value=mean, unit="mm/year", status="supported",
        provenance=Provenance(source_module="M1", field_path=path,
                              dataset="NASA NEX-GDDP-CMIP6"),
    )
    assert record.value == mean


# ---------------------------------------------------------------------------
# Change 4 — scenarios / years / locations come from M1's registry
# ---------------------------------------------------------------------------

def test_every_m1_registry_scenario_and_year_is_accepted():
    scenarios = climate_provider.registered_scenario_ids()
    years = climate_provider.registered_projection_years()
    assert scenarios and years
    for scenario in scenarios:
        for year in years:
            request = AnalyzeRequest(
                farm=FarmContext(location_id="pamplemousses-04"),
                scenario=scenario, year=year,
            )
            assert request.scenario == scenario


def test_unknown_scenario_year_and_location_are_rejected():
    farm = FarmContext(location_id="pamplemousses-04")
    with pytest.raises(ValidationError, match="Unknown climate scenario"):
        AnalyzeRequest(farm=farm, scenario="ssp999")
    with pytest.raises(ValidationError, match="Unknown projection year"):
        AnalyzeRequest(farm=farm, year=2045)
    with pytest.raises(ValidationError, match="Unknown location"):
        FarmContext(location_id="not-a-farm")
    with pytest.raises(ValidationError, match="Unknown climate scenario"):
        ResilienceInput(scenario="ssp999")


def test_new_m1_scenario_is_accepted_without_m4_changes(monkeypatch):
    monkeypatch.setattr(climate_provider, "registered_scenario_ids",
                        lambda: {"ssp245", "ssp370", "ssp585"})
    monkeypatch.setattr(climate_provider, "registered_projection_years",
                        lambda: {2030, 2040, 2050, 2070})
    request = AnalyzeRequest(farm=FarmContext(location_id="pamplemousses-04"),
                             scenario="ssp585", year=2070)
    assert (request.scenario, request.year) == ("ssp585", 2070)


def test_unreadable_registry_passes_identifier_through(monkeypatch):
    monkeypatch.setattr(climate_provider, "registered_scenario_ids", lambda: None)
    monkeypatch.setattr(climate_provider, "registered_location_ids", lambda: None)
    request = AnalyzeRequest(farm=FarmContext(location_id="new-site"), scenario="ssp126")
    assert request.scenario == "ssp126"
