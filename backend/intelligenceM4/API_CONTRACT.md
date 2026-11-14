# M4 — Explainable AI & Integration API Contract

**Project:** CropCompass 2.0 · **Module:** M4 · **Status:** Phase 4. `/evidence`, `/blind-spots` and `/assistant` are live.

Frontend examples (real data, kept in sync by tests) are in `intelligenceM4/fixtures/`:

- `example_evidence_request.json`: an `AnalysisBundle`, the request body for `/evidence` and `/blind-spots`.
- `example_evidence_response.json` and `example_blind_spots_response.json`.
- `example_assistant_request.json`: a **list** of three `AssistantRequest` bodies (one per question).
- `example_assistant_response.json`: the matching list of responses.

M4 explains results from M1/M2/M3/M5. It does **not** generate rotations, score crops, compute water use, or run stress tests, and it never fills missing data with default values.

## 1. Endpoints

Prefix: `/api/intelligence` (defined in `intelligenceM4/routes.py`).

| Method | Endpoint | Phase | Request | Response |
|---|---|---|---|---|
| POST | `/api/intelligence/evidence` | 2 (live) | `AnalysisBundle` | `EvidencePassport` |
| POST | `/api/intelligence/blind-spots` | 3 (live) | `AnalysisBundle` | `BlindSpotReport` |
| POST | `/api/intelligence/assistant` | 4 (live) | `AssistantRequest` | `AssistantResponse` |
| POST | `/api/intelligence/analyze` | 5 | `AnalyzeRequest` | `AnalyzeResponse` |

`/evidence`, `/blind-spots` and `/assistant` take a complete `AnalysisBundle`, so the frontend can ask for explanations of an analysis it already holds without recomputing it. `/analyze` builds the bundle itself by calling the providers.

All models are defined in `intelligenceM4/schemas.py`, and the running Swagger/OpenAPI schema is the authoritative field reference.

## 2. Integrity rules (enforced in code)

| Rule | Where it is enforced |
|---|---|
| Any non-null evidence `value` attributed to M1/M2/M3/M5 must carry `provenance.field_path`, the exact bundle field it came from. Values from M4 or the farmer are exempt. | `EvidenceRecord` validator |
| Evidence `claim` text contains no digits except exact module ids (`M1`–`M5`) and the scenario ids/labels and projection years in M1's registry (e.g. "for 2050 under SSP3-7.0"). Measured or computed numbers appear only in `value` + `unit`. If the registry is unreadable, only module ids are allowed. | `EvidenceRecord` validator (`claim_has_disallowed_digits`) |
| After a passport is built, every upstream value is re-read from its `field_path` in the bundle (serialised by alias) and must match exactly, or the request fails with HTTP 500. | `evidence_passport.verify_traceability` |
| Missing farmer inputs (`soil_ph`, `field_area_ha`, `irrigation_budget_m3`, …) stay `null` and become blind spots. They are never defaulted. | `FarmContext` (no defaults) |
| No overall quality score or percentage is produced by M4. | By design |
| Scenario ids, projection years and location ids are validated against M1's registry, so new M1 entries are accepted with no M4 change. If the registry cannot be read, the identifier passes through and an `M1_REGISTRY_UNREADABLE` blind spot (category `module`, severity `warning`) is emitted. | `ScenarioId`, `ProjectionYear`, `LocationId`, `blind_spot_detector.registry_blind_spots` |

## 3. Blind spots

`/evidence` (in `passport.blind_spots`) and `/blind-spots` call the same `detect_blind_spots()`, so they always agree for the same bundle. Detection never modifies the bundle and never fills a default.

- **Text rule:** `message`, `farmer_action` and `team_action` are fixed templates and follow the claim digit rule.
- **Specific values:** these go in `affects` (crop ids, `model:<id>`, `variable:<name>`, `scenario:<id>`) and in `citations`. Each citation is `{label, value, unit, source_module, field_path}`, and upstream citations are traceability-checked like evidence.
- **Ordering:** one blind spot per `code`, sorted critical → warning → info, then by the rule order below.

