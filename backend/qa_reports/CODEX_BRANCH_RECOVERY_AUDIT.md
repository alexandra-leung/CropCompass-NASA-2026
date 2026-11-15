# CropCompass 2.0 ? branch recovery and backend revalidation

Audit date: 15 November 2026 (Mauritius, UTC+04). Audited HEAD: `ce1da6d` on `kentish`.

## Verdict

**Repository preserved; backend starts and supports a controlled, cached-data demonstration, but the branch is not regression-clean or ready for farmer recommendations.** Current tests: **305 passed, 7 failed, 2 skipped**. The immediately preceding commit `b1cb43b` was independently rerun: **275 passed, 2 skipped**. The seven failures concern M3 capability/status expectations and obsolete M4 example outputs after the merge. Additional diagnostic probes found production defects that the passing tests do not cover.

No production source, frontend, existing dataset, tracked cache, test, commit or branch was changed by this audit. Only new audit documentation/evidence was created. Tests and workflow requests ran in a temporary backend copy; baseline tests ran in a separate `git archive` extraction. No resets, rebases, merges, commits, pushes or fetches were performed. Remote branch conclusions refer to locally available remote-tracking refs, not a fresh GitHub fetch.

## 1. Git assessment and ownership

- Current branch/upstream: `kentish` / `origin/kentish`, both at `ce1da6d` (merge authored by Alexandra Leung Dat Wan). Initial working tree clean; `git diff --check` clean.
- `origin/main` is `b8173f4`; local `main` is `c1c64c7`, one commit behind. Actual HEAD/main merge base: `b8173f4`.
- Current team integration ref `origin/Alexandra` is `7605af4`, HEAD's second parent and its actual merge base with that ref. Do not confuse uppercase `Alexandra` with lowercase `origin/alexandra`, which remains at `c1c64c7`.
- Local reflog says the branch was **created from `origin/kentish` at `c1c64c7`**, then advanced to `b8173f4`. It does not prove that the branch was originally created from Alexandra. Subsequent integration came through PRs #3/#4/#5 and merge `ce1da6d`.
- No dedicated current recovery backup branch exists. There **is** an older `refs/original/refs/heads/kentish` at `3ce0291`; reflog records an earlier `filter-branch: rewrite` before `6277b63`. This predates this audit and is not a backup of current HEAD. Recommend creating a named backup reference at `ce1da6d` before any approved fixes; none was created here.
- First-parent development milestones: `d77a4a8` M1/M5; `4883de3` cache ignore; `9b31d0b` M2/M5; `b9602c8` M4/M5; `4874480` first audit; `b1cb43b` second audit; `ce1da6d` teammate merge.
- Commits reachable from HEAD but not `origin/Alexandra`: `ce1da6d`, `b1cb43b`, `4874480`, `b8d2add`, `b9602c8`, `aaec3d0`. The older M1/M2/M5 integration commits are already shared ancestry with Alexandra, not exclusively feature-branch work.
- Teammate merge content is evidenced by `304b862`, `2c995bc`, `c289ac4`, `04c69b5`, `ee97a5f`, `903bf89`, `4dc2a25` (recorded author Suhaasinee Sookaul), merged into Alexandra in `7605af4`, then into kentish in `ce1da6d`. M4 commits record Shruti-Devi; M2 upload `be92962` records the khushi branch contribution.
- Agent-host checkpoint refs exist in `git log --all`; that is evidence of agent activity, **not proof that each checkpoint or Copilot-authored line was pushed**. Human commit author metadata cannot establish AI authorship. The user's attribution to Copilot cannot be independently assigned file-by-file from Git alone.

### Diff scope

| Comparison | Result |
|---|---|
| `b8173f4..HEAD` (main / actual base) | 167 files; 80,751 insertions, 4 deletions |
| `7605af4..HEAD` (Alexandra / actual base) | 130 files; 25,840 insertions, 3,754 deletions |
| `b1cb43b..HEAD` (merge effect) | 58 files; 16,371 insertions, 4 deletions |

[File-by-file inventory](CODEX_BRANCH_RECOVERY_FILE_INVENTORY.md) lists the union of both comparisons: **259 paths**, including deleted nested files, with status, latest relevant commit/author, classification and reason. ?Necessary cross-module integration? describes the integration purpose, not blanket approval of every changed algorithm. Frontend paths were inventoried from Git only and never modified.

### What was pushed, and what is actually suspicious?

