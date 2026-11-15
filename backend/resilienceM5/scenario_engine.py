"""M5 NASA POWER candidate data and the M1 farm-climate integration contract.

M1 is authoritative for farm history and CMIP6 projections. NASA POWER is used
here only for the documented historical candidate pool.
"""
from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import math
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NASA_BASE = "https://power.larc.nasa.gov"
HIST_START, HIST_END = 2015, 2024
DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "data" / "raw" / "nasa_power" / "m5_analogs"
SCENARIOS = {"ssp245", "ssp370"}


class DataUnavailable(RuntimeError):
    """Cannot substantiate a required climate value from the recorded NASA source."""


@dataclass(frozen=True)
class MonthlyClimate:
    """Calendar-month mean temperature (°C) and monthly precipitation totals (mm).

    12-element vectors are Jan..Dec. The raw API response is cached separately.
    """
    temperature_c: tuple[float, ...]
    precipitation_mm: tuple[float, ...]
    provenance: dict

    def __post_init__(self):
        if len(self.temperature_c) != 12 or len(self.precipitation_mm) != 12:
            raise ValueError("Climate must have exactly twelve Jan-Dec values")
        if any(not math.isfinite(float(v)) for v in (*self.temperature_c, *self.precipitation_mm)):
            raise ValueError("Climate vectors must contain finite numeric values")
        if any(p < 0 for p in self.precipitation_mm):
            raise ValueError("Monthly precipitation totals must not be negative")
        source_urls = self.provenance.get("source_urls") if isinstance(self.provenance, dict) else None
        if not isinstance(source_urls, list) or not source_urls or any(
            not isinstance(url, str) or not url.strip() for url in source_urls
        ):
            raise ValueError("Source URLs are mandatory. Do not label invented data as NASA records")

    def to_dict(self) -> dict:
        return asdict(self)


# Locations are sample reference points, not measured crops or inferred suitability.
# Do not call these a global search; the candidate pool is deliberately small.
CANDIDATE_SITES = (
    {"id": "MG_TOAMASINA", "name": "Toamasina, Madagascar", "latitude": -18.15, "longitude": 49.40},
    {"id": "MG_ANTANANARIVO", "name": "Antananarivo, Madagascar", "latitude": -18.91, "longitude": 47.52},
    {"id": "RE_SAINT_DENIS", "name": "Saint-Denis, Réunion", "latitude": -20.88, "longitude": 55.45},
    {"id": "TZ_DAR", "name": "Dar es Salaam, Tanzania", "latitude": -6.79, "longitude": 39.21},
    {"id": "MZ_MAPUTO", "name": "Maputo, Mozambique", "latitude": -25.97, "longitude": 32.59},
    {"id": "ZA_DURBAN", "name": "Durban, South Africa", "latitude": -29.86, "longitude": 31.03},
    {"id": "AU_CAIRNS", "name": "Cairns, Australia", "latitude": -16.92, "longitude": 145.78},
    {"id": "AU_TOWNSVILLE", "name": "Townsville, Australia", "latitude": -19.26, "longitude": 146.82},
    {"id": "FJ_NADI", "name": "Nadi, Fiji", "latitude": -17.78, "longitude": 177.42},
    {"id": "FJ_SUVA", "name": "Suva, Fiji", "latitude": -18.14, "longitude": 178.44},
)


