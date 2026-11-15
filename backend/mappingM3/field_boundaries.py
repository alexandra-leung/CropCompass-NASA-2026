"""Field boundaries for M3.

The reliable path is a polygon the farmer draws (manual). Automatic outlines
(e.g. Fields of The World predictions) are a stretch feature: when no verified
prediction is available this module says so instead of inventing a shape.

Geometry is GeoJSON (longitude, latitude order, WGS84).
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from climateM1.services.locations import LOCATIONS

EARTH_RADIUS_M = 6_371_008.8

# Generous bounding box around Mauritius island (the demo country).
MAURITIUS_BBOX = {"lat_min": -20.6, "lat_max": -19.9, "lon_min": 57.25, "lon_max": 57.85}

BoundaryMethod = Literal["manual", "auto_suggested", "default_square"]


class FieldBoundary(BaseModel):
    """A field outline plus how it was obtained."""

    geometry: dict[str, Any]
    method: BoundaryMethod = "manual"
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str | None = None
    note: str | None = None

    @field_validator("geometry")
    @classmethod
    def _valid_polygon(cls, g: dict[str, Any]) -> dict[str, Any]:
        validate_polygon(g)
        return g


def _ring(geometry: dict[str, Any]) -> list[list[float]]:
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise ValueError("geometry must be a GeoJSON Polygon")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords or not isinstance(coords[0], list):
        raise ValueError("Polygon needs coordinates: [[ [lon, lat], ... ]]")
    return coords[0]


def validate_polygon(geometry: dict[str, Any], require_mauritius: bool = True) -> None:
    ring = _ring(geometry)
    if len(ring) < 4:
        raise ValueError("Polygon ring needs at least 4 positions (3 corners + closing point)")
    for p in ring:
        if not (isinstance(p, (list, tuple)) and len(p) >= 2 and all(isinstance(v, (int, float)) for v in p[:2])):
            raise ValueError("Each position must be [longitude, latitude]")
        lon, lat = p[0], p[1]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("Position out of range; GeoJSON order is [longitude, latitude]")
        if require_mauritius and not (
            MAURITIUS_BBOX["lat_min"] <= lat <= MAURITIUS_BBOX["lat_max"]
            and MAURITIUS_BBOX["lon_min"] <= lon <= MAURITIUS_BBOX["lon_max"]
        ):
            raise ValueError("Field must be on Mauritius island for this demo")
    if list(ring[0][:2]) != list(ring[-1][:2]):
        raise ValueError("Polygon ring must be closed (first and last positions equal)")
    if polygon_area_ha(geometry) <= 0:
        raise ValueError("Polygon has no area")


def polygon_area_ha(geometry: dict[str, Any]) -> float:
    """Area of a small polygon in hectares (local equirectangular projection)."""
    ring = _ring(geometry)
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    xs = [math.radians(p[0]) * EARTH_RADIUS_M * math.cos(lat0) for p in ring]
    ys = [math.radians(p[1]) * EARTH_RADIUS_M for p in ring]
    area_m2 = 0.0
    for i in range(len(ring) - 1):
        area_m2 += xs[i] * ys[i + 1] - xs[i + 1] * ys[i]
    return round(abs(area_m2) / 2 / 10_000, 4)


def centroid(geometry: dict[str, Any]) -> tuple[float, float]:
    """Mean of the ring's distinct vertices: (latitude, longitude)."""
    ring = _ring(geometry)[:-1]
    return (
        round(sum(p[1] for p in ring) / len(ring), 6),
        round(sum(p[0] for p in ring) / len(ring), 6),
    )


def square_boundary(latitude: float, longitude: float, area_ha: float) -> dict[str, Any]:
    """A square polygon of the given area centred on a point (placeholder outline)."""
    if area_ha <= 0:
        raise ValueError("area_ha must be > 0")
    half_side_m = math.sqrt(area_ha * 10_000) / 2
    dlat = math.degrees(half_side_m / EARTH_RADIUS_M)
    dlon = math.degrees(half_side_m / (EARTH_RADIUS_M * math.cos(math.radians(latitude))))
    lo, la = longitude, latitude
    ring = [
        [round(lo - dlon, 7), round(la - dlat, 7)],
        [round(lo + dlon, 7), round(la - dlat, 7)],
        [round(lo + dlon, 7), round(la + dlat, 7)],
        [round(lo - dlon, 7), round(la + dlat, 7)],
        [round(lo - dlon, 7), round(la - dlat, 7)],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M / 1000 * math.asin(math.sqrt(a))


def nearest_location(latitude: float, longitude: float) -> dict[str, Any]:
    """The registered M1 climate location closest to a point the farmer tapped."""
    best = min(LOCATIONS.values(), key=lambda L: haversine_km(latitude, longitude, L.latitude, L.longitude))
    return {
        "location_id": best.id,
        "name": best.name,
        "district": best.district,
        "distance_km": round(haversine_km(latitude, longitude, best.latitude, best.longitude), 2),
        "note": "Climate data for this location covers a regional grid, not just this field.",
    }


def suggest_boundary(latitude: float, longitude: float) -> dict[str, Any]:
    """Automatic outline suggestion.

    No verified field-boundary prediction (e.g. Fields of The World) is cached for
    Mauritius in this build, so nothing is invented: the caller should let the
    farmer draw the field by hand.
    """
    return {
        "status": "unavailable",
        "method": "auto_suggested",
        "geometry": None,
        "reason": "No verified field-boundary prediction is cached for this point.",
        "fallback": "Draw the field by hand on the map.",
        "planned_source": "Fields of The World, global field boundaries (10 m)",
    }