The latest merge legitimately brought in the frontend, M3, M2 plan engine, M5 evaluator replacement and new data files. **There is no evidence that all of this was an accidental push.** Intent requires owner confirmation.

Concrete repository hygiene candidates:

- `backend/m5_stress_result.json` (~2 MB) and `backend/m5_twin_result.json` (~260 KB), introduced in earlier M5 integration history, are captured outputs, not production source.
- `backend/data/processed/m5_farm_climate_cache.json` (~605 KB) is tracked runtime cache added through the later teammate work (`903bf89`, updated `4dc2a25`). Production code writes this path.
- `b1cb43b` added `live_external_integration_workflow.json` (20,691 lines) and `nex_historical_reference_comparison.json` (4,138 lines). These account for much of the large patch and are audit evidence, not algorithm rewrites.
- The duplicated `backend/CropCompass-Nasa/` tree, including bytecode and an old SQLite database, was removed in `4874480`; it remains visible as deletions relative to Alexandra. Review the historical files before any further cleanup. Do not restore the duplicate tree wholesale.
- No currently tracked `.pyc` or SQLite database was found. The local ignored `backend/data/climate_cache.sqlite3` is ~350 MB with 705 rows; it was copied for tests and not overwritten.
- Tracked environment files are examples with empty API key fields. Filename history checks for actual `.env`, private-key/credential filenames, and a bounded current-tree secret-signature scan found no credential evidence. This is not a guarantee against all secret formats or all historical blobs.
- Git preserves prior contents; intentional overwrites versus accidents cannot be inferred from changed paths alone. The concrete problematic changes below have identifiable behavioral evidence.

## 2. Actual architecture and contracts

`backend/app.py` imports and registers one FastAPI application: M1 climate router, legacy M2 router, new M2 plans router, M3 farms router, M4 intelligence router and M5 resilience router. App import and OpenAPI generation succeed; **26 OpenAPI paths, no duplicate path/method registrations**. AST parsing found no syntax errors in 78 Python files. This does not mean every dormant code path was dynamically exercised.

M1 owns farm history and future projection acquisition. M5 `m1_adapter.py` calls M1 services in process, checking units, NASA hosts, coordinates, periods, scenario, model count and uncertainty. M5 acquires only its candidate-location history independently from POWER. Normal conversion paths use monthly mean daily rainfall ? actual days, and NEX precipitation flux ? 86,400 with Kelvin ? 273.15. Monthly projection validation checks full calendars/paired cells. Annual scenario outputs can expose incomplete years with flags; downstream consumers must respect those flags.

M5 now registers **`evaluate_with_plan_engine`**, replacing `evaluate_m2_scenario` at app startup. It reuses M2, but M2 has **two different agricultural engines**: legacy rotation/suitability calls used by M4, and scored `/api/agriculture/plans` used by the newer M5 adapter. The former preserves missing reference ranges and uncalibrated ranking; the latter reads approximate ranges, models irrigation and uses example economics. A valid HTTP response does not resolve that scientific disagreement.

M3 now supplies coordinates, field area, soil data/provenance, current rotations, irrigation budget conversion and a persistent farm store. M4 dynamically detects `get_farm_profile`. With a valid farm ID, audited `/analyze` reports M3 `ok`; without an ID it reports unavailable/skipped caller-context behavior. The module docstring claiming M3 is unimplemented is stale.

M4 `/analyze` still does **not** call M5 automatically and does not consume `/plans`. Its M5 provider explicitly reports the separate-call contract. Call M5 separately, then submit unchanged payloads as `resilience.climate_twin` and **`resilience.stress_tests` (plural list)** to `/evidence`. Both exact value/field-path pass-through checks succeeded. Evidence traceability proves faithful copying, not scientific validity. The template assistant works; optional Gemini SDK is absent and external LLM behavior was not verified.

Shared `shared/schemas.py` remains an empty placeholder; schemas are module-local, with M4 importing M1 models. Startup found no active circular-import failure. M4 provider exceptions/timeouts degrade to unavailable, while new plans/M5 adapter validation has uncaught `KeyError` paths. M1/M5 disk caches and M3 store are file-relative; M3/M5 have selected env overrides, M1 SQLite does not. `.env.example` documents only part of current configuration. `CORS_ORIGINS` exists but is not installed as middleware; no browser-origin deployment validation was performed. M2's optional HTTP climate adapter uses `M1_API_BASE_URL`; primary audited integration is in-process.

