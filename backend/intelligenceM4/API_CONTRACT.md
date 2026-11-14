# M4 — Explainable AI & Integration API Contract

**Project:** CropCompass 2.0 · **Module:** M4 · **Status:** Phase 1 (contracts + providers). No HTTP endpoints are live yet.

M4 explains results from M1/M2/M3/M5. It does **not** generate rotations, score crops, compute water use, or run stress tests, and it never fills missing data with default values.

## 1. Endpoints (planned)

Prefix: `/api/intelligence` (defined in `intelligenceM4/routes.py`).

| Method | Endpoint | Phase | Request | Response |
|---|---|---|---|---|
| POST | `/api/intelligence/evidence` | 2 | `AnalysisBundle` | `EvidencePassport` |
| POST | `/api/intelligence/blind-spots` | 3 | `AnalysisBundle` | `BlindSpotReport` |
| POST | `/api/intelligence/assistant` | 4 | `AssistantRequest` | `AssistantResponse` |
| POST | `/api/intelligence/analyze` | 5 | `AnalyzeRequest` | `AnalyzeResponse` |

`/evidence`, `/blind-spots` and `/assistant` take a complete `AnalysisBundle`, so the frontend can ask for explanations of an analysis it already holds without recomputing it. `/analyze` builds the bundle itself by calling the providers.

All models are defined in `intelligenceM4/schemas.py`, and the running Swagger/OpenAPI schema is the authoritative field reference.

## 2. Integrity rules (enforced in code)

| Rule | Where it is enforced |
|---|---|
| Any non-null evidence `value` attributed to M1/M2/M3/M5 must carry `provenance.field_path`, the exact bundle field it came from. Values from M4 or the farmer are exempt. | `EvidenceRecord` validator |
| Evidence `claim` text contains **no digits**. Numbers appear only in `value` + `unit`. Module ids ("M2") and labels like "SSP3-7.0" belong in `provenance` / `subject`. | `EvidenceRecord` validator |
| Missing farmer inputs (`soil_ph`, `field_area_ha`, `irrigation_budget_m3`, …) stay `null` and become blind spots. They are never defaulted. | `FarmContext` (no defaults) |
| No overall quality score or percentage is produced by M4. | By design |
| Scenario ids, projection years and location ids are validated against M1's registry, so new M1 entries are accepted with no M4 change. If the registry cannot be read, the identifier passes through and the M1 provider reports `unavailable`. | `ScenarioId`, `ProjectionYear`, `LocationId` |

## 3. Module statuses

Every provider returns a `ProviderResult` and **never raises**.

| Status | Meaning |
|---|---|
| `ok` | Call succeeded and upstream completeness flags are clean. |
| `partial` | Call succeeded but upstream flags incompleteness (M1 `missingData`, a model not `success`, M2 suitability `insufficient_data`). |
| `unavailable` | Exception, timeout (`M4_PROVIDER_TIMEOUT_SECONDS`, default 90), import failure, or payload failed validation. `error` explains why. |
| `not_implemented` | Upstream has no usable function yet. |

## 4. What M4 calls (in-process, service layer only)

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

## 5. Open issues for other modules

| To | Issue |
|---|---|
| M2 | `crop_catalog.csv` has no temperature/rainfall/pH ranges, so suitability is always `insufficient_data`. |
| M2 | `water_wallet.py` uses `parents[3]` and cannot find `crop_water_coefficients.csv`. No water route is registered, and the newer `/water-budget` exists only in `backend/CropCompass-Nasa/`. Which copy is canonical? |
| M1 | Historical POWER rainfall (about 590–870 mm/yr) and NEX-GDDP projected rainfall (about 1,350–2,450 mm/yr) differ by roughly a factor of two to three at the same site. Please confirm the precipitation conversion. |
| M1 | History caching lives in the route handler. Could it move into `services/history.py` so in-process consumers benefit? |
| M1 | `Scenario.id` / `EnsembleScenario.id` are hard-coded `Literal["ssp245","ssp370"]`, so adding a registry scenario would fail M1's own validation. |
| M1 | No ET₀ or seasonal projections are available, which M2 needs for water demand. |
| M3 / M5 | Please confirm or amend the proposed contracts above. |

## 6. Testing

```bash
cd backend
python -m pytest tests/test_m4_*.py -v            # offline
M4_LIVE=1 python -m pytest tests/test_m4_*.py -v  # also calls M1 for real
python -m intelligenceM4.fixtures.build_fixtures  # regenerate real fixtures
```
