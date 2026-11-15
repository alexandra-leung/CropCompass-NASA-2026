from datetime import date
from fastapi import APIRouter, HTTPException, Query
from climateM1.models.climate import HistoryResponse, ScenarioResponse
from climateM1.services.cache import (
    get_cached,
    save_cached,
    HISTORY_CACHE_VERSION,
    SCENARIO_CACHE_VERSION,
)
from climateM1.services.history import fetch_history
from climateM1.services.locations import LOCATIONS
from climateM1.services.projections import fetch_scenarios
from climateM1.services.model_registry import load_model_registry

router = APIRouter(prefix="/api/climate", tags=["Climate intelligence"])


def _get_location(location_id: str):
    location = LOCATIONS.get(location_id)
    if location is None:
        raise HTTPException(status_code=404, detail=f"Unknown climate location: {location_id}")
    return location


@router.get("/history", response_model=HistoryResponse)
async def climate_history(
    location_id: str = Query(default="pamplemousses-04"),
    start: date = Query(default=date(2021, 1, 1)),
    end: date = Query(default=date(2025, 12, 31)),
):
    if end < start:
        raise HTTPException(status_code=400, detail="The end date must be on or after the start date")
    location = _get_location(location_id)
    start_key, end_key = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    cache_key = (
        f"history:{HISTORY_CACHE_VERSION}:"
        f"{location_id}:{start_key}:{end_key}"
    )
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        payload = await fetch_history(location, start_key, end_key)
        save_cached(cache_key, payload)
        return payload
    except Exception as exc:
        stale_payload = get_cached(cache_key, allow_stale=True)
        if stale_payload is not None:
            return stale_payload
        raise HTTPException(status_code=502, detail=f"Climate history retrieval failed and no cached copy is available: {exc}") from exc



@router.get("/scenarios", response_model=ScenarioResponse)
async def climate_scenarios(
    location_id: str = Query(default="pamplemousses-04")
):
    location = _get_location(location_id)
    registry = load_model_registry()

    source = registry["source"]
    enabled_models = [
        model for model in registry["models"]
        if model.get("enabled", True)
    ]

    model_signature = ",".join(
        f"{m['id']}-{m['variant']}-{m.get('grid_label', 'gn')}"
        for m in enabled_models
    )

    scenario_signature = ",".join(
        scenario["id"] for scenario in registry["scenarios"]
    )

    year_signature = ",".join(
        str(year) for year in registry["projection_years"]
    )

    cache_key = (
        f"scenarios:{SCENARIO_CACHE_VERSION}:{location_id}:"
        f"{source['id']}:{source.get('version', 'unknown')}:"
        f"{model_signature}:{scenario_signature}:{year_signature}"
    )

    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        payload = await fetch_scenarios(location)
        save_cached(cache_key, payload)
        return payload

    except Exception as exc:
        stale_payload = get_cached(cache_key, allow_stale=True)

        if stale_payload is not None:
            return stale_payload

        raise HTTPException(
            status_code=502,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc
