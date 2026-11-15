"""Mount once in the existing backend/app.py; no second server."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, FiniteFloat

from .climate_twin import find_climate_twins
from .rescue_mode import build_rescue_shortlist
from .scenario_engine import (
    DataUnavailable,
    PowerClient,
    SCENARIOS,
    get_farm_climate,
    m1_provider_registered,
)
from .stress_test import M2NotConnected, get_m2_evaluator, evaluate_scenarios

router = APIRouter(prefix="/api/resilience", tags=["Member 5 — Climate Resilience"])


class FarmLocation(BaseModel):
    latitude: float = Field(ge=-59.875, le=89.875, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    scenario: Literal["ssp245", "ssp370"] = "ssp245"
    start_year: int = Field(default=2041, ge=2027, le=2100)
    end_year: int = Field(default=2060, ge=2027, le=2100)


class TwinRequest(FarmLocation):
    top_k: int = Field(default=3, ge=1, le=10)


class CoordinatePayload(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class CandidateLocation(CoordinatePayload):
    id: str
    name: str


class MonthlyComparison(BaseModel):
    month: int = Field(ge=1, le=12)
    future_t_c: float = Field(allow_inf_nan=False)
    candidate_t_c: float = Field(allow_inf_nan=False)
    future_p_mm: float = Field(ge=0, allow_inf_nan=False)
    candidate_p_mm: float = Field(ge=0, allow_inf_nan=False)


class MonthlyClimatePayload(BaseModel):
    temperature_c: list[FiniteFloat] = Field(min_length=12, max_length=12)
    precipitation_mm: list[FiniteFloat] = Field(min_length=12, max_length=12)
    provenance: dict[str, Any]


class ClimateAnalog(BaseModel):
    location: CandidateLocation
    distance_index: float = Field(ge=0, allow_inf_nan=False)
    temperature_rmse_c: float = Field(ge=0, allow_inf_nan=False)
    precipitation_mae_mm_per_month: float = Field(ge=0, allow_inf_nan=False)
    temperature_distance_component: float = Field(ge=0, allow_inf_nan=False)
    precipitation_distance_component: float = Field(ge=0, allow_inf_nan=False)
    monthly_comparison: list[MonthlyComparison] = Field(min_length=12, max_length=12)
    candidate_provenance: dict[str, Any]


class ClimateTwinResponse(BaseModel):
    field: CoordinatePayload
    scenario: Literal["ssp245", "ssp370"]
    period: dict[str, int]
    historical: MonthlyClimatePayload
    projected_target: MonthlyClimatePayload
    analogs: list[ClimateAnalog] = Field(min_length=1, max_length=10)
    candidate_count: int = Field(ge=3)
    excluded_candidates: list[dict[str, str]]
    method: dict[str, Any]
    limitations: list[str]


class StressRequest(FarmLocation):
    rotation_request: dict
    baseline_water_budget_m3: FiniteFloat = Field(ge=0)
    irrigation_reduction_fraction: FiniteFloat | None = Field(default=None, gt=0, lt=1)


class RescueRequest(BaseModel):
    stress_output: dict


def validate_period(scenario: str, start_year: int, end_year: int):
    if scenario not in SCENARIOS:
        raise HTTPException(422, detail=f"Unsupported scenario {scenario}. Allowed: {sorted(SCENARIOS)}")
    if start_year > end_year:
        raise HTTPException(422, detail="start_year must be <= end_year")
    if end_year - start_year + 1 > 30:
        raise HTTPException(422, detail="Future period may not exceed 30 years")


@router.get("/health")
def health():
    try:
        get_m2_evaluator()
        connected = True
    except M2NotConnected:
        connected = False
    m1_connected = m1_provider_registered()
    return {"module": "resilienceM5",
            "status": "ready_for_climate_twin" if m1_connected else "m1_provider_unavailable",
            "m2_evaluator_connected": connected,
            "m2_scenario_feasibility_supported": False,
            "m2_evaluator": get_m2_evaluator().__name__ if connected else None,
            "m2_agricultural_feasibility_status": "unverified_model",
            "m2_water_estimation_supported": connected and get_m2_evaluator().__name__ == "evaluate_with_plan_engine",
            "m1_provider_connected": m1_connected,
            "offline_mode": PowerClient().offline}


@router.post("/climate-twin", response_model=ClimateTwinResponse)
async def climate_twin_endpoint(request: TwinRequest):
    validate_period(request.scenario, request.start_year, request.end_year)
    try:
        return await find_climate_twins(
            request.latitude,
            request.longitude,
            request.scenario,
            request.start_year,
            request.end_year,
            request.top_k,
            PowerClient(),
        )
    except DataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/stress-test")
async def stress_test_endpoint(request: StressRequest):
    validate_period(request.scenario, request.start_year, request.end_year)
    try:
        evaluator = get_m2_evaluator()   # Fail before downloading if the dependency is not wired.
    except M2NotConnected as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    try:
        from .m2_adapter import evaluate_with_plan_engine, validate_plan_request
        rotation_request = {**request.rotation_request, "latitude": request.latitude, "longitude": request.longitude}
        if evaluator is evaluate_with_plan_engine:
            validate_plan_request(rotation_request, request.baseline_water_budget_m3)
        historical, future = await get_farm_climate(
            request.latitude,
            request.longitude,
            request.scenario,
            request.start_year,
            request.end_year,
        )
        return evaluate_scenarios(rotation_request, historical, future,
                                  request.baseline_water_budget_m3,
                                  request.irrigation_reduction_fraction, evaluator)
    except DataUnavailable as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.post("/rescue-mode")
def rescue_mode_endpoint(request: RescueRequest):
    try:
        return build_rescue_shortlist(request.stress_output)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc
