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
- `/stress-test` is wired to M2's `score_rotations()` and
  `check_crop_suitability()` callables.
- M2 currently does not compute rotation feasibility, per-rotation scores,
  rankings, or climate-derived irrigation demand. Those results remain null;
  M5 does not claim that a rotation passed an agronomic test.
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

## M2 integration and current model limits

The root `backend/agricultureM2/API_CONTRACT.md` does not exist. The supported
callables found in the checked-in M2 source are:

- `score_rotations(rotations: list[list[str]])`: requires at least three
  sequences, delegates to `compare_rotations`, and returns positional IDs such
  as `rotation_1`. `overall_score`, `recommended_rotation`, and `ranking` are
  currently null/not calibrated.
- `check_crop_suitability(crop_id, temperature_c=None, soil_ph=None)`: screens
  one scalar temperature and/or pH against catalog reference ranges. The current
  catalog has no temperature, rainfall, or pH ranges, so these checks report
  insufficient data.
- `calculate_crop_water_demand(crop_id, daily_et0_mm)`: uses the FAO-style
  `Kc × ET0` calculation. M1/M5 provide monthly temperature and precipitation,
  not daily reference ET0; the M2 function also does not calculate irrigation
  requirement.
- `providers/m1_climate.py` fetches raw M1 responses but does not map them into
  an M2 decision calculation.

M5's `m2_adapter.py` maps named `{id, crops}` candidates to the real M2
`score_rotations` call and applies M2's temperature suitability callable to each
calendar-month temperature as a diagnostic only. It does not assume that crops
are planted or growing in every month. The monthly precipitation and farmer
water budget are retained in scenario provenance but are not consumed by M2;
feasibility and water requirement are therefore `null`, not guessed.

The `/stress-test` endpoint requires a farmer-entered `baseline_water_budget_m3`.
If a reduction fraction is supplied, M5 creates the four requested conditions
and sends the reduced budget through the adapter. The current M2 decision
callables ignore that budget, so this is a recorded what-if rather than a
verified feasibility change. `verified_m2_climate_sensitivity` remains false
until actual M2 calculations consume validated climate variables and the
catalog/model supplies the necessary reference data.

No separate recommendation engine, hardcoded crop thresholds, survival
probability, yield estimate, or invented scores are used. A real climate-based
water feasibility repair still needs, at minimum, sourced crop suitability
ranges and a defensible crop calendar, plus daily/reference ET0 and a supported
rainfall/soil-water calculation. Those inputs cannot be inferred from the
current M2/M1 interfaces.

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
