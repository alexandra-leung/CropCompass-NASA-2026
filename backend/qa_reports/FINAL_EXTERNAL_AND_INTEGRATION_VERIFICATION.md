# Final External and Integration Verification

## Scope and verdict

Backend-only verification of the NASA-backed M1 climate service, M2 demo
workflow, M5 Climate Twin, M4 Evidence Passport pass-through, scientific
comparability, sensitivity, and the backend test suite. No frontend files were
changed and no commits were created.

**Readiness verdict: CONDITIONAL PASS.** The M1/M2/M5-to-M4 integration path
works, including a full-period M5 Climate Twin and exact M4 evidence
traceability. It is not ready to support a farmer-specific crop or irrigation
recommendation: required farmer inputs are absent, M2 suitability reference
ranges are incomplete, M3 farm profiles are not implemented, and the M5 stress
test/rescue workflow requires verified farmer inputs.

## External data and scientific checks

| Check | Result |
|---|---|
| M1 NASA POWER history | HTTP 200 at registered `pamplemousses-04` coordinates (-20.103, 57.575). The 2021–2025 response identifies NASA POWER and reports `missingData: false`. M5's M1 adapter also returned 2015–2024 NASA POWER monthly history with its source URL and no missing data. |
| M1 NEX projections | HTTP 200. All five configured models reported success for the registered location's 2030, 2040, and 2050 projections. Repeating the same scenario request returned an identical response. |
| Full-period M5 Twin | The initial 2041–2060 request encountered DNS/source retrieval errors. A retry returned HTTP 200 for SSP245, 2041–2060, with 10 candidate locations, NASA POWER history, and NASA NEX future provenance. The projected payload records 200 NASA NEX source URLs and `missing_data: false`. |
| Comparable NEX history/future | Compared 1995–2014 historical NEX with 2041–2060 SSP245 NEX at the same registered coordinates, using the same four complete models. The fifth model, MRI-ESM2-0, was excluded rather than imputed because its 1995–2014 historical source was incomplete. |

The four-model equal-weight mean comparison was:

| Measure | Historical 1995–2014 | SSP245 2041–2060 | Difference |
|---|---:|---:|---:|
| Annual precipitation | 1,785.38 mm/year | 1,788.07 mm/year | +2.68 mm/year (+0.15%) |
| Annual mean temperature | 23.087 °C | 24.136 °C | +1.049 °C |

The individual models do not agree on the precipitation direction: ACCESS-CM2
is lower by 4.23%, while the other three are higher by 0.70% to 2.55%. These are
model-period means, not probabilities, field forecasts, or observed climate
changes. Historical NEX is used here as a model reference; it is deliberately
not mixed with NASA POWER observations.

For each model-year, the calculation selected the nearest paired NEX grid cell,
required a complete daily year, converted precipitation flux (`kg m-2 s-1`) by
multiplying by 86,400 and summing daily values, and converted temperature from
Kelvin to Celsius before annual averaging. Four of five model series supplied
complete common 20-year windows. Exact source URLs and annual values are in
[nex_historical_reference_comparison.json](./nex_historical_reference_comparison.json).

## Demonstration workflow and sensitivity

The reproducible request/response record is
[live_external_integration_workflow.json](./live_external_integration_workflow.json).
It includes the original transient M5 failure, the successful full-period
retry, source provenance, M2 demo outputs, and the M4 request/response. The M2
rotation (`maize, cowpea, cabbage`) is explicitly marked as a QA fixture, not
farmer-entered data.

- M1 SSP245 ensemble mean at 2050: 1,839.88 mm/year and 24.03 °C.
- M1 SSP370 ensemble mean at 2050: 1,725.62 mm/year and 24.22 °C.
- SSP370 minus SSP245 at 2050: -114.26 mm/year and +0.19 °C.
- SSP245 2050 minus 2040: -1.22 mm/year and +0.32 °C.
- Repeating the same M1 scenario request returned identical output.
- M2 rotation and alternative-generation calls returned HTTP 200. Alternative
  ranking remained `not_calibrated` and agronomic feasibility remained
  `not_evaluated`.
- M2 suitability returned `insufficient_data` for maize, cowpea, and cabbage;
  each result identified missing temperature and soil-pH inputs. No values
  were supplied or inferred to force a suitability result.

The full-period M5 Twin was submitted unchanged to M4 `/evidence`. M4 returned
HTTP 200 and emitted `ev-resilience-climate-twin` with
`provenance.field_path = "resilience.climate_twin"`; the evidence value exactly
matched the M5 response. M4 retained the unresolved stress-test limitation and
reported `requires_further_validation`.

## Blocked stages and remaining limitations

- **M5 stress test and rescue mode: blocked.** No verified farmer rotation or
  farmer-entered irrigation budget was available. The prior 100 m³ example is
  not used as farmer evidence. Rescue mode was not run because it requires a
  stress-test result.
- **Irrigation sensitivity: blocked.** M1 does not provide a verified daily
  reference ET0 series for M2, and no farmer water budget was provided.
  Water Wallet's crop ETc calculation is not an irrigation-requirement
  calculation.
- **Crop suitability: insufficient evidence.** The crop catalog's temperature,
  rainfall, and soil-pH reference ranges are blank, and this workflow supplied
  neither temperature nor soil pH to M2. A demo rotation is not a verified
  farmer rotation.
- **M3 farm profiles: not implemented.** The M4 analysis used only explicit
  caller context; no farm profile was fabricated.
- **Model coverage:** MRI-ESM2-0 is excluded from the full historical/future
  comparison because NASA NEX historical precipitation/temperature retrieval
  was incomplete for 2012–2014. The four-model comparison is reported with that
  exclusion visible.
- **M5 status semantics:** M5 is a separate-call service, not an automatic
  `/analyze` call. M4's `/analyze` module entry therefore remains
  `not_implemented`; bundle-based M4 reporting now describes supplied Twin and
  stress-test results as unavailable, partial, or complete instead of treating
  an obsolete in-process M5 function as the implementation test.

## Code and contract corrections verified

- Added service-layer caching for daily M1 history so in-process M4 calls do
  not bypass route-level caching.
- Made M1 scenario identifiers compatible with registry-defined values.
- Corrected M4 M5 reporting and blind spots for the separate-call workflow.
  M5 output status is now determined from the results actually present in the
  bundle; an incomplete Twin/stress-test set is reported as partial.
- Corrected M4 water and cache explanations and updated the API contract and
  generated examples.
- Tightened Water Wallet ET0 validation to reject booleans and non-finite
  values.

## Test results

- Focused M4 regression tests: **139 passed, 1 skipped**.
- Full backend test suite: **275 passed, 2 skipped**, with one existing
  Starlette/httpx deprecation warning.
- Full M5-to-M4 pass-through was also exercised against the live unified
  FastAPI application and verified by exact value and field-path equality.

**CONDITIONAL PASS**
