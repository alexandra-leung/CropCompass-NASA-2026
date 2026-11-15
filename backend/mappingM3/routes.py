"""M3 HTTP routes: farms, locations and field boundaries (prefix /api/farms)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from climateM1.services.locations import LOCATIONS
from mappingM3 import farm_profile as fp
from mappingM3.field_boundaries import (
    FieldBoundary, centroid, nearest_location, polygon_area_ha, square_boundary, suggest_boundary,
)
from mappingM3.soil_inputs import TEXTURE_LABELS

router = APIRouter(prefix="/api/farms", tags=["M3 - Farm Mapping"])


def _summary(p: fp.FarmProfile) -> dict[str, Any]:
    loc = LOCATIONS[p.location_id]
    report = fp.validate_profile(p)
    return {
        "farm_id": p.farm_id,
        "name": p.name,
        "location_id": p.location_id,
        "district": loc.district,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "field_area_ha": p.field_area_ha,
        "current_rotation": p.current_rotation,
        "soil_texture": TEXTURE_LABELS[p.soil.texture],
        "soil_confidence": p.soil.confidence(),
        "water_source": p.irrigation.water_source,
        "irrigation_budget_mm": p.irrigation.budget_mm_per_season,
        "irrigation_budget_m3": fp.irrigation_budget_m3(p),
        "missing_count": len(report["missing"]),
        "demo": p.demo,
    }


def _full(p: fp.FarmProfile) -> dict[str, Any]:
    return {**p.model_dump(mode="json"), "irrigation_budget_m3": fp.irrigation_budget_m3(p),
            "validation": fp.validate_profile(p)}


def _get(farm_id: str) -> fp.FarmProfile:
    try:
        return fp.load_farm(farm_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No farm '{farm_id}'. Pick one from GET /api/farms.")


@router.get("", summary="List farms (demo farms first)")
def list_farms() -> dict[str, Any]:
    farms = sorted(fp.list_farms(), key=lambda p: (not p.demo, p.name))
    return {"farms": [_summary(p) for p in farms]}


@router.get("/locations", summary="Registered climate locations the farmer can choose from")
def locations() -> dict[str, Any]:
    return {"locations": [
        {"location_id": L.id, "name": L.name, "district": L.district, "latitude": L.latitude, "longitude": L.longitude}
        for L in LOCATIONS.values()
    ], "note": "Locations come from M1. Climate data covers a regional grid around each point."}


@router.get("/nearest-location", summary="Closest registered location to a tapped point")
def nearest(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)) -> dict[str, Any]:
    return nearest_location(lat, lon)


class AreaRequest(BaseModel):
    geometry: dict[str, Any]


@router.post("/boundary/measure", summary="Area and centre of a drawn field outline")
def measure(req: AreaRequest) -> dict[str, Any]:
    try:
        b = FieldBoundary(geometry=req.geometry)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    lat, lon = centroid(b.geometry)
    return {"area_ha": polygon_area_ha(b.geometry), "centroid": {"latitude": lat, "longitude": lon},
            "nearest_location": nearest_location(lat, lon)}


@router.get("/boundary/suggest", summary="Automatic outline suggestion (falls back to manual)")
def suggest(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)) -> dict[str, Any]:
    return suggest_boundary(lat, lon)


@router.post("/validate", summary="Check a profile for missing or contradictory inputs")
def validate(profile: fp.FarmProfileIn) -> dict[str, Any]:
    return fp.validate_profile(profile)


@router.post("", status_code=201, summary="Create a farm")
def create(profile: fp.FarmProfileIn) -> dict[str, Any]:
    if profile.farm_id and profile.farm_id in {p.farm_id for p in fp.list_farms()}:
        raise HTTPException(status_code=409, detail=f"Farm '{profile.farm_id}' already exists; use PUT to update it.")
    if profile.boundary is None and profile.field_area_ha:
        loc = LOCATIONS[profile.location_id]
        profile.boundary = FieldBoundary(geometry=square_boundary(loc.latitude, loc.longitude, profile.field_area_ha),
                                         method="default_square", note="Placeholder outline: farmer should redraw.")
    return _full(fp.save_farm(profile))


@router.get("/{farm_id}", summary="Full farm profile with validation report")
def get_farm(farm_id: str) -> dict[str, Any]:
    return _full(_get(farm_id))


@router.get("/{farm_id}/context", summary="Farm context in the M4 contract")
def context(farm_id: str) -> dict[str, Any]:
    _get(farm_id)
    return fp.get_farm_profile(farm_id)


@router.put("/{farm_id}", summary="Replace a farm profile")
def update(farm_id: str, profile: fp.FarmProfileIn) -> dict[str, Any]:
    _get(farm_id)
    return _full(fp.save_farm(profile, farm_id=farm_id))


class PatchRequest(BaseModel):
    field_area_ha: float | None = None
    soil: dict[str, Any] | None = None
    irrigation: dict[str, Any] | None = None
    current_rotation: list[str] | None = None
    priorities: dict[str, float] | None = None
    constraints: list[str] | None = None
    boundary: dict[str, Any] | None = None
    prices_rs_per_kg: dict[str, float] | None = None


@router.patch("/{farm_id}", summary="Change some fields of a farm (e.g. the water slider)")
def patch(farm_id: str, req: PatchRequest) -> dict[str, Any]:
    current = _get(farm_id).model_dump(mode="json")
    for key, value in req.model_dump(exclude_unset=True).items():
        if isinstance(value, dict) and isinstance(current.get(key), dict) and key != "boundary":
            current[key] = {**current[key], **value}
        else:
            current[key] = value
    try:
        updated = fp.FarmProfileIn.model_validate(current)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _full(fp.save_farm(updated, farm_id=farm_id))


@router.put("/{farm_id}/boundary", summary="Save a drawn field outline")
def put_boundary(farm_id: str, boundary: FieldBoundary) -> dict[str, Any]:
    p = _get(farm_id)
    data = p.model_dump()
    data["boundary"] = boundary.model_dump()
    return _full(fp.save_farm(fp.FarmProfileIn.model_validate(data), farm_id=farm_id))


@router.delete("/{farm_id}", status_code=204, summary="Delete a farm you created (demo farms stay)")
def delete(farm_id: str) -> None:
    p = _get(farm_id)
    if p.demo:
        raise HTTPException(status_code=403, detail="Demo farms cannot be deleted.")
    fp.delete_farm(farm_id)
