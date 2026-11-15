"""M3 farm profile: the farmer's field, soil, water, crops and priorities.

Implements the contract M4 already consumes:

    get_farm_profile(farm_id) -> {
        "farm_id", "location_id", "soil_ph", "field_area_ha",
        "irrigation_budget_m3", "current_rotation", "source": "M3"
    }

Rules (from the project plan): missing values stay null and are reported, never
defaulted; every value records whether the farmer entered it or it came from a map.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from climateM1.services.locations import LOCATIONS
from mappingM3.field_boundaries import FieldBoundary, centroid, haversine_km, polygon_area_ha
from mappingM3.soil_inputs import SoilInputs
from mappingM3.units import mm_to_m3

BASE_DIR = Path(__file__).resolve().parents[1]
SEED_PATH = BASE_DIR / "data" / "farms" / "demo_farms.json"
CATALOG_PATH = BASE_DIR / "data" / "reference" / "crop_catalog.csv"

WaterSource = Literal["rain_only", "tank", "borehole", "irrigation_scheme", "unknown"]
Constraint = Literal["little_labour_at_harvest", "no_tractor", "must_sell_to_market", "need_food_for_home", "short_lease"]
PRIORITY_KEYS = ("water", "soil", "climate", "income")

_lock = threading.Lock()


def _store_path() -> Path:
    return Path(os.environ.get("M3_FARM_STORE", BASE_DIR / "data" / "farms" / "farms_store.json"))


def known_crop_ids() -> set[str]:
    """Crop ids from M2's catalog (read directly so M3 does not depend on M2 internals)."""
    ids: set[str] = set()
    if CATALOG_PATH.exists():
        lines = CATALOG_PATH.read_text(encoding="utf-8").splitlines()[1:]
        for line in lines:
            cid = line.split(",", 1)[0].strip()
            if cid:
                ids.add(cid)
    return ids


class Irrigation(BaseModel):
    water_source: WaterSource = "unknown"
    budget_mm_per_season: float | None = Field(default=None, ge=0, le=2000)
    budget_source: Literal["farmer", "unknown"] = "unknown"

    @model_validator(mode="after")
    def _consistent(self) -> "Irrigation":
        if self.water_source == "rain_only" and self.budget_mm_per_season is None:
            self.budget_mm_per_season = 0.0
            self.budget_source = "farmer"
        if self.budget_mm_per_season is None:
            self.budget_source = "unknown"
        elif self.budget_source == "unknown":
            self.budget_source = "farmer"
        return self


class Priorities(BaseModel):
    """Farmer weights. Stored normalised so they sum to 1 (plan section 11)."""
    water: float = Field(default=0.25, ge=0)
    soil: float = Field(default=0.25, ge=0)
    climate: float = Field(default=0.25, ge=0)
    income: float = Field(default=0.25, ge=0)

    @model_validator(mode="after")
    def _normalise(self) -> "Priorities":
        total = self.water + self.soil + self.climate + self.income
        if total <= 0:
            raise ValueError("At least one priority weight must be above zero")
        for k in PRIORITY_KEYS:
            setattr(self, k, round(getattr(self, k) / total, 4))
        return self


class Site(BaseModel):
    """Where the field is, for a farm anywhere in the world (NASA data is global)."""
    latitude: float = Field(ge=-60, le=75)
    longitude: float = Field(ge=-180, le=180)
    place: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=80)


class PlantingWindow(BaseModel):
    crop_id: str
    start_month: int = Field(ge=1, le=12)
    end_month: int = Field(ge=1, le=12)


def site_location_id(lat: float, lon: float) -> str:
    return f"site_{lat:.3f}_{lon:.3f}"


def register_site(site: "Site | dict") -> str:
    """Add a farm's own coordinates to the M1 location registry so every module can use them."""
    from climateM1.services.locations import ClimateLocation
    d = site if isinstance(site, dict) else site.model_dump()
    lat, lon = round(float(d["latitude"]), 3), round(float(d["longitude"]), 3)
    loc_id = site_location_id(lat, lon)
    if loc_id not in LOCATIONS:
        LOCATIONS[loc_id] = ClimateLocation(loc_id, d.get("place") or f"Field at {lat}, {lon}", d.get("country") or "", lat, lon)
    return loc_id


class FarmProfileIn(BaseModel):
    """What the farmer submits (create or full update)."""
    farm_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{1,48}$")
    name: str = Field(min_length=1, max_length=80)
    location_id: str = "site"
    site: Site | None = None
    rotation_calendar: list[PlantingWindow] | None = None
    field_area_ha: float | None = Field(default=None, gt=0, le=500)
    soil: SoilInputs = Field(default_factory=SoilInputs)
    irrigation: Irrigation = Field(default_factory=Irrigation)
    current_rotation: list[str] | None = None
    priorities: Priorities = Field(default_factory=Priorities)
    prices_rs_per_kg: dict[str, float] | None = Field(default=None, description="Farmer's own selling price per kg, by crop_id (used for harvest value).")
    costs_rs_per_ha: dict[str, float] | None = Field(default=None, description="Farmer's growing cost per hectare per crop.")
    constraints: list[Constraint] = Field(default_factory=list)
    boundary: FieldBoundary | None = None

    @model_validator(mode="before")
    @classmethod
    def _site_location(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("site") and (data.get("location_id") in (None, "", "site") or data.get("location_id", "").startswith("site_")):
            data = {**data, "location_id": register_site(data["site"])}
        return data

    @field_validator("location_id")
    @classmethod
    def _registered(cls, v: str) -> str:
        if v not in LOCATIONS:
            raise ValueError(f"Unknown location_id '{v}'. Registered: {sorted(LOCATIONS)}")
        return v

    @field_validator("current_rotation")
    @classmethod
    def _crops(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if not 1 <= len(v) <= 6:
            raise ValueError("current_rotation needs 1 to 6 seasons")
        known = known_crop_ids()
        bad = [c for c in v if known and c not in known]
        if bad:
            raise ValueError(f"Unknown crop id(s) {bad}. Known: {sorted(known)}")
        return v


class FarmProfile(FarmProfileIn):
    farm_id: str
    demo: bool = False
    updated_at: str


# ---------------------------------------------------------------- storage

def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    return {f["farm_id"]: f for f in data.get("farms", [])}


def _all_raw() -> dict[str, Any]:
    farms = _read_json(SEED_PATH)
    farms.update(_read_json(_store_path()))
    return farms


def _save_user_farm(profile: FarmProfile) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        current = _read_json(path)
        current[profile.farm_id] = profile.model_dump(mode="json")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"farms": list(current.values())}, indent=2), encoding="utf-8")
        tmp.replace(path)


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "farm"
    return s if len(s) >= 2 else s + "-1"