| Code | Category | Severity | Fires when | Action |
|---|---|---|---|---|
| `ROTATION_UNAVAILABLE` | module | critical | `agriculture.rotation` is null | farmer + M2 |
| `CLIMATE_PROJECTIONS_UNAVAILABLE` | module | critical | `climate.scenarios` is null | M1 |
| `CLIMATE_PROJECTIONS_PARTIAL` | climate | warning | M1 `provenance.missingData` is true or any `modelResults[].status` ≠ `success`. Failed models are listed in `affects` and cited. | M1 |
| `CLIMATE_HISTORY_UNAVAILABLE` | climate | warning | `climate.history` is null | M1 |
| `CLIMATE_HISTORY_PARTIAL` | climate | warning | any M1 history `provenance[].missingData` is true | M1 |
| `CROP_REFERENCE_INCOMPLETE` | crop_reference | warning | an M2 suitability `missing` entry ends in `_reference_range`, meaning the input was given but M2's catalog has no range. Each entry is cited at `suitability[i].missing[j]`. | M2 |
| `SUITABILITY_INPUT_NOT_PASSED` | module | warning | an M2 `missing` entry is a bare input name (e.g. `temperature_c`), meaning the call never received it. `soil_ph` counts here only when the farmer supplied a pH; otherwise `SOIL_PH_MISSING` covers it. | M4 (orchestrator) |
| `CROP_SUITABILITY_NOT_SCREENED` | crop_reference | warning | a rotation crop has no M2 suitability result | M4 (orchestrator) |
| `SOIL_PH_MISSING` | soil | warning | `farm.soil_ph` is null | farmer: soil test pH |
| `IRRIGATION_BUDGET_MISSING` | water | warning | `farm.irrigation_budget_m3` is null | farmer |
| `WATER_DEMAND_NOT_IMPLEMENTED` | water | warning | no `agriculture.water` and M2 has no water service | M2 |
| `M2_WATER_DATA_MISSING` | water | warning | no `agriculture.water` although M2 has a water service | M4 (orchestrator) |
| `M5_RESILIENCE_DATA_MISSING` | module | warning | no `resilience` although M5 has stress tests | M4 (orchestrator) |
| `M1_REGISTRY_UNREADABLE` | module | warning | M1 registry unreadable; identifiers passed through | M1 |
| `CLIMATE_RESOLUTION` | resolution | info | any M1 climate data is present. Cites M1's own `gridResolution` and `caveat`; M4 applies no resolution threshold of its own. | none |
| `M3_NOT_IMPLEMENTED` | module | info | M3 has not published `get_farm_profile` | M3 |
| `M5_NOT_IMPLEMENTED` | module | info | M5 has not published `run_stress_test` | M5 |

**M2 `missing` semantics:** M2 checks each input before its catalog range. So when an input is absent, M2 reports the bare input name and never consults the catalog for that factor, and any catalog gap for it stays hidden until the input is supplied.

"Not implemented" is decided by read-only capability probes in the providers (`water_demand_implemented`, `farm_profile_implemented`, `resilience_implemented`), which never execute upstream code.

### `module_status` (always contains `M1`, `M2`, `M3`, `M5`)

| Module | `ok` | `partial` | `unavailable` | `not_implemented` |
|---|---|---|---|---|
| M1 | scenarios and history present and complete | one is missing, or M1 flags incompleteness | neither present | n/a |
| M2 | rotation present, every crop screened, water present | rotation present but screening or water incomplete; or only other M2 data present | no M2 data | n/a |
| M3 | farm supplied by M3 | n/a | M3 exists but farm came from the farmer | M3 function missing |
| M5 | resilience present | n/a | M5 exists but no results | M5 function missing |

### `recommendation_status`

| Value | When |
|---|---|
| `insufficient_evidence` | rotation or projections missing, or any **critical** blind spot |
| `supported` | every rotation crop `within_checked_ranges`, complete projections for the selected scenario/year, and **no critical or warning** blind spots |
| `requires_further_validation` | everything else |

### Alternative rotations in the passport

When `agriculture.alternatives` is supplied, alternatives are labelled **A, B, C…** in M2's order. Each one gets these evidence records, each with a field_path into `agriculture.alternatives.alternative_rotations[i]`:

- `ev-alt-<L>-rotation`: the crop sequence
- `ev-alt-<L>-family-<crop>`: each crop's family
- `ev-alt-<L>-nfix`: its nitrogen-fixing crops
- `ev-alt-<L>-repeat`: whether it repeats a crop family in consecutive seasons

## 4. Grounded assistant (`POST /api/intelligence/assistant`)

Answers come only from the passport and blind spots built from `request.analysis`, using the same code as `/evidence` and `/blind-spots`.