## 3. Automated baseline and regressions

Python 3.13.5, repository `backend/.venv` dependencies, isolated copies. Command: `python -m pytest -q tests -ra --basetemp=<unique temporary path> --junitxml=<audit output>`.

| Run | Passed | Failed | Skipped | Setup/collection errors | Warnings |
|---|---:|---:|---:|---:|---|
| `b1cb43b` archive, current environment | 275 | 0 | 2 | 0 | None reported |
| `ce1da6d` copied backend | 305 | 7 | 2 | 0 | None reported |

A first sandbox run had 117 temp-fixture permission errors (189 passes, 7 failures, 1 skip, 2 warnings); a second unique-directory attempt still hit Windows sandbox permissions. These were environment failures, not the final baseline. The authorized outside-sandbox isolated rerun resolved them. Neither tests nor implementation was weakened. The historical Starlette warning was not emitted in the authoritative rerun.

Test delta: 314 collected versus 277, **37 net additions**: 13 M2 plan tests and 24 parametrized M3 cases. One M3 provider test was renamed/replaced to assert unknown-farm unavailability; therefore node-ID comparison shows 38 added and 1 removed. No wholesale removal of old test files. Seven previously passing tests now fail:

- `test_m4_blind_spots.py::test_real_data_blind_spots`
- `test_m4_blind_spots.py::test_real_data_module_status`
- `test_m4_blind_spots.py::test_m3_missing_profile_and_m5_missing_results_are_info`
- `test_m4_blind_spots.py::test_saved_blind_spots_example_matches_current_output`
- `test_m4_evidence.py::test_saved_example_matches_current_endpoint_output`
- `test_m4_integration.py::test_end_to_end_analyze`
- `test_m4_integration.py::test_saved_analyze_example_is_consistent`

Cause: M3 implementation in `304b862`, introduced into this branch by `ce1da6d`, changes capability detection and removes the old M3-not-implemented blind spot. Existing fixtures/assertions were not consistently updated. Do not disable M3 to restore tests. Verify correct statuses with/without a farm ID, then update expectations and regenerate examples after approval.

Skipped: optional `google.genai.types` import and opt-in `M4_LIVE=1` provider check. See [test log](CODEX_BRANCH_RECOVERY_TEST_RESULTS.txt), [JUnit](CODEX_BRANCH_RECOVERY_TEST_RESULTS.xml), [baseline log](CODEX_BRANCH_RECOVERY_BASELINE.txt), [exact test delta](CODEX_BRANCH_RECOVERY_TEST_DELTA.json).

## 4. Scientific datasets: presence, use and source verification

[Static evidence](CODEX_BRANCH_RECOVERY_STATIC_EVIDENCE.json) inventories every actual `backend/data` file with size, tracking status and hash (21 files including empty placeholders). A source URL alone is not verification of its numeric contents.