# ---------------------------------------------------------------- service

def list_farms() -> list[FarmProfile]:
    return [FarmProfile.model_validate(f) for f in _all_raw().values()]


def load_farm(farm_id: str) -> FarmProfile:
    raw = _all_raw().get(farm_id)
    if raw is None:
        raise KeyError(farm_id)
    return FarmProfile.model_validate(raw)


def save_farm(data: FarmProfileIn, farm_id: str | None = None) -> FarmProfile:
    existing = _all_raw()
    fid = farm_id or data.farm_id or _slug(data.name)
    if farm_id is None and data.farm_id is None:
        base, n = fid, 2
        while fid in existing:
            fid, n = f"{base}-{n}", n + 1
    profile = FarmProfile(**{**data.model_dump(), "farm_id": fid, "demo": False,
                             "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    _save_user_farm(profile)
    return profile


def delete_farm(farm_id: str) -> bool:
    path = _store_path()
    with _lock:
        current = _read_json(path)
        if farm_id not in current:
            return False
        del current[farm_id]
        path.write_text(json.dumps({"farms": list(current.values())}, indent=2), encoding="utf-8")
    return True


def irrigation_budget_m3(profile: FarmProfile) -> float | None:
    return mm_to_m3(profile.irrigation.budget_mm_per_season, profile.field_area_ha)


def get_farm_profile(farm_id: str) -> dict[str, Any]:
    """The M4 contract (intelligenceM4/API_CONTRACT.md, 'M3: Farm context')."""
    p = load_farm(farm_id)
    return {
        "farm_id": p.farm_id,
        "location_id": p.location_id,
        "soil_ph": p.soil.ph,
        "field_area_ha": p.field_area_ha,
        "irrigation_budget_m3": irrigation_budget_m3(p),
        "current_rotation": p.current_rotation,
        "source": "M3",
        "demo": p.demo,
        "input_provenance": {
            "soil": p.soil.model_dump(mode="json"),
            "irrigation": p.irrigation.model_dump(mode="json"),
            "boundary": p.boundary.model_dump(mode="json") if p.boundary else None,
            "field_area_ha": "illustrative_seed" if p.demo else "caller_supplied_unverified",
            "current_rotation": "illustrative_seed" if p.demo else "caller_supplied_unverified",
        },
    }


def validate_profile(p: FarmProfileIn) -> dict[str, Any]:
    """Plan step 1: detect missing or contradictory inputs and say what to ask."""
    missing: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def need(field: str, prompt: str) -> None:
        missing.append({"field": field, "prompt": prompt})

    if p.field_area_ha is None:
        need("field_area_ha", "How big is the field? (hectares)")
    if p.current_rotation is None:
        need("current_rotation", "Which crops did you grow in the last seasons?")
    if p.irrigation.budget_mm_per_season is None:
        need("irrigation.budget_mm_per_season", "How much water can you give per season? (mm)")
    for f in p.soil.missing():
        need(f, {"soil.texture": "What is your soil like? (sandy, loam, clay…)",
                 "soil.ph": "Do you know your soil pH? A soil test gives it.",
                 "soil.drainage": "Does water stand on the field after rain?"}[f])
    if p.boundary is None:
        need("boundary", "Draw your field on the map.")

    if p.boundary is not None:
        area = polygon_area_ha(p.boundary.geometry)
        if p.field_area_ha is not None and abs(area - p.field_area_ha) / p.field_area_ha > 0.25:
            warnings.append({"field": "field_area_ha",
                             "message": f"Drawn outline is {area:.2f} ha but the stated area is {p.field_area_ha:.2f} ha."})
        lat, lon = centroid(p.boundary.geometry)
        loc = LOCATIONS[p.location_id]
        d = haversine_km(lat, lon, loc.latitude, loc.longitude)
        if d > 15:
            warnings.append({"field": "location_id",
                             "message": f"Field is {d:.0f} km from climate location {loc.name}; pick a closer location."})
    if p.soil.texture_source == "map_estimate" or p.soil.ph_source == "map_estimate":
        warnings.append({"field": "soil", "message": "Soil values come from a map estimate, not a field test."})
    if p.irrigation.water_source == "rain_only" and (p.irrigation.budget_mm_per_season or 0) > 0:
        warnings.append({"field": "irrigation", "message": "Rain only is selected but an irrigation budget is set."})

    return {
        "ready_for_analysis": not any(m["field"] in ("current_rotation",) for m in missing),
        "complete": not missing,
        "missing": missing,
        "warnings": warnings,
        "soil_confidence": p.soil.confidence(),
        "irrigation_budget_m3": mm_to_m3(p.irrigation.budget_mm_per_season, p.field_area_ha),
    }
