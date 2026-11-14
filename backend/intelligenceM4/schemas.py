"""
M4 — shared schemas for the Evidence Passport, Blind-Spot Detector,
Grounded Assistant and Orchestrator.

Design rules
------------
* M1 payloads are validated with M1's own Pydantic models (imported, never
  copied or modified).
* M2 has no response models, so M4 defines read-only mirrors that tolerate
  extra fields (extra="allow") — if M2 adds fields, nothing breaks.
* M3 / M5 have no implementation yet; FarmContext and ResilienceInput are
  PROPOSED contracts to agree with those members.
* Scenario ids, projection years and location ids are validated against M1's
  live registry (via providers.climate_provider), not hard-coded, so new M1
  scenarios/years/locations are accepted automatically.
* Any non-None evidence value attributed to an upstream module (M1/M2/M3/M5)
  MUST carry provenance.field_path pointing at the exact upstream field.
* Evidence claims contain no digits except exact module ids (M1–M5) and
  M1-registered scenario ids/labels and projection years. Measured or
  computed numbers live only in value + unit.
* There is deliberately no overall "quality score" or percentage anywhere in
  M4 output: completeness is expressed as statuses and blind spots.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from climateM1.models.climate import HistoryResponse, ScenarioResponse

# ---------------------------------------------------------------------------
# Shared literals
# ---------------------------------------------------------------------------

SourceModule = Literal["M1", "M2", "M3", "M5", "M4", "farmer"]
UpstreamModule = Literal["M1", "M2", "M3", "M5"]
UPSTREAM_MODULES: frozenset[str] = frozenset({"M1", "M2", "M3", "M5"})

EvidenceStatus = Literal[
    "supported",      # backed by an upstream computed/sourced value
    "partial",        # some backing, but incomplete (e.g. not all models)
    "unsupported",    # upstream data contradicts or fails the check
    "not_evaluated",  # upstream explicitly did not evaluate ("not_calibrated")
    "unavailable",    # upstream module/data missing entirely
]

Severity = Literal["critical", "warning", "info"]

ModuleStatus = Literal[
    "ok",               # call succeeded, data complete per upstream flags
    "partial",          # call succeeded but upstream flags incompleteness
    "unavailable",      # call raised / timed out / failed validation
    "not_implemented",  # upstream module has no usable function yet
]

RecommendationStatus = Literal[
    "supported",
    "requires_further_validation",
    "insufficient_evidence",
]


# ---------------------------------------------------------------------------
# Registry-backed identifiers (validated against M1, not hard-coded)
# ---------------------------------------------------------------------------
# If M1's registry cannot be read, the identifier passes through unvalidated:
# it is only an identifier (no data is invented), and the M1 provider will
# report "unavailable", which surfaces as a blind spot downstream.

def _check_scenario(value: str) -> str:
    from intelligenceM4.providers import climate_provider

    allowed = climate_provider.registered_scenario_ids()
    if allowed is not None and value not in allowed:
        raise ValueError(
            f"Unknown climate scenario '{value}'. "
            f"M1 registry provides: {sorted(allowed)}"
        )
    return value


def _check_year(value: int) -> int:
    from intelligenceM4.providers import climate_provider

    allowed = climate_provider.registered_projection_years()
    if allowed is not None and value not in allowed:
        raise ValueError(
            f"Unknown projection year {value}. "
            f"M1 registry provides: {sorted(allowed)}"
        )
    return value


def _check_location(value: str) -> str:
    from intelligenceM4.providers import climate_provider

    allowed = climate_provider.registered_location_ids()
    if allowed is not None and value not in allowed:
        raise ValueError(
            f"Unknown location '{value}'. "
            f"M1 registered locations: {sorted(allowed)}"
        )
    return value


ScenarioId = Annotated[str, AfterValidator(_check_scenario)]


# ---------------------------------------------------------------------------
# Claim digit allowlist
# ---------------------------------------------------------------------------
# Claims may contain digits only inside these exact identifiers:
#   * module ids M1–M5
#   * scenario ids and labels from M1's registry ("ssp370", "SSP3-7.0")
#   * projection years from M1's registry ("2050")
# Any other digit (e.g. a measured or projected value) is rejected.
# If M1's registry is unreadable, only module ids remain allowed.

MODULE_IDS: tuple[str, ...] = ("M1", "M2", "M3", "M4", "M5")


def allowed_claim_tokens() -> set[str]:
    from intelligenceM4.providers import climate_provider

    tokens = set(MODULE_IDS)
    scenarios = climate_provider.registered_scenarios()
    if scenarios:
        tokens |= set(scenarios) | set(scenarios.values())
    years = climate_provider.registered_projection_years()
    if years:
        tokens |= {str(year) for year in years}
    return tokens


def claim_has_disallowed_digits(text: str, tokens: set[str] | None = None) -> bool:
    remaining = text
    # Longest first so "SSP3-7.0" is removed before any shorter token inside it.
    for token in sorted(tokens if tokens is not None else allowed_claim_tokens(),
                        key=len, reverse=True):
        pattern = rf"(?<![0-9A-Za-z]){re.escape(token)}(?![0-9A-Za-z])"
        remaining = re.sub(pattern, " ", remaining)
    return any(ch.isdigit() for ch in remaining)
ProjectionYear = Annotated[int, AfterValidator(_check_year)]
LocationId = Annotated[str, AfterValidator(_check_location)]


# ---------------------------------------------------------------------------
# Provider wrapper — every provider returns this, never raises
# ---------------------------------------------------------------------------

T = TypeVar("T")


class ProviderResult(BaseModel, Generic[T]):
    module: UpstreamModule
    status: ModuleStatus
    data: T | None = None
    error: str | None = None   # exception type + message when not "ok"/"partial"
    called: str                # e.g. "climateM1.services.projections.fetch_scenarios"

    @property
    def usable(self) -> bool:
        return self.status in ("ok", "partial") and self.data is not None


# ---------------------------------------------------------------------------
# M2 read-only mirrors (fields taken from real M2 output)
# ---------------------------------------------------------------------------

class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class M2SequenceItem(_Loose):
    season: int
    crop_id: str
    crop_name: str
    family: str
    source_url: str


class M2RepeatedFamily(_Loose):
    season: int
    crop_family: str


class M2RotationResult(_Loose):
    """Mirror of agricultureM2.rotation_engine.evaluate_rotation()."""
    rotation: list[str]
    sequence: list[M2SequenceItem]
    crop_count: int
    repeated_families: list[M2RepeatedFamily]
    nitrogen_fixing_crops: list[str]
    has_adjacent_family_repetition: bool
    soil_health_score: float | None = None   # currently always None in M2
    score_status: str                         # currently "not_calibrated"


class M2SuitabilityCheck(_Loose):
    factor: str
    # Optional: one-sided reference ranges and missing actuals must not fail
    # validation. A None here is reported, never filled in.
    actual: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    passed: bool


class M2SuitabilityResult(_Loose):
    """Mirror of agricultureM2.suitability.check_crop_suitability()."""
    crop_id: str
    status: Literal[
        "within_checked_ranges",
        "outside_reference_range",
        "insufficient_data",
    ]
    checks: list[M2SuitabilityCheck]
    missing: list[str]
    source_url: str
    note: str | None = None


class M2GenerationResult(_Loose):
    """Mirror of agricultureM2.rotation_generator.generate_rotation_candidates()."""
    current_rotation: M2RotationResult
    alternative_rotations: list[M2RotationResult]
    alternatives_found: int
    selection_method: str
    agronomic_feasibility: str   # currently "not_evaluated"
    ranking_status: str          # currently "not_calibrated"
    note: str | None = None


# ---------------------------------------------------------------------------
# PROPOSED contracts for M3 and M5 (to be agreed with them)
# ---------------------------------------------------------------------------

class FarmContext(BaseModel):
    """Farm context — proposed M3 contract. Farmer may also supply it directly.

    None means "not provided" and becomes a blind spot. Never defaulted.
    """
    farm_id: str | None = None
    location_id: LocationId
    soil_ph: float | None = Field(default=None, ge=0, le=14)
    field_area_ha: float | None = Field(default=None, gt=0)
    irrigation_budget_m3: float | None = Field(default=None, ge=0)
    current_rotation: list[str] | None = None
    source: Literal["M3", "farmer"] = "farmer"


class ResilienceInput(_Loose):
    """Proposed M5 contract — kept loose until M5 publishes real output."""
    scenario: ScenarioId | None = None
    year: ProjectionYear | None = None
    stress_tests: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# The analysis bundle M4 reasons over
# ---------------------------------------------------------------------------

class ClimateInput(BaseModel):
    scenarios: ScenarioResponse | None = None   # M1's own model
    history: HistoryResponse | None = None      # M1's own model


class AgricultureInput(BaseModel):
    rotation: M2RotationResult | None = None
    alternatives: M2GenerationResult | None = None
    suitability: list[M2SuitabilityResult] = Field(default_factory=list)
    # Held raw: no canonical M2 water function exists yet. M4 only cites
    # values from here with a field_path, and flags hypothetical assumptions.
    water: dict[str, Any] | None = None


class AnalysisBundle(BaseModel):
    analysis_id: str
    farm: FarmContext
    selected_scenario: ScenarioId | None = None
    selected_year: ProjectionYear | None = None
    climate: ClimateInput = Field(default_factory=ClimateInput)
    agriculture: AgricultureInput = Field(default_factory=AgricultureInput)
    resilience: ResilienceInput | None = None


# ---------------------------------------------------------------------------
# M4 outputs
# ---------------------------------------------------------------------------

class Provenance(BaseModel):
    source_module: SourceModule
    field_path: str | None = None       # e.g. "agriculture.rotation.nitrogen_fixing_crops[0]"
    dataset: str | None = None          # copied from M1 provenance.source
    product: str | None = None          # copied from M1 provenance.product
    source_url: str | None = None       # e.g. FAO-56 URL from M2 catalog
    grid_resolution: str | None = None  # copied from M1 provenance.gridResolution
    retrieved_at: str | None = None     # copied from M1 provenance.retrievedAt
    method: str | None = None           # e.g. "Sourced crop trait lookup"


class EvidenceRecord(BaseModel):
    id: str                              # stable id, e.g. "ev-nfix-cowpea"
    claim: str                           # template text, never contains digits
    subject: str | None = None           # crop id, "rotation", "climate:ssp370:2050"
    value: str | float | int | bool | list[str] | None = None
    unit: str | None = None
    status: EvidenceStatus
    provenance: Provenance
    qualifications: list[str] = Field(default_factory=list)

    @field_validator("claim")
    @classmethod
    def claim_has_no_numbers(cls, claim: str) -> str:
        if claim_has_disallowed_digits(claim):
            raise ValueError(
                "Evidence claims must not contain numbers other than module ids "
                "and M1-registered scenario ids/labels/years; "
                "put numbers in `value` and `unit` instead"
            )
        return claim

    @model_validator(mode="after")
    def upstream_values_must_be_traceable(self) -> "EvidenceRecord":
        if (
            self.value is not None
            and self.provenance.source_module in UPSTREAM_MODULES
            and not self.provenance.field_path
        ):
            raise ValueError(
                f"Evidence value attributed to {self.provenance.source_module} "
                "requires provenance.field_path (M4 must not emit untraceable values)"
            )
        return self


class RuleApplied(BaseModel):
    rule_id: str              # e.g. "R-NFIX-01"
    description: str
    inputs: list[str]         # field paths read by the rule
    outcome: str


class Limitation(BaseModel):
    text: str                 # upstream caveats copied verbatim
    source_module: SourceModule


class BlindSpot(BaseModel):
    code: str                 # e.g. "SOIL_PH_MISSING", "CLIMATE_MODEL_PARTIAL"
    category: Literal["soil", "water", "climate", "crop_reference", "resolution", "module"]
    severity: Severity
    message: str
    affects: list[str] = Field(default_factory=list)   # evidence ids / crop ids
    source_module: SourceModule
    farmer_action: str | None = None   # what the farmer can provide
    team_action: str | None = None     # which module must supply it


class EvidencePassport(BaseModel):
    analysis_id: str
    location_id: str
    rotation: list[str]
    evidence: list[EvidenceRecord]
    rules_applied: list[RuleApplied]
    limitations: list[Limitation]
    blind_spots: list[BlindSpot]
    recommendation_status: RecommendationStatus
    generated_at: str


class BlindSpotReport(BaseModel):
    analysis_id: str
    blind_spots: list[BlindSpot]
    module_status: dict[UpstreamModule, ModuleStatus]


# ---------------------------------------------------------------------------
# Endpoint request / response models
# ---------------------------------------------------------------------------

class AssistantRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    analysis: AnalysisBundle
    use_llm: bool = False


class AssistantResponse(BaseModel):
    answer: str
    mode: Literal["template", "llm", "refused"]
    cited_evidence: list[str] = Field(default_factory=list)   # EvidenceRecord ids
    blind_spots: list[str] = Field(default_factory=list)      # BlindSpot codes
    limitations: list[str] = Field(default_factory=list)
    refusal_reason: str | None = None


class AnalyzeRequest(BaseModel):
    farm: FarmContext
    scenario: ScenarioId = "ssp370"
    year: ProjectionYear = 2050
    max_alternatives: int = Field(default=3, ge=1, le=20)


class ModuleReport(BaseModel):
    status: ModuleStatus
    called: str | None = None
    error: str | None = None


class AnalyzeResponse(BaseModel):
    analysis_id: str
    modules: dict[UpstreamModule, ModuleReport]
    bundle: AnalysisBundle
    passport: EvidencePassport
    blind_spot_report: BlindSpotReport