def _value(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    # NASA's missing sentinel is -999.
    return n if math.isfinite(n) and n > -998 else None


def _get_series(payload: dict, parameter: str):
    raw = payload.get("properties", {}).get("parameter", {}).get(parameter)
    if not isinstance(raw, dict):
        raise DataUnavailable(f"Missing NASA parameter {parameter}")
    if not any(str(k).isdigit() and len(str(k)) == 6 for k in raw):
        raise DataUnavailable(f"Unexpected historical NASA structure for {parameter}")
    return raw


def _verify_units(payload: dict):
    params = payload.get("parameters", {})
    if not isinstance(params, dict):
        raise DataUnavailable("NASA POWER response has no parameter unit metadata")
    accepted = {
        "T2M": {"c", "°c", "degc", "degree c", "degrees c"},
        "PRECTOTCORR": {"mm/day", "mm/d", "mm day-1", "mm/day (mean)"},
    }
    for name, allowed in accepted.items():
        entry = params.get(name, {})
        declared = entry.get("units") if isinstance(entry, dict) else None
        if declared is None or str(declared).strip().lower() not in allowed:
            raise DataUnavailable(f"Unexpected or missing {name} units {declared!r}: verify before converting")


def assemble_climatology(
    saved: dict,
    year_start: int,
    year_end: int,
    latitude: float | None = None,
    longitude: float | None = None,
) -> MonthlyClimate:
    """Convert documented monthly mean-daily precipitation to monthly totals.

    Requires >=80% of requested years for *every* calendar month.
    """
    if year_start > year_end:
        raise ValueError("Invalid year range")
    payload = saved["payload"]
    _verify_units(payload)
    temp_raw = _get_series(payload, "T2M")
    precip_raw = _get_series(payload, "PRECTOTCORR")
    temp, rain = defaultdict(list), defaultdict(list)
    for key, value in temp_raw.items():
        date = str(key)
        if len(date) != 6 or not date.isdigit():
            continue
        year, month = int(date[:4]), int(date[4:])
        if not (year_start <= year <= year_end and 1 <= month <= 12):
            continue
        t, p = _value(value), _value(precip_raw.get(key))
        if t is None or p is None or p < 0:
            continue
        temp[month].append(t)
        rain[month].append(p * calendar.monthrange(year, month)[1])
    expected_years = year_end - year_start + 1
    counts = {m: len(temp[m]) for m in range(1, 13)}
    if any(counts[m] != expected_years for m in counts):
        raise DataUnavailable(f"Incomplete NASA data ({year_start}-{year_end}); valid years by month: {counts}")
    coords = payload.get("geometry", {}).get("coordinates")
    return MonthlyClimate(
        temperature_c=tuple(round(sum(temp[m]) / len(temp[m]), 4) for m in range(1, 13)),
        precipitation_mm=tuple(round(sum(rain[m]) / len(rain[m]), 4) for m in range(1, 13)),
        provenance={
            "source": "NASA POWER",
            "source_id": "NASA POWER monthly point API",
            "dataset": "NASA POWER monthly meteorology",
            "source_urls": [saved["url"]], "retrieved_at": saved["retrieved_at"],
            "data_type": "historical_gridded",
            "scenario": None, "model": "NASA POWER meteorological product",
            "requested_coordinates": (
                {"latitude": latitude, "longitude": longitude}
                if latitude is not None and longitude is not None
                else None
            ),
            "period_start": f"{year_start}-01", "period_end": f"{year_end}-12",
            "grid_resolution": "NASA POWER point product; spatial support varies by parameter",
            "grid_coordinates": coords, "temperature_unit": "degC",
            "precipitation_unit": "mm/month",
            "precipitation_method": "monthly mean daily rate (mm/day) × actual days in month, then average across years",
            "coverage_valid_years_by_month": counts,
            "missing_data": False,
            "cache_status": saved.get("cache_status", "unknown"),
            "limitations": "NASA gridded climate data; not direct measurements on the farmer's field",
        },
    )


class PowerClient:
    def __init__(self, cache_dir: Path | None = None, offline: bool | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE
        self.offline = (os.getenv("M5_OFFLINE", "0") == "1") if offline is None else offline
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get(self, route: str, params: dict) -> dict:
        url = NASA_BASE + route + "?" + urlencode(sorted(params.items()))
        filename = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24] + ".json"
        path = self.cache_dir / filename
        if path.is_file():
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("url") == url and isinstance(record["payload"]["properties"]["parameter"], dict):
                    return {**record, "cache_status": "historical_archive_cache_age_not_verified"}
            except (ValueError, KeyError, TypeError, AttributeError, OSError):
                pass
        if self.offline:
            raise DataUnavailable(f"Genuine NASA cache missing or invalid for {url}; fetch online first")
        req = Request(url, headers={"User-Agent": "CropCompass-M5-SpaceApps-2026/1.0", "Accept": "application/json"})
        try:
            with urlopen(req, timeout=80) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError, UnicodeError) as e:
            raise DataUnavailable(f"NASA POWER request failed: {url}: {e}") from e
        if not isinstance(payload, dict) or not isinstance(payload.get("properties", {}).get("parameter"), dict):
            raise DataUnavailable(f"Unexpected NASA response structure from {url}")
        record = {
            "url": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "cache_status": "network",
        }
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            raise DataUnavailable(
                f"NASA POWER source response was retrieved but could not be cached at {path}: {exc}"
            ) from exc
        return record

    def historical(self, latitude: float, longitude: float, start: int = HIST_START, end: int = HIST_END):
        saved = self._get("/api/temporal/monthly/point", {
            "community": "AG", "parameters": "T2M,PRECTOTCORR", "latitude": latitude,
            "longitude": longitude, "start": start, "end": end, "format": "JSON", "time-standard": "UTC",
        })
        return assemble_climatology(saved, start, end, latitude, longitude)

    async def historical_async(
        self,
        latitude: float,
        longitude: float,
        start: int = HIST_START,
        end: int = HIST_END,
    ) -> MonthlyClimate:
        return await asyncio.to_thread(self.historical, latitude, longitude, start, end)



