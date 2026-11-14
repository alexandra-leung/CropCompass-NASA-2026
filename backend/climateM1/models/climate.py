
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class Location(BaseModel):
    id: str
    name: str
    district: str
    country: str = "Mauritius"


class Units(BaseModel):
    rainfall: str = "mm/year"
    temperature: str = "°C daily mean"
    dry_spells: str = Field(
        default="consecutive days with rainfall < 1 mm/day",
        alias="drySpells"
    )
    model_config = ConfigDict(populate_by_name=True)


class HistoryPoint(BaseModel):
    period: str
    label: str
    rainfall_mm: float = Field(alias="rainfallMm")
    temperature_c: float = Field(alias="temperatureC")
    dry_spell_days: int = Field(alias="drySpellDays")
    model_config = ConfigDict(populate_by_name=True)

class SeasonalPoint(HistoryPoint):
    completeness_pct: float = Field(alias="completenessPct")
    completeness_status: str = Field(alias="completenessStatus")
    model_config = ConfigDict(populate_by_name=True)


class ClimateTrend(BaseModel):
    direction: Literal["increasing", "decreasing", "no trend"]
    slope: float
    p_value: float = Field(alias="pValue")
    significant: bool
    observations: int

    model_config = ConfigDict(populate_by_name=True)

class ClimateMetrics(BaseModel):
    rainfall_shift: float = Field(alias="rainfallShift")
    temperature_trend: float = Field(alias="temperatureTrend")
    longest_dry_spell: int = Field(alias="longestDrySpell")
    data_completeness: float = Field(alias="dataCompleteness")
    model_config = ConfigDict(populate_by_name=True)
    annual_rainfall_trend: ClimateTrend = Field(alias="annualRainfallTrend")
    annual_temperature_trend: ClimateTrend = Field(alias="annualTemperatureTrend")



class Provenance(BaseModel):
    source: str
    product: str
    variable: str
    coordinates: Coordinates
    grid_resolution: str = Field(alias="gridResolution")
    date_range: str = Field(alias="dateRange")
    missing_data: bool = Field(alias="missingData")
    retrieved_at: str = Field(alias="retrievedAt")
    model: str | None = None
    caveat: str | None = None
    model_config = ConfigDict(populate_by_name=True)


class HistoryResponse(BaseModel):
    location: Location
    units: Units
    timeseries: list[HistoryPoint]
    seasonal: list[SeasonalPoint]
    metrics: ClimateMetrics
    provenance: list[Provenance]


class GridCell(BaseModel):
    latitude: float
    longitude: float


class ScenarioValue(BaseModel):
    year: int
    rainfall_mm: float = Field(alias="rainfallMm")
    temperature_c: float = Field(alias="temperatureC")
    grid_cell: GridCell = Field(alias="gridCell")
    sample_days: int = Field(alias="sampleDays")

    # New data-quality fields
    expected_days: int | None = Field(default=None, alias="expectedDays")
    missing_days: int | None = Field(default=None, alias="missingDays")
    completeness_pct: float | None = Field(default=None, alias="completenessPct")

    model_config = ConfigDict(populate_by_name=True)


class Scenario(BaseModel):
    id: Literal["ssp245", "ssp370"]
    label: str
    description: str
    model: str
    values: list[ScenarioValue]


class ModelResult(BaseModel):
    id: str
    variant: str
    status: Literal["success", "partial", "failed"] = "success"
    scenarios: list[Scenario]
    errors: list[str] = Field(default_factory=list)


class EnsembleStatistics(BaseModel):
    count: int
    mean: float
    median: float
    minimum: float
    maximum: float
    spread: float


class EnsembleValue(BaseModel):
    year: int
    rainfall_mm: EnsembleStatistics = Field(alias="rainfallMm")
    temperature_c: EnsembleStatistics = Field(alias="temperatureC")
    contributing_models: list[str] = Field(alias="contributingModels")


class EnsembleScenario(BaseModel):
    id: Literal["ssp245", "ssp370"]
    label: str
    description: str
    values: list[EnsembleValue]


class ScenarioResponse(BaseModel):
    location_id: str = Field(alias="locationId")
    baseline_period: str = Field(alias="baselinePeriod")

    # Existing field: preserves compatibility
    scenarios: list[Scenario]

    provenance: Provenance
    caveats: list[str]

    # New fields
    model_results: list[ModelResult] = Field(
        default_factory=list,
        alias="modelResults"
    )
    ensemble: list[EnsembleScenario] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)
