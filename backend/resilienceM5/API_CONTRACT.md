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
  "rotation_request": {
    "soil_ph": null,
    "rotations": [
      {"id": "current", "crops": ["maize", "maize", "maize"]},
      {"id": "alternative_a", "crops": ["maize", "cowpea", "sweet_potato"]},
      {"id": "alternative_b", "crops": ["cowpea", "sweet_potato", "groundnut"]}
    ]
  }
}
```

The 100 m3 and 30% values in this **request example** are explicitly hypothetical
farmer inputs, not claims about real farms or NASA data. `baseline_water_budget_m3`
is required and must be finite/nonnegative. `irrigation_reduction_fraction`, if
provided, must be strictly between 0 and 1. `rotation_request.rotations` must
contain at least three `{id, crops}` candidates; each crop sequence must contain
at least two M2 catalog IDs. IDs are caller supplied and are retained across all
scenarios. Optional `soil_ph` is passed to M2's suitability screening callable.

The adapter passes candidate sequences to the existing
`agricultureM2.scoring.score_rotations(list[list[str]])` callable. That callable
uses M2's `compare_rotations` and emits positional `rotation_1`… IDs, which M5
maps back to the supplied IDs. The adapter also invokes M2's
`check_crop_suitability` for each candidate crop and each month, using actual
M1 monthly temperature and optional soil pH. These month-by-month screens are
diagnostic only; M2 has no planting calendar to associate crops with months.

Current normalized result for each scenario has this shape:

```json
{
  "rotations": [
    {
      "id": "current",
      "feasible": null,
      "score": null,
      "rank": null,
      "water_requirement_m3": null,
      "failed_constraints": [],
      "details": {
        "feasibility_status": "not_calculated_by_m2",
        "water_budget_applied": false,
        "precipitation_applied": false
      }
    }
  ]
}
```

The nullable fields are intentional. The current M2 scorer returns no
per-rotation score/rank or feasibility. Its catalog has no temperature, rainfall,
or pH reference ranges, and its water-demand utility requires daily ET0 that M1
does not provide. Empty `failed_constraints` means M2 supplied no such
constraints; it does not mean the rotation passed agronomic constraints.

Every scenario includes its exact 12 monthly M1 temperature (°C) and
precipitation (mm/month), the full validated climate provenance, the farmer
water budget in m3, M2 input-capability flags, and actual M2 rotation details.
The response also includes the per-month climate delta, available score/rank
deltas only when scales permit, and a climate sensitivity report. Historical
and projected climate differences are calculated month by month and are not
assumed to be uniformly warmer or drier. Reduced irrigation is a distinct
farmer-defined what-if and is never derived from rainfall.

With the current M2 implementation, temperature values reach the suitability
callable but no crop reference ranges are available for a sensitivity result.
Precipitation and irrigation budgets do not affect M2 calculations.
`verified_m2_climate_sensitivity` therefore remains false. Missing M2 evaluator
or M1 data returns 503; invalid budgets, reductions, or rotations return 422.

## POST /rescue-mode

Request: `{"stress_output": <the unchanged actual stress-test response>}`.
Returns candidate IDs ordered by known feasibility passes, then unknown/failed
outcomes. Null feasibility and missing scenario results count as unknown, never
as a pass. Scores are compared only when all results have non-null scores on the
same declared scale; no score is manufactured when M2 omits it. Failures include
the scenario, water budget, and actual M2 constraint reasons where provided.
The response includes the tested scenario conditions and each candidate's
per-scenario outcome details so climate and irrigation trade-offs remain visible.

The response may include M2's verified rotation sequence as a season-labeled
sequence only. Planting dates and interventions remain pending unless supported
by explicit M2 agronomic logic. A robust-across-scenarios label is emitted only
when all scenarios in a two- or four-condition set report feasibility as true.
No survival probability or guaranteed success rate is produced.

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
- M2: adapter is connected to real M2 callables, but climate/water feasibility
  remains unverified: crop ranges, crop calendar, ET0, and a supported rainfall
  water-balance calculation are absent. Do not treat unknown as pass.
- M3: supply verified farm point and user-defined irrigation budget.
- M4: present source/assumption metadata and distinguish observation, scenario,
  modeled decision and user what-if.
