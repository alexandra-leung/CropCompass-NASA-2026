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

- M4: send the unchanged results from `/api/resilience/climate-twin` and
  `/api/resilience/stress-test` inside the `resilience` object of the existing
  `AnalysisBundle`, then POST that bundle to `/api/intelligence/evidence`.
  The passport returns traceable M5 records and retains source URLs, data
  classification, scenario, grid scale, method, baseline/future periods,
  missingness, farmer constraints and limitations. M4 does not itself call M5
  from `/api/intelligence/analyze`.
- Frontend: the repository root `frontend/` currently contains only
  `.gitkeep`; there is no checked-in React app, API client, M3 UI or design
  system to extend. Do not treat the nested legacy `rotation_studio.html` as
  the unified frontend.
- M3: use actual farm coordinates and the original farmer-entered water budget
  in m3; no verified M3 farm profile is currently implemented.

## Reproducible cached-data API demonstration

Run from `backend/` after installing `requirements.txt`. The M5 candidate
records are real cached NASA POWER responses under
`data/raw/nasa_power/m5_analogs/`; M1 also needs the matching cached source
records in `data/climate_cache.sqlite3`. Set `M5_OFFLINE=1` to require cached
candidate data and prevent silent substitution. The M5 result snapshot uses
`(-20.25, 57.5)`; this is a technical test point, not a verified farmer parcel
or an implemented M3 farm profile.

The cached `ssp245` comparison for 2041–2060 returned these top analogs:

| Rank | NASA POWER reference location | Temperature RMSE (°C) | Precipitation MAE (mm/month) |
|---|---|---:|---:|
| 1 | Toamasina, Madagascar | 0.884 | 23.811 |
| 2 | Cairns, Australia | 1.224 | 45.379 |
| 3 | Saint-Denis, Réunion | 1.129 | 79.959 |

These are actual results from the limited candidate pool, not global matches.
The associated M1/M5 stress-test output reported historical 2015–2024 annual
mean temperature and rainfall of 25.3699 °C and 773.12 mm, versus 23.1426 °C
and 1779.9672 mm for the 2041–2060 `ssp245` multi-model projection at that
technical point. These derived annual summaries describe this cached example
only; they are not field measurements or general scenario claims. M2 received
the differing monthly temperatures, but reported no temperature calculation,
water-balance calculation, or water-budget feasibility. With the test-only
100 m³ budget and 30% reduction, the passed budget changed from 100 to 70 m³;
M2 marked it unapplied, all four scenario outcomes remained unknown, and Rescue
Mode reported no feasibility passes.

```powershell
$env:M5_OFFLINE = "1"
python -m uvicorn app:app --port 8000
```

From a second PowerShell terminal in `backend/`, use the technical test point
and a test-only farmer what-if. The water budget/reduction are user inputs, not
measurements, and do not currently change M2 feasibility:

```powershell
$location = @{ latitude = -20.25; longitude = 57.5 }
$twinRequest = $location + @{
  scenario = "ssp245"; start_year = 2041; end_year = 2060; top_k = 3
}
$twin = Invoke-RestMethod http://127.0.0.1:8000/api/resilience/climate-twin `
  -Method Post -ContentType "application/json" -Body ($twinRequest | ConvertTo-Json)

$rotationRequest = Get-Content .\data\fixtures\m5_test_rotation_request.json -Raw |
  ConvertFrom-Json
$stressRequest = $location + @{
  scenario = "ssp245"; start_year = 2041; end_year = 2060
  baseline_water_budget_m3 = 100; irrigation_reduction_fraction = 0.3
  rotation_request = $rotationRequest
}
$stress = Invoke-RestMethod http://127.0.0.1:8000/api/resilience/stress-test `
  -Method Post -ContentType "application/json" -Body ($stressRequest | ConvertTo-Json -Depth 20)
$rescue = Invoke-RestMethod http://127.0.0.1:8000/api/resilience/rescue-mode `
  -Method Post -ContentType "application/json" `
  -Body (@{ stress_output = $stress } | ConvertTo-Json -Depth 30)

$bundle = Get-Content .\intelligenceM4\fixtures\example_evidence_request.json -Raw |
  ConvertFrom-Json
$bundle | Add-Member -NotePropertyName resilience -NotePropertyValue @{
  scenario = "ssp245"; climate_twin = $twin; stress_tests = @($stress)
}
$bundleJson = $bundle | ConvertTo-Json -Depth 100
$bundleBytes = [System.Text.Encoding]::UTF8.GetBytes($bundleJson)
$passport = Invoke-RestMethod http://127.0.0.1:8000/api/intelligence/evidence `
  -Method Post -ContentType "application/json; charset=utf-8" -Body $bundleBytes
```

Inspect `$twin.analogs`, `$stress.scenarios`, `$rescue.candidates`, and the
M5 records in `$passport.evidence`; all reported comparisons come from the API
responses, not constants in the interface. Preserve the full M5 responses in
the evidence bundle to retain source URLs, model/scenario details, units,
farmer constraints, and limitations. This fixture call checks the M4
serialization contract only: its farm context is not a verified profile for
the technical M5 point above. Do not present it as a joined farmer journey.

The root `frontend/` is empty, so this repository currently cannot produce
Resilience Lab screenshots or a browser-based farmer journey. Do not present
Swagger or a JSON response as a UI screenshot. A verified M3 farm profile and
the frontend project/design system are still required for that submission
evidence.

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
