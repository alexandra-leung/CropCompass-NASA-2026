# CropCompass 2.0 ? Controlled backend repair results

Date: 15 November 2026 (Mauritius, UTC+04).

## Verdict

**Software regression checks pass; scientific readiness does not receive a full PASS.** The backend supports a controlled demonstration using provenance-bearing cached climate and explicitly illustrative farm inputs. Agricultural feasibility remains `null`: approximate environmental ranges and the current water/soil models do not establish validated agricultural feasibility. No yield, revenue, profit or market-price optimization is used in recommendations.

Final full backend run: **359 passed, 0 failed, 2 skipped**, 33.51 seconds. This compares with **275 passed, 2 skipped** before the merge and **305 passed, 7 failed, 2 skipped** in the recovery audit. All seven original M4 failures are resolved. There are 47 additional collected cases relative to the merged baseline; assertions were updated to explicit corrected contracts, not removed to conceal failures.

## Branch and preservation

Work is on `correction/controlled-backend-stabilization`, created from the existing HEAD `f7804fb`. The audited commit was `ce1da6d`; inspection of `git show f7804fb` confirmed the intervening commit contains only recovery-audit artifacts, with no production source changes. The original working tree was clean. No reset, merge, commit, push or force-push was performed.

All tests, endpoint probes and fixture regeneration ran in separate temporary copies of the backend. Original `backend/data/**` files were SHA-256 checked before/after test and probe runs; the controlled probe reports `original_data_hashes_unchanged: true`. No frontend files, original NASA cache files, reference datasets, historical audit evidence or crop coefficients/ranges were changed. Synthetic climate arrays occur only in clearly identified regression tests. Regenerated files are M4 example responses and their manifest, not scientific evidence.

Windows sandbox permissions prevented creation of nested temporary-copy directories during the first test attempt. Authorized elevated runs of the isolation helpers succeeded. This was an environment failure, not a suppressed test failure.

## Issue disposition

| ID | Repair and evidence | Remaining limitation / review |
|---|---|---|
| R1 | Removed the assumed one-hectare area and all calculated economics from planner outputs. Nullable compatibility fields remain, with `income.status=out_of_scope` and income weight zero. Agricultural `feasible` is always null while scientific validation is absent; model constraint flags remain separate. Missing area, budget, soil or climate are tested independently. | Within-scenario soil/climate/water scores are exploratory indicators, not validated recommendations. M2 owner review required for the clarified semantics. |
| R2 | Seasonal conversion requires explicit complete status and 100% completeness. Excluded periods are exposed. Complete-season totals are conserved by the documented equal-month distribution. Controlled real-data January rain changes from 75.9 to 97.2 mm. | Seasonal totals divided into three equal monthly estimates are not measured monthly rainfall; actual within-season variation is not recovered. |
| R3 | Production M5 adapter requires a finite positive field area, validates the water budget, and forwards latitude, longitude, per-rotation planting windows and provenance. Volume conversion uses the supplied area; northern-hemisphere and explicit calendar paths are exercised. | Missing calendars still use explicitly documented model defaults. They do not establish agricultural feasibility. M2 owner must review calendar semantics. |
| R4 | Processed cache entries pass the same `_to_monthly_climate` and `_validate_m1_provenance` functions as M1 records: units, source, NASA URLs, scenario, period, coordinates, monthly values, model-series and uncertainty structure. Corrupt entries fail closed with DataUnavailable/503. | This validates the recorded provenance contract, not cryptographic authenticity of every cached numeric value. |
| R5 | M5 publishes a null common score scale for scenario-relative planner scores. Stress comparison flags are false and score changes null; Rescue suppresses cross-scenario score comparisons. Within-scenario ranks remain available. | No fixed, scientifically calibrated normalization has been introduced. Absolute water estimates retain model limitations. |
| R6 | Crop IDs, lengths, rotation IDs, calendars, area and numeric inputs are validated. Unknown crops and malformed plans/stress inputs return 422 before climate retrieval. Negative budgets and raw NaN/Infinity/-Infinity are covered. An app-level validation error serializer prevents non-finite input echoes from causing 500. | M3 can still store 4?6-season rotations, but this planner explicitly returns 422 because it only models 1?3 slots. This evaluation restriction needs owner review. |
| R7 | Confirmed actual M3 status: existing farm `ok`; unknown farm `unavailable`; caller context without ID `unavailable` with a skipped-provider reason. Updated stale exact assertions and regenerated M4 examples against running endpoints using real cached/recorded M1 evidence. | Optional Gemini and live external-provider checks remain skipped. No M3/M4 safety check was disabled. |
| R8 | Rescue reads production `details.rotation` as well as legacy `details.analysis.sequence`. Health names the active evaluator and its water-estimation capability, while distinguishing unverified agricultural feasibility. Stress method/limitations no longer claim the production evaluator ignores rainfall/budget. | Rescue returns the M2 sequence, not inferred interventions or a validated rescue calendar. |
| R9 | M3 supplies `demo` and per-field `input_provenance`; FarmContext retains both. Evidence Passport includes exact-value/path records for them. Demo area/rotation are labelled illustrative; non-demo values remain caller-supplied/unverified. | Additive M3/M4 contract fields need owner review. Source attribution does not certify farmer inputs. |
| R10 | Rejects unsupported 4?6-slot evaluation, overlapping months, malformed windows and crop/window mismatches. Wrap-year windows work. Crops exceeding their window are explicitly flagged and `calendar_complete=false`; no full modeled harvest is emitted. | Full-duration crop simulation and concurrent crops remain unimplemented. Water totals for a clipped window are incomplete and must not be interpreted as full crop demand. |
| R11 | Example economics have no effect on ranking or recommendations; changing prices/costs yields identical planner output. Approximate-range/source qualifications and exploratory recommendation status are explicit. No reference data was edited. | **Scientific portion unresolved:** row-level numerical verification, local calibration and owner acceptance of environmental ranges remain outstanding. No evidence was invented or coefficients changed. |
| R12 | M1 stale fallback adds source caveat, cache timestamp and age without rewriting payloads in SQLite. POWER archive cache no longer claims freshness. Processed climate uses a method-version/configuration signature plus a 30-day reuse window; legacy/expired/signature-mismatched valid entries reacquire through M1. Corrupt entries are rejected first. | Historical candidate files are reusable archives, with age explicitly unverified, not expiring operational forecasts. The 30-day processed-cache policy is an engineering choice requiring M1/M5 owner review. The existing tracked runtime-cache location is retained; migration/removal remains separate work. |