| Dataset | Local/API presence and production use | Variables, coverage and processing | Verification / missing data / limits |
|---|---|---|---|
| NASA POWER historical | `climateM1/services/history.py`; daily/monthly API; ignored SQLite; ten raw candidate JSON files via `scenario_engine.PowerClient` | T2M ?C, PRECTOTCORR mm/day; regional gridded locations; daily 2021?2025 demo, monthly 2015?2024 M5; actual-day monthly totals and seasonal/annual summaries | One fresh 2024 point retrieval HTTP 200; real payload normalized successfully with no missing months. Full 2015?2024/2021?2025 workflows were cached, not freshly downloaded. Sentinel ?999 handled. Seasonal boundary records remain incomplete. |
| NASA NEX-GDDP-CMIP6 | `services/projections.py`, model registry, SQLite and tracked M5 processed cache; actively used by Twin/stress | `pr` kg m?2 s?1 ? mm; `tas` K ? ?C; SSP245/SSP370; five configured models; annual 2030/2040/2050 plus full monthly 2041?2060 demo. Nearest paired grid, complete monthly series, model mean/spread | Full workflow succeeded from existing provenance-bearing cache. One bounded live ACCESS-CM2 2041 subset timed out: no new live projection claim. Historical report's four-model 1995?2014 comparison was inspected, not rerun. POWER-versus-NEX baselines are different products/periods, not directly attributable climate-change estimates. |
| FAO-56 Kc and growth stages | Seven rows in `crop_water_coefficients.csv`; used by Water Wallet and new plan engine; `crop_catalog.csv` references same chapter | Dimensionless initial/mid/end Kc and stage days; reference climates/planting seasons, not Mauritius-calibrated coefficients | Original FAO chapter retrieved; ETc=Kc?ET0 and selected stage rows supported. Local row selection/context is incomplete; cowpea stage entries sum to 100 while the cited table displays a 110-day total for that row. Requires source/row reconciliation, not invented correction. No verified daily ET0 input series for Water Wallet. |
| Legacy crop catalog | Seven local crops loaded by `crop_catalog.py`, rotation engine and legacy suitability | Family, nitrogen-fixing flag, growth days; temperature ?C, rainfall mm and pH reference columns | All temperature/rainfall/pH reference fields blank. `/suitability` returns insufficient data even with supplied temperature/pH. FAO-56 chapter is not proof of those missing ranges. |
| ECOCROP approximate ranges | `crop_ranges.csv`, loaded by `plan_engine.crops`, actively determines suitability | Seven temperature optimal/absolute ranges and pH optima, no rainfall ranges; global crop summaries with no cultivar/season version | Rows explicitly say approximate/verify before field use. Linked FAO landing page had no readable crop records; exact numerical ranges **not independently verified**. Does not populate or fix legacy catalog. |
| Crop economics | `crop_economics.csv`, actively used for income, profit and rank | Mauritius 2024 aggregate production/area; sweet potato 2023; t/ha, example Rs/kg and Rs/ha. Cowpea uses beans-and-peas proxy | PDF fetch failed via browser and bounded direct request; original numeric tables not reverified. CSV arithmetic/labels inspectable, but example prices/costs and fixed climate penalties are not validated farm economics. No geographic adaptation for global farms. |
| Farmer inputs | `data/farms/demo_farms.json`, M3 JSON store, `data/fixtures/m5_test_rotation_request.json` | Area ha, coordinates degrees, pH, rotations, budget mm/season ? m? using ha?10 | Seed explicitly illustrative; default boundaries are placeholders; no actual verified farmer inputs supplied. M3 adapter drops demo/source-detail flags when creating M4 context. |
| FAO GAEZ spatial suitability | `gaez_layers.csv` empty, `providers/gaez.py` empty, raw directory `.gitkeep` only | No raster variables, geographic subset or time slice loaded | Mentioned/planned, not downloaded or used in a spatial calculation. ECOCROP range file is not a GAEZ suitability raster. |
| SoilGrids | Mentioned in README/soil provenance labels | No downloaded soil layers or active acquisition provider found | Soil values are supplied/illustrative, not an actual SoilGrids calculation. |
| Fields of The World | Named as planned source in boundary code | No local field-boundary dataset loaded | Planned, not implemented as FOTW inference; OSM lookup/manual geometry are distinct. |
| MSIRI suitability, Sentinel-2, GPM IMERG, SMAP | No matching data/provider implementation found in audited backend | No loaded variables or spatial/temporal coverage to report | Requested strategy items, not implemented data sources. Do not claim their use. |

