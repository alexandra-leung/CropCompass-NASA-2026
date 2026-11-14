# CropCompass Member 5 — Unified Repository Edition

This folder replaces the superseded standalone `backendM5/` service. It is an
**in-process FastAPI router** mounted into the team's existing `backend/app.py`.
It does not install a new dependency environment or own a separate application.

## Actual integration status

- The router is mounted once in the unified `backend/app.py`; M1 is registered
  as the in-process farm-climate provider.
- Farm history and future targets use M1 services. NASA POWER is used for the
  documented candidate-location pool only.
- Climate Twin validates and ranks source-backed records. It does not infer crop
  suitability, yield, profit, or market outcomes.
- Until M2 adapter registration, `/stress-test` returns an explicit HTTP 503.
- Real network acquisition was verified for NASA POWER monthly history and the
  configured NASA NEX NetCDF subset endpoint at the registered Pamplemousses
  coordinates. No verified farmer parcel coordinates have been supplied.

## Run and test — from `backend/`

```bash
python -m pip install -r requirements.txt
python -m pytest -q tests
python -m uvicorn app:app --reload --port 8000
```

Interactive API documentation: `http://127.0.0.1:8000/docs`.
The coordinates below are the registered Pamplemousses technical-test location,
not a verified farmer parcel.

```bash
curl.exe -X POST http://127.0.0.1:8000/api/resilience/climate-twin -H "Content-Type: application/json" -d "{\"latitude\":-20.103,\"longitude\":57.575,\"scenario\":\"ssp245\",\"start_year\":2041,\"end_year\":2060,\"top_k\":3}"
```

The endpoint fetches/caches 2015–2024 NASA POWER monthly history for the farm
through M1, monthly NEX-GDDP-CMIP6 daily records for the selected SSP and years,
and historical NASA POWER records for the candidate pool. M1's SQLite cache
stores source URLs, retrieval timestamps, parsed rows, and the original NEX
NetCDF response bytes; M5 caches full candidate POWER JSON responses under
`backend/data/raw/nasa_power/m5_analogs/`. Do not commit generated cache data.

Offline candidate-cache behavior can be enabled with `M5_OFFLINE=1`; farm data
must also be available in M1's source cache or the endpoint returns 503.
Synthetic records are restricted to explicitly labelled tests.

## M1-to-M5 monthly climate contract

- Historical target: NASA POWER monthly `T2M` (°C) and `PRECTOTCORR`
  (mm/day) from M1. Precipitation is multiplied by the actual days in each
  calendar month, then averaged across the 2015–2024 baseline.
- Future target: M1 retrieves daily `tas`/`pr` from NASA NEX-GDDP-CMIP6 for
  each year and enabled model. `tas` K is converted to °C; `pr` kg m⁻² s⁻¹ is
  multiplied by 86,400, summed by month, averaged across years per model, then
  equally averaged across contributing models.
- NASA describes NEX-GDDP-CMIP6 as a bias-corrected, downscaled product. M1
  and M5 apply no second delta adjustment. Provenance includes SSP, model,
  variant, source URLs, requested coordinates, selected grid cells, dates,
  units, model spread, and excluded models.
- Incomplete POWER monthly baselines are rejected. A future target requires at
  least three complete M1 models; incomplete model-years are excluded at the
  model level and reported.

The public M1 `/api/climate/history` and `/api/climate/scenarios` response
schemas remain unchanged. The in-process M5 adapter uses additional monthly
M1 service functions because the existing public contract exposes annual
summaries only.

## Endpoints

- `GET /api/resilience/health` — M5 and M2 readiness.
- `POST /api/resilience/climate-twin` — download/read actual NASA records, rank candidates.
- `POST /api/resilience/stress-test` — run actual M2 evaluator across scenario variants.
- `POST /api/resilience/rescue-mode` — summarize existing stress results; NO new scores.

See [API_CONTRACT.md](API_CONTRACT.md) for request and response shapes. Supported
scenarios are the two configured by M1: `ssp245` and `ssp370`.

## Real M2 integration

**Do not guess** `agricultureM2` symbols. Inspect:
`agricultureM2/API_CONTRACT.md`, `agricultureM2/routes.py`,
`agricultureM2/rotation_engine.py`, `agricultureM2/water_wallet.py`,
`agricultureM2/scoring.py`, `agricultureM2/providers/m1_climate.py`.

Register an in-process M2 wrapper via:

```python
from resilienceM5.stress_test import register_m2_evaluator

# Implement after reading M2's true input/output contract:
# def real_m2_adapter(original_request: dict, climate: MonthlyClimate,
#                     water_budget_m3: float | None) -> dict:
#     <copy input; map climate and water to REAL M2 request fields>
#     <call SAME M2 rotation engine used by normal app>
#     <return normalized {"rotations": [{"id": ..., "feasible": ..., ...}, ...]}>
# register_m2_evaluator(real_m2_adapter)
```

`rotations` must include the current plan and at least two alternatives. Preserve
IDs and report infeasible alternatives rather than dropping them. M5 will run
the wrapper with four conditions if irrigation is reduced: historical, future,
historical with reduced irrigation, and future with reduced irrigation.

If M2 never consumes changed monthly rainfall/temperature inputs, the stress
test is NOT valid. Add or repair M2's climate sensitivity before demo.

## M4 and frontend integration

- Frontend: call `/api/resilience/climate-twin` and `/api/resilience/stress-test`
  from the existing `frontend/src/api/resilience.ts`; render in the existing
  `pages/ResilienceLab.tsx`.
- M4: expose `source_urls`, data classification, scenario, grid scale, method,
  baseline period, missingness, and limitations through its Evidence Passport.
- M3: use actual farm coordinates and original farmer water budget in m3.

## Scientific constraints

1. Climate Twin is a comparison inside the selected reference pool, not proof
   that another site's crops are suitable for Mauritius.
2. NASA climate is gridded; do not claim exact field-level forecasts.
3. A scenario score is not a survival probability or measured result.
4. An irrigation reduction is farmer-specified hypothetical input, not NASA data.
5. Soil nutrient improvement, yield, profit, and market optimization are outside
   this project's current scope.
6. Optional Bare-Soil Radar must not infer exposed soil from low NDVI alone.
7. Weather and model data must have explicit source URLs and units.
