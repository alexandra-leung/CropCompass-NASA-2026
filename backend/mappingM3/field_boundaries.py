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


def validate_polygon(geometry: dict[str, Any], require_mauritius: bool = False) -> None:
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


OSM_URL = "https://overpass-api.de/api/interpreter"
OSM_FIELD_TAGS = ("farmland", "orchard", "meadow", "farmyard", "greenhouse_horticulture", "plant_nursery", "vineyard", "allotments")


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "method": "auto_suggested",
        "geometry": None,
        "reason": reason,
        "fallback": "Draw the field by hand on the map.",
        "planned_source": "Fields of The World, global field boundaries (10 m)",
    }


def suggest_boundary(latitude: float, longitude: float) -> dict[str, Any]:
    """Automatic outline: the mapped OpenStreetMap farmland polygon at this point.

    Only a real mapped polygon is returned (never an invented shape); the farmer
    confirms or redraws it. Works anywhere OSM volunteers have mapped fields.
    """
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    if os.getenv("M3_OSM_DISABLED") == "1":
        return _unavailable("Automatic outlines are switched off (M3_OSM_DISABLED=1).")
    q = (f'[out:json][timeout:20];way(around:250,{latitude},{longitude})[landuse~"^({"|".join(OSM_FIELD_TAGS)})$"];'
         "out tags geom 25;")
    try:
        req = Request(OSM_URL, data=urlencode({"data": q}).encode(), headers={"User-Agent": "CropCompass-M3/1.0 (NASA Space Apps 2026)"})
        with urlopen(req, timeout=25) as r:
            elements = json.loads(r.read().decode("utf-8")).get("elements", [])
    except Exception as exc:  # network or service problem: fall back to drawing
        return _unavailable(f"OpenStreetMap could not be reached ({type(exc).__name__}).")
    best = None
    for el in elements:
        pts = [[round(g["lon"], 7), round(g["lat"], 7)] for g in el.get("geometry", []) if "lat" in g and "lon" in g]
        if len(pts) < 4 or pts[0] != pts[-1]:
            continue
        geom = {"type": "Polygon", "coordinates": [pts]}
        area = polygon_area_ha(geom)
        if not 0.01 <= area <= 100:
            continue
        inside = _point_in_ring(longitude, latitude, pts)
        clat, clon = centroid(geom)
        d = haversine_km(latitude, longitude, clat, clon)
        rank = (not inside, d, area)
        if best is None or rank < best[0]:
            best = (rank, geom, area, el, inside, d)
    if best is None:
        return _unavailable("No farmland is mapped in OpenStreetMap within 250 m of this point.")
    _, geom, area, el, inside, d = best
    return {
        "status": "suggested",
        "method": "auto_suggested",
        "geometry": geom,
        "area_ha": round(area, 3),
        "contains_point": inside,
        "distance_km": round(d, 3),
        "landuse": el.get("tags", {}).get("landuse"),
        "source": "OpenStreetMap landuse polygon (© OpenStreetMap contributors, ODbL)",
        "source_url": f"https://www.openstreetmap.org/way/{el.get('id')}",
        "note": "Mapped by volunteers; check it matches your field before saving.",
    }


def land_grid(geometry: dict[str, Any], buffer_m: float = 2.0, cell_m: float = 5.0, max_cells: int = 4000) -> dict[str, Any]:
    """Grid the field into square cells; a cell is plantable when its centre is inside the field
    and at least `buffer_m` from the edge (paths, borders, drainage). No external libraries."""
    ring = _ring(geometry)
    lat0 = sum(p[1] for p in ring) / len(ring)
    lon0 = sum(p[0] for p in ring) / len(ring)
    kx = math.radians(1) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    ky = math.radians(1) * EARTH_RADIUS_M
    pts = [((p[0] - lon0) * kx, (p[1] - lat0) * ky) for p in ring]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    cell = max(cell_m, math.sqrt(max(w * h, 1) / max_cells))

    def inside(x: float, y: float) -> bool:
        res = False
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                res = not res
        return res

    def edge_dist(x: float, y: float) -> float:
        best = float("inf")
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            dx, dy = x2 - x1, y2 - y1
            t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(x - x1 - t * dx, y - y1 - t * dy))
        return best

    cells, n_in, n_use = [], 0, 0
    y = min(ys) + cell / 2
    while y < max(ys):
        x = min(xs) + cell / 2
        while x < max(xs):
            if inside(x, y):
                n_in += 1
                ok = edge_dist(x, y) >= buffer_m + cell / 2
                n_use += ok
                cells.append([round(lon0 + x / kx, 7), round(lat0 + y / ky, 7), 1 if ok else 0])
            x += cell
        y += cell
    pct = round(n_use / n_in * 100, 1) if n_in else 0.0
    area = polygon_area_ha(geometry)
    return {"cell_m": round(cell, 2), "buffer_m": buffer_m, "cells_total": n_in, "cells_usable": n_use,
            "usable_pct": pct, "field_area_ha": round(area, 4), "usable_area_ha": round(area * pct / 100, 4),
            "cells": cells, "half_cell_deg": [round(cell / 2 / kx, 8), round(cell / 2 / ky, 8)],
            "method": f"{cell:.1f} m grid; a whole cell is plantable when it lies at least {buffer_m} m inside the field edge"}