## Before/after controlled diagnostics

See [compact probe output](CODEX_CONTROLLED_REPAIR_PROBES.json). The unchanged recovery harness was copied into a temporary backend and run with M5 offline, outgoing async HTTP blocked, and M1 cache TTL extended only in that process. This is a current-code/cache integration check, **not fresh live NASA retrieval**.

| Probe | Recovery audit | Repaired result |
|---|---|---|
| No climate/budget/area | feasible=true, assumed 1 ha, profit Rs 1,075,000 | feasible=null, area=null, area_assumed=false, financial values=null |
| Wrong SSP/non-NASA processed-cache provenance | accepted | rejected by regression probes; source, units, period and coordinate corruption also rejected |
| Partial boundary DJF | January rainfall 75.9 mm | 97.2 mm; excluded 2021-DJF and 2026-DJF reported |
| Cross-scenario scores | falsely comparable | all nine replayed comparisons false; score_change=null |
| Unknown crop /plans | HTTP 500 | HTTP 422 |
| Unknown crop /stress-test | HTTP 500 | HTTP 422 |
| NaN/Infinity raw JSON | newly reproduced HTTP 500 during repair testing | HTTP 422 for both endpoints |
| Rescue sequence | pending despite production M2 rotation | all three real production sequences present |
| M4 M3 contract | obsolete not_implemented expectations | existing=ok; unknown/caller-context=unavailable |
| M5 Evidence Passport | exact value/path equality | climate_twin=true and stress_tests=true; M3 provenance equality also tested |

Valid cached requests remain HTTP 200: backend/M5 health, M3 farms, M1 history/projections, legacy M2 rotation/generate/suitability, M2 plans, M5 Twin/stress/rescue, M4 analyze/evidence/template assistant. No duplicate route registration was introduced.

A missing-input plan can still have a numeric structural/soil score (the replay shows 1.0). This is explicitly an exploratory relative indicator, **not feasibility, probability of success or a farmer recommendation**. Positive agricultural feasibility is not inferred from it.

## Verification record

