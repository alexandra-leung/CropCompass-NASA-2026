# Member 5 — Climate Resilience API Contract

Base path: `/api/resilience` mounted on existing FastAPI `backend/app.py`.
Farm history and projections are provided by M1 in-process. Candidate history
comes from cached NASA POWER source responses. Production responses never use
synthetic values.

## GET /health

Returns module readiness, whether the M1 provider and optional M2 evaluator are
registered, and whether M5 candidate-cache offline mode is enabled. M2 is not
required for Climate Twin.

## POST /climate-twin

Request:

```json
{
  "latitude": -20.25,
  "longitude": 57.50,
  "scenario": "ssp245",
  "start_year": 2041,
  "end_year": 2060,
  "top_k": 3
}
```

Coordinates above are approximate technical-test coordinates, not a verified
farmer parcel. `scenario` must be `ssp245` or `ssp370`, matching the M1 model
registry. Latitude must be within NEX-GDDP-CMIP6 coverage (59.875°S–89.875°N);
longitude is -180° to 180°. Future years are 2027–2100, ordered, with no more
than 30 years per request. `top_k` is 1–10 and defaults to 3.

Response fields:

- `field`, `scenario`, `period`
- `historical`: 12 Jan–Dec T (degC), P (mm/month), provenance
- `projected_target`: future monthly series, source URLs and transformation
- `analogs[]`: location ID, name, coordinates, normalized distance, monthly
  comparisons, temperature RMSE, precipitation MAE, candidate source metadata
- `candidate_count`, `excluded_candidates`, `method`, `limitations`

Each analog contains candidate coordinates, 12 monthly comparisons, temperature
RMSE (°C), precipitation MAE (mm/month), standardized distance components, and
NASA source provenance. The future target includes M1 model series and
descriptive model-spread metadata.

The score is:

```text
sqrt(0.5 * mean(((Ttarget - Tcandidate) / sTmonth)^2)
   + 0.5 * mean(((Ptarget - Pcandidate) / sPmonth)^2))
```

`sTmonth` and `sPmonth` are population standard deviations across valid candidate
climates for that calendar month, floored at 1 °C and 25 mm/month respectively.
Scores are sorted using full precision; exact ties sort by candidate ID. The
pool contains ten fixed reference locations and is not a global search. At least
three valid candidates are required; if the requested number cannot be supplied,
the API returns 503 rather than silently reducing `top_k`.

The target historical baseline is 2015–2024. POWER `T2M` is °C; monthly
`PRECTOTCORR` is mm/day and is multiplied by the actual days in each month.
Future NEX `tas` is converted K→°C; `pr` in kg m⁻² s⁻¹ is converted to daily
mm, summed within months, and averaged across years and contributing models.
NASA describes NEX-GDDP-CMIP6 as bias-corrected and downscaled; M1/M5 apply no
additional delta correction.

422: invalid request coordinates, scenario, period, or `top_k`.
503: required source data is missing/incomplete, fewer than three complete M1
models or candidates are available, or upstream NASA data cannot be retrieved.

## POST /stress-test

```json
{
  "latitude": -20.25,
  "longitude": 57.50,
  "scenario": "ssp245",
  "start_year": 2041,
  "end_year": 2060,
  "baseline_water_budget_m3": 100,
  "irrigation_reduction_fraction": 0.3,
  "rotation_request": { "PLACEHOLDER": "Replace with the validated M2 request object" }
}
```

The 100 m3 and 30% values in this **request example** are explicitly hypothetical
farmer inputs, not claims about real farms or NASA data. The `rotation_request`
object is opaque to M5, because M2 owns that schema. An M2 adapter must be
registered before the endpoint works; without it, the endpoint returns 503.

Normalized result returned by the adapter **for each scenario**:

```json
{
  "rotations": [
    {"id": "current", "feasible": true, "score": null, "failed_constraints": []},
    {"id": "alternative_a", "feasible": true, "score": null, "failed_constraints": []},
    {"id": "alternative_b", "feasible": false, "score": null,
     "failed_constraints": ["example_machine_readable_constraint"]}
  ]
}
```

This is a schema illustration only, NOT a computed response. M2 must determine
actual feasibility, score and failure reasons. `score` is nullable; do not fill
it with guessed percentages. Return all three IDs in every run. The M2 wrapper
maps `climate.temperature_c` and `climate.precipitation_mm` to its verified
climate fields, with units degC and mm/month. Water is always m3.

Response fields include `scenarios`, `differences_vs_baseline`, `method`,
`limitations`, and `verified_m2_climate_sensitivity:false` until this has been
explicitly checked in the integrated app.

## POST /rescue-mode

Request: `{"stress_output": <the unchanged actual stress-test response>}`.
Returns candidate IDs ordered by count of passed tested scenarios, with a
qualified worst feasible modeled score, failures and limitations.

## Data and interpretation

- M1's existing public history and scenario endpoints remain unchanged. The M5
  adapter uses M1's in-process monthly POWER and NEX services because the
  existing M1 API contract only exposes annual summaries.
- M1 cache entries retain the source URL, retrieval time, parsed grid-cell rows
  and original NEX NetCDF response bytes. M5 candidate cache files retain full
  POWER JSON responses, URL and retrieval time.
- Candidate pool is documented in `resilienceM5/scenario_engine.py`. NASA
  grids represent regional conditions, not farm-field measurements.
- A climate analog does not demonstrate that crops, soils, pests, water supply,
  or management practices from that location will succeed at the target farm.
- No yield, profit, revenue, survival probability, or market-price prediction is
  produced by Climate Twin.

## Integration gates

- M1: preserve source identity, coordinates, time bounds, scenario, model,
  variant, units, missingness, uncertainty and spatial scale.
- M2: inspect actual input function and output schema; connect via a small adapter,
  not a second crop decision engine.
- M3: supply verified farm point and user-defined irrigation budget.
- M4: present source/assumption metadata and distinguish observation, scenario,
  modeled decision and user what-if.
