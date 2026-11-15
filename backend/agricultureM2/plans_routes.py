"""POST /api/agriculture/plans - ranked rotation plans for one farm (M2 engine, M1 climate, M3 farm)."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict, model_validator

from agricultureM2.plan_engine import build_plans

router = APIRouter(prefix="/api/agriculture", tags=["M2 - Agricultural Intelligence"])


class PlansRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    farm_id: str
    temperature_change_c: float = Field(default=0.0, ge=-2, le=5)
    rainfall_change_pct: float = Field(default=0.0, ge=-60, le=60)
    water_budget_mm: float | None = Field(default=None, ge=0, le=2000, description="Override the farm's budget (what-if)")
    max_alternatives: int = Field(default=3, ge=1, le=6)
    prices_rs_per_kg: dict[str, float] | None = Field(default=None, description="Farmer's own price per kg, by crop_id.")
    costs_rs_per_ha: dict[str, float] | None = Field(default=None, description="Farmer's growing cost per hectare per crop.")
    rotations: list[list[str]] | None = Field(default=None, description="Evaluate exactly these rotations (stress tests) instead of generating alternatives.")


    @model_validator(mode="after")
    def validate_inputs(self):
        from agricultureM2.plan_engine import validate_rotation, validate_number
        if self.rotations is not None:
            if not self.rotations:
                raise ValueError("rotations must not be empty")
            for rotation in self.rotations:
                validate_rotation(rotation)
        for mapping in (self.prices_rs_per_kg, self.costs_rs_per_ha):
            for key, value in (mapping or {}).items():
                validate_number(value, key, minimum=0)
        return self


async def _seasonal(location_id: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    try:
        from climateM1.api.climate import climate_history
        hist = await climate_history(location_id=location_id, start=date(2021, 1, 1), end=date(2025, 12, 31))
        data = hist if isinstance(hist, dict) else hist.model_dump()
        return data.get("seasonal"), None
    except Exception as exc:  # climate unavailable: plans still compared on rotation rules
        return None, f"{type(exc).__name__}: {exc}"


def _lat(location_id: str) -> float | None:
    from climateM1.services.locations import LOCATIONS
    loc = LOCATIONS.get(location_id)
    return loc.latitude if loc else None


def _months(farm: Any) -> list[list[int]] | None:
    """The farmer's own planting windows, in the order of the current rotation."""
    cal = getattr(farm, "rotation_calendar", None)
    if cal is None:
        return None
    from agricultureM2.plan_engine import calendar_months
    return calendar_months(farm.current_rotation, [w.model_dump() for w in cal])


@router.post("/plans", summary="Ranked rotation plans for a farm (water need, suitability, score)")
async def plans(req: PlansRequest) -> dict[str, Any]:
    from mappingM3.farm_profile import load_farm
    try:
        farm = load_farm(req.farm_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No farm '{req.farm_id}'")
    if not farm.current_rotation:
        raise HTTPException(status_code=422, detail="This farm has no current rotation yet.")
    from agricultureM2.plan_engine import validate_rotation
    try:
        validate_rotation(farm.current_rotation)
        months = _months(farm)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    seasonal, err = await _seasonal(farm.location_id)
    budget = req.water_budget_mm if req.water_budget_mm is not None else farm.irrigation.budget_mm_per_season
    try:
        out = build_plans(current=farm.current_rotation, seasonal=seasonal, budget_mm=budget, area_ha=farm.field_area_ha,
                      soil_ph=farm.soil.ph, priorities=farm.priorities.model_dump(),
                      d_temp=req.temperature_change_c, d_rain_pct=req.rainfall_change_pct, max_alternatives=req.max_alternatives,
                      fixed_rotations=req.rotations,
                      prices=req.prices_rs_per_kg or getattr(farm, 'prices_rs_per_kg', None),
                      costs=req.costs_rs_per_ha or getattr(farm, 'costs_rs_per_ha', None),
                      latitude=_lat(farm.location_id), current_months=months)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    out.update({"farm_id": farm.farm_id, "location_id": farm.location_id, "climate_error": err})
    return out