- Group A initial focused regressions: 7 passed.
- Group B/C combined focused regressions: 30 passed (after correcting the new test's field names to the actual `changes`/`score_change`/`candidates` schema).
- M3 live contract check before fixture regeneration: 3 passed, 16 deselected.
- Group D after regeneration: 94 passed, including the seven original failures and traceability checks.
- First full run: 344 passed, 1 failed, 2 skipped. The failure was the exact M3 key-set assertion, updated to explicitly include the two new fields.
- Subsequent full runs: 349 and then 356 passed, 2 skipped as additional regressions were introduced.
- Raw non-finite JSON probes then reproduced 3 failures (422 error serialization became 500); these were fixed in `app.py`.
- **Final full run: 359 passed, 2 skipped in 33.51 seconds.** [Full pytest output](CONTROLLED_LATEST_TESTS.txt).
- Skips: optional `google.genai.types` absent; opt-in `M4_LIVE=1` external-provider check not enabled.
- `git diff --check` passes. Git emits informational LF/CRLF conversion warnings only.

Reproduction from the repository root:

```powershell
backend/.venv/Scripts/python.exe backend/qa_reports/run_controlled_checks.py
backend/.venv/Scripts/python.exe backend/qa_reports/run_controlled_diagnostics.py
```

The helpers make fresh temporary copies and check source-data preservation. Do not run the original recovery harness directly against the working backend. Fixture regeneration is separately reproducible with `regenerate_controlled_examples.py`; it copies back only named M4 example responses and their manifest. Tests assert exact output contracts, rejection behavior, completeness, provenance and arithmetic; scientific data assertions were not weakened.

## Owner coordination and compatibility notes

Owner guidance/review routing was requested during this work; no response or owner approval was received. These are local, uncommitted proposals for review, not owner-approved contracts. No message was sent to teammates without authorization.

**M2 owner:** review nullable agricultural feasibility, separated model constraints, excluded-season metadata, explicit calendar validation, 1?3-season evaluation limit, disabled economics, exploratory range labels and within-scenario-only scoring. Existing financial keys remain nullable rather than disappearing; price/cost request fields are still accepted but cannot influence results. M5 now requires positive area for m3/mm conversion. Repeated crop IDs remain legal monoculture; duplicate rotation identifiers are rejected. These are intentional behavior changes, not silent schema changes.

**M3 owner:** review the additive `demo: bool | null` and `input_provenance: dict` boundary fields. Existing source and farm fields are preserved. Stored 4?6-season farms are not deleted or migrated; planner rejection is explicit. Existing explicit rain-only inputs remain distinct from missing/unknown irrigation inputs.

**M4 owner:** review new provenance evidence records, corrected provider-status expectations and regenerated response fixtures. Caller context is retained when no usable profile is returned. Exact upstream value/field-path checks remain enforced.

**M1/M5 owners:** review processed-cache method/configuration invalidation and the 30-day operational reuse window, retained historical archive policy, source-failure behavior and later runtime-cache relocation. Invalid processed provenance returns 503 rather than trusting or silently relabelling it.

## Remaining scientific limitations and unaddressed work

The software defects are repaired or contained, but the application is not scientifically ready for farmer recommendations. R11's underlying reference verification is unresolved because verifiable row-level source evidence and owner review are absent. Approximate ECOCROP ranges, heuristic soil weights, temperature-based ET0 and 75% irrigation efficiency remain exploratory. No authoritative coefficients or ranges were changed. Missing legacy crop reference fields remain missing. FAO stage/source-context reconciliation remains with the data owner.

Full crop-duration/concurrent-calendar simulation, field-verified soil and water inputs, local crop calibration, and verified daily ET0 are not supplied by these repairs. Yield, revenue, profit and market-price optimization remain out of scope. Existing GAEZ/SoilGrids/FOTW/remote-sensing gaps are not claimed as implemented. Live NEX availability and optional external LLM behavior were not revalidated. Tracked runtime cache relocation was not performed because preservation and scoped repair did not authorize deleting the cache artifact.

**Readiness: regression-clean controlled backend demonstration; owner review and scientific validation required before farmer-facing recommendations.**

## Exact changed files

Tracked files changed (all backend):

- `backend/agricultureM2/plan_engine.py`
- `backend/agricultureM2/plans_routes.py`
- `backend/app.py`
- `backend/climateM1/services/cache.py`
- `backend/intelligenceM4/evidence_passport.py`
- `backend/intelligenceM4/fixtures/example_analyze_response.json`
- `backend/intelligenceM4/fixtures/example_blind_spots_response.json`
- `backend/intelligenceM4/fixtures/example_evidence_response.json`
- `backend/intelligenceM4/fixtures/manifest.json`
- `backend/intelligenceM4/providers/farm_provider.py`
- `backend/intelligenceM4/schemas.py`
- `backend/mappingM3/farm_profile.py`
- `backend/resilienceM5/m2_adapter.py`
- `backend/resilienceM5/rescue_mode.py`
- `backend/resilienceM5/routes.py`
- `backend/resilienceM5/scenario_engine.py`
- `backend/resilienceM5/stress_test.py`
- `backend/tests/test_m2_plan_engine.py`
- `backend/tests/test_m3_mapping.py`
- `backend/tests/test_m4_blind_spots.py`
- `backend/tests/test_m4_integration.py`
- `backend/tests/test_m5_resilience.py`

New files:

- `backend/tests/test_controlled_repairs.py` ? focused integrity, calendar, cache lifecycle, API and provenance regressions (44 parametrized cases).
- `backend/qa_reports/run_controlled_checks.py` ? isolated pytest runner and data-hash guard.
- `backend/qa_reports/run_controlled_diagnostics.py` ? isolated audit replay and compact result capture.
- `backend/qa_reports/regenerate_controlled_examples.py` ? isolated M4 example regeneration.
- `backend/qa_reports/CODEX_CONTROLLED_REPAIR_PROBES.json` ? after-repair diagnostic results.
- `backend/qa_reports/CONTROLLED_LATEST_TESTS.txt` ? final full pytest output.
- `backend/qa_reports/CODEX_CONTROLLED_REPAIR_RESULTS.md` ? this report.

No modifications are committed or pushed. All remain available for review.