FAO source reviewed: [FAO-56 chapter 6](https://www.fao.org/4/x0490e/x0490e0b.htm). The chapter supports the coefficient methodology and emphasizes stage/climate context; it does not validate this application's ranking, profit or crop recommendations. [Live source checks](CODEX_BRANCH_RECOVERY_LIVE_CHECKS.json) record exact URLs, outcomes and controlled timeouts; [POWER response](CODEX_BRANCH_RECOVERY_POWER_SAMPLE.json) preserves the small fresh sample. No repeated bulk NEX downloads were attempted.

## 5. Member readiness and end-to-end results

OpenAPI was read before requests; [schema snapshot](CODEX_BRANCH_RECOVERY_OPENAPI.json). Existing caches were copied, M1 cache TTL extended only in the audit process, HTTP blocked for the workflow and M5 set offline. Thus the following are **cached-source integration tests**, not fresh live retrieval. Farm/rotation/budget choices are explicitly QA-only.

| Feature | Observed outcome | Readiness classification |
|---|---|---|
| M1 historical acquisition | Cached route 200; fresh 2024 POWER sample 200 and normalized | Working/tested; only bounded live sample verified |
| M1 projections | Cached route 200; unit/calendar checks present; live subset timeout | Working from cache, live availability not revalidated |
| M2 legacy catalog/rotation/generate | HTTP 200; alternatives remain uncalibrated | Working/tested structural rules, scientific ranking partial |
| M2 legacy suitability | HTTP 200, insufficient data with temp=25 and pH=6.5 | Blocked by missing reference ranges |
| M2 Water Wallet | Service exists/tested; no dedicated route in current OpenAPI; missing ET0 rejected | Computational component working; actual farmer workflow blocked |
| M2 plans | HTTP 200 with demo farm; modeled water/score/income | Partially implemented, externally unvalidated, known defects below |
| M3 profiles/coordinates/area/soil/rotations/budget | `/api/farms` 200; M4 profile integration 200; new tests pass | Working/tested with demo inputs; field boundaries/soil externally unvalidated |
| M4 analyze/evidence/blind spots/assistant | Cached analyze 200, M1 ok/M2 partial/M3 ok/M5 not_implemented; evidence and template assistant 200 | Working core; seven stale contract/example checks fail; no automatic M5 |
| M5 Climate Twin | 200, SSP245 2041?2060, all ten candidates, exact M4 pass-through | Working cached/tested; limited candidate pool, not global agronomic analog validation |
| M5 stress test | 200, QA 0.6 ha/3,600 m? baseline and 50% hypothetical reduction, real cached climate | Working computational path; farmer validity and agronomic calibration unresolved |
| M5 Rescue Mode | 200; passes/unknowns/failures sorted deterministically | Partial: adapter sequence mismatch leaves all sequences pending; relative score comparison unsafe |

[Workflow evidence](CODEX_BRANCH_RECOVERY_WORKFLOW.json) stores statuses/provenance and [reproduction harness](CODEX_BRANCH_RECOVERY_REPRODUCE.py) records exact requests. **Run that harness only inside a copied backend**, as it imports the real app and may invoke runtime caches. Both Twin and `stress_tests` reached M4 unchanged with matching field paths. The full raw temporary workflow capture remains outside the repository to avoid another large generated commit.

## 6. Confirmed regressions and smallest corrections

Severity describes backend/scientific impact, not blame. Commit attribution below identifies introduction or integration, not AI authorship.

| ID / severity | File and commit | Before ? current evidence | Smallest correction and proof required |
|---|---|---|---|
| R1 High | `agricultureM2/plan_engine.py`, `04c69b5` (economics later `ee97a5f`, `903bf89`), merged `ce1da6d` | Legacy paths retain unknown feasibility. New no-climate/no-budget/no-area probe returns `feasible=true`, score 0.786, assumed 1 ha and Rs 1,075,000 profit | Preserve unknown feasibility and explicit missing-input status; separate demo economics from evidence-backed ranking. Test missing climate, water, area, prices and ranges independently; no false success. |
| R2 High | `plan_engine.py::monthly_climate`, `04c69b5` | New planner ignores M1 seasonal completeness flags. Actual 2021?2025 cache has 65.6% and 34.4% boundary DJF records; current January rainfall 75.9 mm versus 97.2 mm using complete DJF records | Exclude/report incomplete seasons or aggregate complete monthly data. Test boundary seasons/missing days and conservation of monthly totals. Do not hide excluded data. |
| R3 High | `resilienceM5/m2_adapter.py::evaluate_with_plan_engine`, `ee97a5f` | Replaces explicit-null legacy feasibility with new model; defaults missing/zero area to 1 ha, omits latitude and planting windows when calling M2 | Require validated positive area, propagate coordinates/calendar and input provenance. Compare plans/M5 outputs for the same northern/southern farm, calendar, price/cost and budget. |
| R4 High | `scenario_engine.py::get_farm_climate`, `903bf89` | New processed-cache hit bypasses adapter's source/scenario/period validation. Isolated in-memory corruption probe accepted `ssp999` and non-NASA URL for an SSP245 lookup | Validate cached provenance just like fresh M1 output; version keys by method/source/model config; test corrupt/mismatched cache and safe miss behavior. No production cache was tampered with. |
| R5 High | `plan_engine.py`, `stress_test.py`, `rescue_mode.py`, activated `ee97a5f` | Water/profit indices renormalize per scenario, but fixed `m2_plan_engine_0_1_relative` label causes stress/rescue to mark cross-scenario scores comparable | Use common fixed normalization or declare cross-scenario score deltas unavailable. Test identical absolute results under changed candidate normalization; compare absolute water/profit separately. |
| R6 Medium | `plans_routes.py`, `m2_adapter.py`, `04c69b5`/`ee97a5f` | New plans and stress routes accept arbitrary crop lists; `cat[cid]` raises uncaught `KeyError`; both invalid-crop probes returned 500 | Validate IDs, lengths, area and finite values before data retrieval; return 422. Test empty/unknown crop IDs, duplicate IDs, invalid area, malformed rotation structure. |
| R7 Medium | M4 tests/fixtures listed above; trigger `304b862`/`ce1da6d` | Baseline 275/0/2 ? 305/7/2; M3 capability is now real, examples still describe absence | Review desired statuses; update precise assertions and regenerate fixture outputs, preserving traceability checks. Full suite plus with-ID/without-ID/unknown-ID cases. |
| R8 Medium | `stress_test.py`, `routes.py`, `rescue_mode.py`, adapter change `ee97a5f` | Health still says feasibility unsupported; response limitations say M2 ignores rainfall/budget although it now uses them. Rescue expects `details.analysis.sequence`, new adapter provides `details.rotation`, so all sequence statuses remain pending | Derive capability/method text from active evaluator and normalize sequence schema. Test the registered production evaluator through stress?rescue, not only isolated legacy adapter. |
| R9 Medium | `mappingM3/farm_profile.py::get_farm_profile`, `304b862` | Demo seed has `demo=true` and placeholder/input-source labels, but adapter returns only `source=M3`; M4 cannot distinguish demo water/area from verified farm inputs | Preserve demo and per-field provenance through FarmContext/evidence. Test that illustrative data cannot acquire verified-farmer wording. |
| R10 Medium | `plan_engine.py::evaluate`, `04c69b5` | 165-day cabbage can be clipped to a 4-month season; `longer_than_season` flag does not prevent full modeled harvest. Rotations >3 reuse three calendar slots; overlapping windows can overwrite calendar crops | Reject/flag infeasible calendars or model full crop duration; distinguish concurrent crops. Test 165-day crop, 4?6 rotations, overlap, wrap-year and mismatch between window crop ID and rotation. |
| R11 Medium | `data/reference/crop_ranges.csv`, `crop_economics.csv`, `04c69b5`/`ee97a5f`/`903bf89` | New approximate ranges and example economics actively drive rankings, unlike legacy missing-data policy | Review with M2/data owner; retain explicit approximation labels, add row-level verifiable references, disable unsupported recommendation claims. Do not fill original catalog blanks without sourced evidence. |
| R12 Low/Medium | M1 route cache and M5 `PowerClient` | M1 stale fallback returns original payload without a distinct stale-use flag; candidate files are called fresh without age expiry; processed cache lacks TTL/version | Report cache age/source mode, define expiry/invalidation for each data class; test stale fallbacks without overwriting source evidence. Historical data may be reusable, but freshness claims must be accurate. |

Additional limitation: monthly suitability, arbitrary soil weights, 75% irrigation efficiency and fixed 0.75/0.3 yield multipliers are model assumptions, not independently calibrated physiological responses. Crop pH penalties cannot replace soil evidence. Twin distance uses 50/50 temperature/rainfall weights with 1?C and 25 mm scale floors, candidate-dependent normalization and deterministic tie-breaking; these are documented similarity choices, not crop survival probabilities.

[Diagnostic probes](CODEX_BRANCH_RECOVERY_PROBES.json) preserve numerical evidence for seasonal bias, source-cache validation and fresh POWER normalization. Other findings are directly traceable to the named functions and recorded workflow responses. No claim is made that all possible regressions were exhaustively discovered.

## 7. Explicit action table and approval boundary

?Safe to modify?? means a proposed scope for a later authorized patch, **not permission granted by this audit**. The user requested stopping after reviewable findings.

| File | Issue | Severity | Recommended action | Safe to modify? |
|---|---|---|---|---|
| `backend/agricultureM2/plan_engine.py` | Unknown feasibility, seasonal completeness, calendar clipping, relative scores | High | FIX; REVIEW WITH OWNER | After approval and M2 contract review |
| `backend/agricultureM2/plans_routes.py` | Invalid input produces 500 | Medium | FIX | After approval; retain valid-input behavior |
| `backend/resilienceM5/m2_adapter.py` | Area defaults, missing latitude/calendar, weak validation | High | FIX | After approval; coordinate M2/M5 |
| `backend/resilienceM5/scenario_engine.py` | Cache bypass of NASA provenance validation; tracked runtime writes | High | FIX | After approval; preserve existing cache contents |
| `backend/resilienceM5/stress_test.py` | Relative score deltas and obsolete limitations | High | FIX | After approval and evaluator contract tests |
| `backend/resilienceM5/rescue_mode.py` | Sequence schema and score comparability | Medium | FIX | After approval; preserve conservative ordering |
| `backend/resilienceM5/routes.py` | Stale capabilities, validation gaps | Medium | FIX | After approval |
| `backend/mappingM3/farm_profile.py`, `backend/intelligenceM4/schemas.py` | Demo/provenance lost at integration boundary | Medium | REVIEW WITH OWNER; FIX | After approval; schema compatibility review |
| `backend/tests/test_m4_blind_spots.py`, `test_m4_evidence.py`, `test_m4_integration.py` | Seven stale assertions/example comparisons | Medium | FIX | After expected behavior reviewed; never remove safety assertions |
| `backend/intelligenceM4/fixtures/example_*response.json`, `manifest.json` | Obsolete M3-not-implemented snapshots | Medium | FIX | Regenerate only after approval in isolated cache context |
| `backend/data/reference/crop_ranges.csv`, `crop_economics.csv`, `crop_water_coefficients.csv` | Approximate/source-context gaps | High | REVIEW WITH OWNER | No numeric changes without original source evidence |
| `backend/data/reference/crop_catalog.csv` | Missing environmental reference fields | Medium | KEEP pending verified data | Do not fill gaps heuristically |
| `backend/data/processed/m5_farm_climate_cache.json` | Tracked runtime cache | Medium | REMOVE GENERATED ARTIFACT AFTER APPROVAL | Only after preserving cache/provenance and configuring replacement |
| `backend/m5_stress_result.json`, `m5_twin_result.json` | Captured generated outputs | Low | REVIEW WITH OWNER | Remove only after approval; may be useful evidence |
| Existing `backend/qa_reports/*.json` captures | Large historical source evidence | Low | KEEP / REVIEW WITH OWNER | Do not delete evidence simply to reduce diff size |
| Deleted `backend/CropCompass-Nasa/**` | Old duplicated repository subtree | Low | NO ACTION | Do not restore/revert wholesale |
| `backend/app.py` | Unified app registration works | ? | KEEP | No rewrite justified |
| `backend/climateM1/services/history.py`, `projections.py` | Core conversions retained and tested | ? | KEEP; review cache disclosure separately | No blanket algorithm revert justified |
| `backend/.env.example`, module README/API contracts | Stale/partial deployment and evaluator documentation | Low | FIX | Documentation after approved contract decisions |
| `frontend/**` | Legitimate merged teammate application | ? | NO ACTION | Outside authorized modification scope |

Suggested implementation order: first preserve current HEAD with a backup reference; then correct false feasibility and ignored completeness; restore cache validation and adapter input consistency; fix HTTP validation; reconcile M4 status/fixtures and M5 response semantics; then complete scientific calibration/source review. Tests should assert honest missing-data behavior before updating snapshots. No blanket revert is recommended.

## 8. Demonstration boundaries and unresolved work

A **guided demonstration with prewarmed caches and explicitly illustrative farm inputs is feasible**: history, scenarios, rotation structure, M3 profiles, Twin, stress/rescue computation and M4 evidence all responded. NASA POWER live sample worked; live NEX was not available during the bounded check. Keep an explicit cached-source label and do not present modeled profit/ranks/feasibility as verified farm advice. A cold-cache live-only demonstration is not currently substantiated.

Remaining blockers for a scientifically defensible farmer recommendation: verified farmer area/water/soil/calendar/prices/costs; validated crop-specific environmental ranges; coherent legacy/plans contracts; proper completeness propagation; calibrated ET0/water/yield assumptions; calendar realism; reliable cache provenance; robust live NEX availability; seven regression checks; GAEZ/soil/remote-sensing integration if claimed. M3 implementation and stress/rescue computation are no longer absent, but their existence does not remove these evidence gaps.

Final preservation check: SHA-256 comparison of 177 pre-existing tracked files and 21 source/data files found no changes. Git status contains only new `CODEX_BRANCH_RECOVERY_*` audit artifacts. See [preservation evidence](CODEX_BRANCH_RECOVERY_PRESERVATION.json).

STOP: audit complete; no recommended fixes or cleanup applied.
