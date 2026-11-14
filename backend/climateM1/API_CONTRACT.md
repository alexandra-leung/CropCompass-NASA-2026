# M1 — Climate Intelligence API Contract

**Project:** CropCompass 2.0  
**Module:** M1 — Climate Intelligence  
**API Framework:** FastAPI  
**Status:** Operational — geographic coverage and scenario configuration subject to team confirmation

## 1. Purpose

M1 is the centralized climate data provider for CropCompass 2.0.

It retrieves, processes, and serves historical climate information and future climate projections from NASA datasets.

Other modules must consume M1's standardized climate outputs instead of implementing duplicate NASA data ingestion.

**Module responsibilities:**

- M1: Climate data acquisition, preprocessing, caching, provenance and scenario delivery.
- M2: Crop rotation, suitability and water requirement analysis.
- M3: Climate visualization and location selection.
- M4: Evidence-based explanations and data provenance.
- M5: Climate resilience assessment and stress testing.

M1 does not perform crop yield prediction, profit estimation or crop rotation optimization.

## 2. Base URL

For local development:

```text
http://127.0.0.1:8000
```

API prefix:

```text
/api/climate
```

Interactive documentation:

```text
http://127.0.0.1:8000/docs
```

Machine-readable OpenAPI specification:

```text
http://127.0.0.1:8000/openapi.json
```

The base URL will change when the project is deployed.

## 3. Available Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/climate/history` | Retrieve historical climate data |
| GET | `/api/climate/scenarios` | Retrieve future climate projections |

Both endpoints return JSON.

### 3.1 Historical Climate Data

**Endpoint:**

```http
GET /api/climate/history
```

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `location_id` | string | Registered M1 location identifier |
| `start` | date | Optional historical period start, `YYYY-MM-DD` |
| `end` | date | Optional historical period end, `YYYY-MM-DD` |

Example:

```bash
curl "http://127.0.0.1:8000/api/climate/history?location_id=pamplemousses-04&start=2021-01-01&end=2025-12-31"
```

**Primary data source:** NASA POWER.

The endpoint provides historical climate information for the requested location and date range.

Consumers must use the actual response metadata to determine available variables, units, temporal resolution, and missing observations.

The exact response schema is defined by the FastAPI `HistoryResponse` model.

### 3.2 Future Climate Scenarios

**Endpoint:**

```http
GET /api/climate/scenarios
```

**Query parameter:**

| Parameter | Type | Description |
|---|---|---|
| `location_id` | string | Registered M1 location identifier |

Example:

```bash
curl "http://127.0.0.1:8000/api/climate/scenarios?location_id=pamplemousses-04"
```

**Primary data source:** NASA NEX-GDDP-CMIP6.

The endpoint provides projected climate conditions using multiple climate models.

Currently configured scenarios:

| Scenario | Description |
|---|---|
| `ssp245` | SSP2-4.5 |
| `ssp370` | SSP3-7.0 |

Currently configured projection years:

- 2030
- 2040
- 2050

These values describe the current implementation and may change following team review.

The exact response schema is defined by the FastAPI `ScenarioResponse` model.

## 4. Climate Models

M1 currently uses the following five CMIP6 models:

| Model | Current test status |
|---|---|
| ACCESS-CM2 | Success |
| CanESM5 | Success |
| MPI-ESM1-2-HR | Success |
| CNRM-ESM2-1 | Success |
| MRI-ESM2-0 | Success |

All five models successfully processed the configured scenarios and years during the latest local integration tests.

The implementation uses a model registry at:

```text
backend/climateM1/config/model_registry.json
```

The registry is the authoritative source for enabled models, variants, scenarios, projection years, variables and source configuration.

## 5. Scenario Response Structure

M1's scenario response exposes the following principal fields:

| Field | Meaning |
|---|---|
| `locationId` | Requested M1 location identifier |
| `baselinePeriod` | Descriptive period information |
| `scenarios` | Legacy scenario representation retained for compatibility |
| `modelResults` | Results and statuses from individual climate models |
| `ensemble` | Aggregated multi-model scenario results |
| `provenance` | Source information and metadata |
| `caveats` | Scientific limitations and interpretation guidance |

### 5.1 Ensemble Results

Each ensemble entry identifies a climate scenario and includes projected values for the configured years.

The observed structure includes:

```json
{
  "id": "ssp245",
  "values": [
    {
      "year": 2030,
      "rainfallMm": {
        "count": 5,
        "mean": null,
        "median": null,
        "minimum": null,
        "maximum": null,
        "spread": null
      },
      "temperatureC": {
        "count": 5,
        "mean": null,
        "median": null,
        "minimum": null,
        "maximum": null,
        "spread": null
      },
      "contributingModels": []
    }
  ]
}
```