**Request:** `{question (3–500 chars), analysis: AnalysisBundle, use_llm: false}`.

**Response fields:**

| Field | Meaning |
|---|---|
| `answer` | The answer text |
| `mode` | `template`, `llm` or `refused` |
| `intent` | The classified intent |
| `cited_evidence` | Evidence ids the answer uses |
| `blind_spots` | Blind-spot codes the answer uses |
| `limitations` | Upstream caveats relevant to the intent |
| `refusal_reason` | Why a question was refused |
| `fallback_reason` | Set when `use_llm` was requested but the template answer was returned |

| Intent | Typical question | Built from |
|---|---|---|
| `why_crop` | "Why cowpea?" | crop family, nitrogen-fixing flag and its qualifications, family repetition, M2 suitability, uncalibrated soil score, blind spots affecting that crop |
| `compare_rotations` | "Why is Rotation B preferable under 2050?" | M2 ranking/feasibility status, then the facts M2 reports per rotation. **Never states that one rotation is better**; while ranking is `not_calibrated` it says plainly that CropCompass has not ranked them. |
| `climate_outlook` | "What is the climate outlook?" | M1 ensemble mean and spread for the selected scenario/year, model count, observed trends, dry spell, completeness, M1 grid resolution |
| `water` | "Is there enough water?" | M2 water status, farmer irrigation budget, M1 projected rainfall (context only) |
| `missing_data` | "What data is missing?" | every blind spot, with farmer and team actions |
| `confidence` | "How sure is this?" | `recommendation_status` and the evidence statuses |

**Refused** (`mode: "refused"`, with a suggestion of answerable questions) when the question asks about:

| `refusal_reason` | Topic |
|---|---|
| `yield_prediction` | yields |
| `financial_outcome` | profit, income, prices |
| `input_dosage` | fertiliser or pesticide doses |
| `quantified_soil_improvement` | % soil improvement |
| `crop_choice` | "what should I plant" |
| `not_about_this_analysis` | anything else, including crops not in the analysis |

**Answer guard.** Applied to template and LLM answers alike.

- Every number in the text must equal a value of a cited evidence record or of a cited blind spot's citations. Allowlisted identifiers (`M1`–`M5`, registry scenarios and years) are exempt.
- Outcome promises are rejected: "will increase…", "guarantee", "% improvement", "profit", "higher yields", and similar phrasing.
- Every cited id and code must exist in the passport.
- A template answer that failed the guard would be returned as `refused` with reason `ungrounded`.

**Optional LLM (`use_llm: true`).** The LLM only rephrases the template answer, given the template text plus the cited evidence and blind spots as JSON, and nothing else. Settings come from the process environment or `backend/.env`; the environment wins, and the file is only read, never exported. `.env` is gitignored, and only `backend/.env.example` is tracked.

| Variable | Default | Meaning |
|---|---|---|
| `M4_LLM_PROVIDER` | `anthropic` | `anthropic` or `gemini` |
| `ANTHROPIC_API_KEY` | none | Required for `anthropic` |
| `GEMINI_API_KEY` | none | Required for `gemini` |
| `M4_LLM_MODEL` | `claude-haiku-5-5` (anthropic) / `gemini-3.8-flash` (gemini) | Model id |
| `M4_LLM_TIMEOUT_SECONDS` | `20` | Request timeout |

Without the key for the selected provider, the template answer is used.

**The calls are minimal:**
- **Anthropic:** `messages.create(model, max_tokens, system, messages)` with the timeout set on the client.
- **Gemini:** `models.generate_content(model, contents, config=GenerateContentConfig(system_instruction, max_output_tokens))` with `HttpOptions(timeout=<ms>)` on the client.

Both use 4096 max output tokens. Neither package (`anthropic`, `google-genai`) is in `requirements.txt`; install the one you use.

`gemini-3.8-flash` is the latest model marked "Stable" in the Flash family on Google's model page (read 2026-11-15). That page describes it as previous-generation; the Gemini 4 models use other names.

If the LLM is not configured, the package is missing, or the call times out, errors, is declined (Anthropic `refusal`, Gemini safety finish), is truncated or fails the guard, the response uses the template answer with `mode: "template"` and `fallback_reason` explaining why. The request never fails because of the LLM, and refused questions never reach it.

## 5. Module statuses (provider calls)

