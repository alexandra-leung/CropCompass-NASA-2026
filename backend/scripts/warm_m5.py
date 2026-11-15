"""Download and save the NASA 2050s climate (M1 history + NEX-GDDP-CMIP6) for the demo farms.

Run once before a demo, from backend/:   py scripts/warm_m5.py
Each farm/scenario takes a few minutes the first time; afterwards the climate twin and
the M5 stress test answer instantly from backend/data/processed/m5_farm_climate_cache.json.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: E402,F401  registers the M1 provider
from climateM1.services.locations import LOCATIONS  # noqa: E402
from resilienceM5.climate_twin import find_climate_twins  # noqa: E402
from resilienceM5.scenario_engine import PowerClient, get_farm_climate  # noqa: E402


async def one(name, lat, lon, scenario):
    t = time.time()
    try:
        await get_farm_climate(lat, lon, scenario, 2041, 2060)
        await find_climate_twins(lat, lon, scenario, 2041, 2060, 3, PowerClient())
        print(f"saved  {name:<20} {scenario}  ({time.time() - t:.0f} s)", flush=True)
    except Exception as exc:
        print(f"failed {name:<20} {scenario}  {type(exc).__name__}: {exc}", flush=True)


async def main():
    for loc_id, loc in LOCATIONS.items():
        lat, lon = loc.latitude, loc.longitude
        for scenario in ("ssp245", "ssp370"):
            await one(loc_id, lat, lon, scenario)


if __name__ == "__main__":
    asyncio.run(main())