**Schema illustration only:** The `null` values and empty model list above are placeholders showing field structure, not actual NASA results. Consumers should obtain real values from the API.

The response also includes scenario labels and descriptions.

### 5.2 Climate Variables

| Field | Meaning | Unit |
|---|---|---|
| `rainfallMm` | Projected annual accumulated precipitation | mm/year |
| `temperatureC` | Projected annual mean air temperature | °C |
| `count` | Number of contributing model values | Count |
| `mean` | Ensemble arithmetic mean | Variable unit |
| `median` | Ensemble median | Variable unit |
| `minimum` | Lowest model value | Variable unit |
| `maximum` | Highest model value | Variable unit |
| `spread` | Maximum minus minimum | Variable unit |

The ensemble spread is a descriptive measure of disagreement between models. It is **not** a statistical confidence interval or probability of future weather.

### 5.3 Model Coverage

Individual models expose status information through `modelResults`.

Known statuses include:

- `success`: Model processing completed successfully.
- `partial`: Some requested model outputs are unavailable or incomplete.
- `failed`: Model processing failed.

Consumers must check both model statuses and the `provenance.missingData` field.

An HTTP 200 response does not automatically mean every model and variable is complete.

## 6. Data Provenance

Future climate projections include a `provenance` object with information such as:

- Source: NASA NEX-GDDP-CMIP6
- Product: Daily downscaled CMIP6 projections
- Variables: precipitation (`pr`) and air temperature (`tas`)
- Requested coordinates
- Reported grid resolution
- Projection years
- Missing-data indicator
- Retrieval timestamp
- Scientific caveats

M1's implementation converts:

- Precipitation flux from `kg m⁻² s⁻¹` to daily precipitation in millimetres, then computes annual totals.
- Temperature from Kelvin to degrees Celsius.

These conversions must remain subject to scientific validation, including temporal aggregation and NetCDF calendar handling.

### Spatial Resolution

NEX-GDDP-CMIP6 uses a nominal 0.25° grid.

Values represent regional model-grid conditions, not precise observations or forecasts for an individual farm.

Different locations may return identical values when their coordinates map to the same model grid cell.

The frontend must not imply field-level precision.

## 7. Caching and Availability

M1 uses a local SQLite cache:

```text
backend/data/climate_cache.sqlite3
```

Cached datasets and scenario responses reduce repeated NASA downloads and processing.

Latest local verification:

- 60 out of 60 configured model/scenario/year/variable combinations cached.
- All five climate models returned `success`.
- `provenance.missingData` returned `false`.
- Cached scenario requests for the three registered locations returned HTTP 200.
- Repeated requests completed within milliseconds on the test machine.

These timings describe the local cached environment, not guaranteed production latency.

**Important:** The SQLite cache is a runtime artifact and is not automatically transferred through GitHub.

A fresh deployment may need to retrieve NASA data again.

### Availability Rules

Consumers must:

1. Handle API errors and request timeouts.
2. Avoid treating absent data as zero.
3. Display incomplete-model warnings when appropriate.
4. Distinguish cached historical projections from live data acquisition.
5. Avoid inventing climate values when M1 is unavailable.

M1 should eventually retry transient NASA transport failures and refresh incomplete cached results automatically.

## 8. Current Supported Locations

The current development registry includes:

| Location ID | Region |
|---|---|
| `pamplemousses-04` | Pamplemousses |
| `flacq-02` | Flacq |
| `black-river-01` | Black River |

**Pending team decision:** Final geographic coverage and any replacement or additional locations.

Location names and IDs must be registered in M1 before being exposed as supported options in the frontend.

## 9. Error Handling

Consumers should expect:

| HTTP status | Meaning |
|---|---|
| `200` | Request succeeded; inspect data completeness |
| `404` | Unknown registered location |
| `422` | Invalid request parameters, where validation applies |
| `502` | Upstream climate retrieval or processing failure, where handled by M1 |
| `500` | Unexpected server error |

Example unknown-location response:

```json
{
  "detail": "Unknown climate location: invalid-location"
}
```

Consumers should not interpret server errors as evidence of safe agricultural conditions.

## 10. Integration Guidance

### M2 — Agricultural Intelligence

M2 can use:

- Historical temperature and rainfall information
- Future projected temperature and rainfall summaries
- Location identifiers and time periods
- Data provenance and model completeness indicators

M2 must not assume that annual projection summaries are sufficient to calculate seasonal crop water requirements.