Every provider returns a `ProviderResult` and **never raises**.

| Status | Meaning |
|---|---|
| `ok` | Call succeeded and upstream completeness flags are clean. |
| `partial` | Call succeeded but upstream flags incompleteness (M1 `missingData`, a model not `success`, M2 suitability `insufficient_data`). |
| `unavailable` | Exception, timeout (`M4_PROVIDER_TIMEOUT_SECONDS`, default 90), import failure, or payload failed validation. `error` explains why. |
| `not_implemented` | Upstream has no usable function yet. |

## 6. What M4 calls (in-process, service layer only)

### M1: Climate (live)

| Provider | Calls | Validated with |
|---|---|---|
| `climate_provider.get_scenarios(location_id)` | `climateM1.services.projections.fetch_scenarios(location)` | `climateM1.models.climate.ScenarioResponse` |
| `climate_provider.get_history(location_id, start, end)` | `climateM1.services.history.fetch_history(location, "YYYYMMDD", "YYYYMMDD")` | `climateM1.models.climate.HistoryResponse` |
| `registered_scenario_ids / registered_projection_years` | `climateM1.services.model_registry` | n/a |
| `registered_location_ids` | `climateM1.services.locations.LOCATIONS` | n/a |

Note: `fetch_history` has no service-layer cache (M1 caches in its route), so every call goes to NASA POWER.

### M2: Agriculture (live)

| Provider | Calls | Validated with |
|---|---|---|
| `agriculture_provider.evaluate_rotation(crop_ids)` | `agricultureM2.rotation_engine.evaluate_rotation` | `M2RotationResult` |
| `agriculture_provider.generate_alternatives(current, max)` | `agricultureM2.rotation_generator.generate_rotation_candidates` | `M2GenerationResult` |
| `agriculture_provider.check_suitability(crop, temperature_c, soil_ph)` | `agricultureM2.suitability.check_crop_suitability` | `M2SuitabilityResult` |
| `agriculture_provider.get_water_demand(crop_ids)` | returns `not_implemented` | n/a |

### M3: Farm context (proposed contract, awaiting M3)

```python
# mappingM3/farm_profile.py
def get_farm_profile(farm_id: str) -> dict:
    return {
        "farm_id": str,
        "location_id": str,              # must be registered in M1
        "soil_ph": float | None,         # None if not measured, never a default
        "field_area_ha": float | None,
        "irrigation_budget_m3": float | None,
        "current_rotation": list[str] | None,   # M2 crop_ids
        "source": "M3",
    }
```

### M5: Resilience (proposed contract, awaiting M5)

```python
# resilienceM5/stress_test.py
def run_stress_test(location_id: str, scenario: str, year: int, rotation: list[str]) -> dict:
    return {
        "scenario": str, "year": int,
        "stress_tests": [ {...} ],   # M5-defined; must label NASA-projected vs hypothetical
        "limitations": [str],
    }
```

Until these exist, M4 reports `not_implemented` and records the missing evidence as a blind spot.

## 7. Open issues for other modules

| To | Issue |
|---|---|
| M2 | `crop_catalog.csv` has no temperature/rainfall/pH ranges, so suitability is always `insufficient_data`. |
| M2 | `water_wallet.py` uses `parents[3]` and cannot find `crop_water_coefficients.csv`. No water route is registered, and the newer `/water-budget` exists only in `backend/CropCompass-Nasa/`. Which copy is canonical? |
| M1 | Historical POWER rainfall (about 590–870 mm/yr) and NEX-GDDP projected rainfall (about 1,350–2,450 mm/yr) differ by roughly a factor of two to three at the same site. Please confirm the precipitation conversion. |
| M1 | History caching lives in the route handler. Could it move into `services/history.py` so in-process consumers benefit? |
| M1 | `Scenario.id` / `EnsembleScenario.id` are hard-coded `Literal["ssp245","ssp370"]`, so adding a registry scenario would fail M1's own validation. |
| M1 | No ET₀ or seasonal projections are available, which M2 needs for water demand. |
| M3 / M5 | Please confirm or amend the proposed contracts above. |

## 8. Testing

```bash
cd backend
python -m pytest tests/test_m4_*.py -v            # offline
M4_LIVE=1 python -m pytest tests/test_m4_*.py -v  # also calls M1 for real
python -m intelligenceM4.fixtures.build_fixtures  # regenerate real fixtures
```