# M1 owns farm history and future projections; M5 only uses this client for its
# documented candidate-location history pool.
M1Provider = Callable[
    [float, float, str, int, int],
    Awaitable[tuple[MonthlyClimate, MonthlyClimate]],
]
_registered_m1: M1Provider | None = None


def register_m1_provider(provider: M1Provider) -> None:
    global _registered_m1
    if not callable(provider):
        raise TypeError("M1 provider must be callable")
    _registered_m1 = provider


def m1_provider_registered() -> bool:
    return _registered_m1 is not None


async def get_farm_climate(
    latitude: float,
    longitude: float,
    scenario: str,
    start: int,
    end: int,
) -> tuple[MonthlyClimate, MonthlyClimate]:
    if _registered_m1 is None:
        raise DataUnavailable(
            "M1 climate provider is not registered; the unified backend must register its in-process adapter"
        )
    key = f"{latitude:.4f},{longitude:.4f}|{scenario}|{start}-{end}"
    use_cache = "PYTEST_CURRENT_TEST" not in os.environ
    saved = _farm_climate_cache().get(key) if use_cache else None
    if saved:
        from .m1_adapter import _to_monthly_climate, _validate_m1_provenance
        try:
            pair = []
            for name, source, first, last, ssp in (
                ("observed", "NASA POWER", HIST_START, HIST_END, None),
                ("future", "NASA NEX-GDDP-CMIP6", start, end, scenario),
            ):
                record = saved[name]
                provenance = record["provenance"]
                climate = _to_monthly_climate({**record,
                    "temperature_unit": provenance.get("temperature_unit"),
                    "precipitation_unit": provenance.get("precipitation_unit")})
                _validate_m1_provenance(climate, source, latitude, longitude,
                                        f"{first}-01", f"{last}-12", ssp)
                pair.append(MonthlyClimate(climate.temperature_c, climate.precipitation_mm,
                    {**provenance, "m5_cache": "validated_saved_M1_result", "m5_cached_at": saved["saved_at"]}))
            saved_at = datetime.fromisoformat(saved["saved_at"])
            age = (datetime.now(timezone.utc) - saved_at).total_seconds()
            if age < 0:
                raise ValueError("Cache timestamp is in the future")
            # Legacy records must pass validation above, but lack a method/config
            # signature and cannot establish that their transformation is current.
            if saved.get("method_signature") == _farm_cache_signature() and age <= 30 * 86400:
                return tuple(pair)
        except (KeyError, TypeError, ValueError, DataUnavailable) as exc:
            raise DataUnavailable(f"Invalid processed M1 climate cache: {exc}") from exc
    observed, future = await _registered_m1(
        latitude, longitude, scenario, start, end
    )
    if not isinstance(observed, MonthlyClimate) or not isinstance(future, MonthlyClimate):
        raise TypeError("M1 adapter must return (MonthlyClimate, MonthlyClimate) with provenance")
    if use_cache and future.provenance.get("source") == "NASA NEX-GDDP-CMIP6":
        _save_farm_climate(key, observed, future)
    return observed, future


# Saved M1 farm climate (history + NEX-GDDP projection): the projection takes minutes to
# download, so each completed result is kept on disk and reused. Values are unchanged.
FARM_CLIMATE_CACHE = Path(os.getenv("M5_FARM_CLIMATE_CACHE", str(Path(__file__).resolve().parents[1] / "data" / "processed" / "m5_farm_climate_cache.json")))


def _farm_climate_cache() -> dict:
    try:
        data = json.loads(FARM_CLIMATE_CACHE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_farm_climate(key: str, observed: MonthlyClimate, future: MonthlyClimate) -> None:
    from datetime import datetime, timezone
    data = _farm_climate_cache()
    data[key] = {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "method_signature": _farm_cache_signature(),
                 "observed": asdict(observed), "future": asdict(future)}
    try:
        FARM_CLIMATE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FARM_CLIMATE_CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(FARM_CLIMATE_CACHE)
    except OSError:
        pass


def _farm_cache_signature() -> str:
    from climateM1.services.model_registry import load_model_registry
    config = json.dumps(load_model_registry(), sort_keys=True)
    return "validated-monthly-v2:" + hashlib.sha256(config.encode()).hexdigest()