FAO-56 Water Wallet calculations require suitable reference evapotranspiration (`ET₀`) data or sufficient meteorological inputs for its calculation.

Crop suitability must also consider independently sourced crop requirements, soil conditions and farmer constraints.

### M3 — User Interface and Mapping

M3 should:

- Use registered location IDs.
- Display climate units and projection years.
- Distinguish historical data from projections.
- Show partial-data warnings.
- Present regional grid-resolution caveats.
- Avoid implying exact farm-scale predictions.

### M4 — Explainable AI

M4 should:

- Use the actual M1 response as evidence.
- Explain the meaning of model spread and missing values.
- Preserve data provenance.
- Avoid unsupported claims about future weather certainty.
- Clearly differentiate observations, modeled projections and hypothetical stress scenarios.

### M5 — Climate Resilience

M5 can use:

- Multi-model projected temperature
- Multi-model projected rainfall
- Scenario and projection-year identifiers
- Model contributing counts
- Ensemble spread
- Missing-data and caveat metadata

M5 owns any additional drought, heat or rainfall stress-test logic.

Those stress tests must distinguish actual NASA projections from derived or hypothetical scenarios.

## 11. Testing

Start the unified backend:

```bash
cd backend
python -m uvicorn app:app --reload --port 8000
```

Check historical climate:

```bash
curl "http://127.0.0.1:8000/api/climate/history?location_id=pamplemousses-04"
```

Check projections:

```bash
curl "http://127.0.0.1:8000/api/climate/scenarios?location_id=pamplemousses-04"
```

Check invalid-location handling:

```bash
curl -i "http://127.0.0.1:8000/api/climate/history?location_id=invalid-location"
```

Expected outcome: HTTP 404 for the invalid location.

For full, machine-readable field definitions, consult the running FastAPI OpenAPI schema.

## 12. Outstanding M1 Work

Before final production-style handover:

- [ ] Independently validate NetCDF spatial sampling and calendar conversion.
- [ ] Add automatic retries for transient NASA connection failures.
- [ ] Implement a strategy for refreshing incomplete scenario caches.
- [ ] Add automated tests for request validation, caching and source failures.
- [ ] Confirm cache persistence after deployment or restart.
- [ ] Confirm final locations and additional scenarios with the team.
- [ ] Verify all API fields against the latest Pydantic response models.

## 13. Scientific Disclaimer

CropCompass M1 provides climate information to support research, visualization and agricultural planning.

Historical climate datasets and climate projections differ in origin, uncertainty and interpretation.

Projected values must not be represented as deterministic weather forecasts or guaranteed local outcomes.

The module is not a substitute for official meteorological services or professional agricultural guidance.

## 14. In-process M5 Monthly Climate Adapter

The public `/api/climate/history` and `/api/climate/scenarios` response schemas
remain unchanged. Their current contract exposes historical annual/seasonal
summaries and projected annual values, so it is insufficient by itself for
calendar-month Climate Twin comparisons.

The unified app therefore uses M1 service functions directly, without making
HTTP calls to its own API:

- `fetch_monthly_history(latitude, longitude, start_year, end_year)` requests the
  official NASA POWER monthly point API. It validates `T2M` in °C and
  `PRECTOTCORR` in mm/day, converts precipitation with the actual calendar days,
  and rejects any missing/invalid month in the requested period. M5 uses
  2015–2024 as its historical normal.
- `fetch_monthly_projection(latitude, longitude, scenario, start_year, end_year)`
  reuses M1's model registry and NASA NEX-GDDP-CMIP6 NetCDF acquisition and
  parser. It validates `tas` in K and `pr` in kg m⁻² s⁻¹ before conversion,
  supports the configured `ssp245` and `ssp370` scenarios and future years
  2027–2100 (up to 30 years per request), selects the nearest paired NEX grid
  cell by great-circle distance, and converts daily values into twelve
  calendar-month means/totals and an equally weighted multi-model mean. At least
  three complete models are required.

NASA identifies NEX-GDDP-CMIP6 as a bias-corrected, downscaled dataset. M1
performs the daily-to-monthly aggregation but no additional delta adjustment.
The adapter preserves source URLs, retrieval times, requested coordinates,
selected model grid cells, model variants, scenario, period, units, model
uncertainty and excluded-model reasons. NEX source responses are cached with
their original NetCDF bytes and parsed rows; POWER response bodies and source
metadata are cached in M1's SQLite cache.

NASA documentation:

- [POWER monthly/annual API](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/)
- [NASA NEX-GDDP-CMIP6 product and THREDDS access](https://www.nccs.nasa.gov/data-collections/nex-gddp-cmip6/)