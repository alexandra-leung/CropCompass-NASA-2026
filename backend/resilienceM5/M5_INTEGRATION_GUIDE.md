# M5 Integration checklist — aligned to shared repository

## Read before modifying teammates' files

1. `backend/app.py`: confirm existing `FastAPI()` variable name and include-router pattern.
2. `backend/climateM1/API_CONTRACT.md` and `api/climate.py`: identify actual historical and projected outputs.
3. `backend/agricultureM2/routes.py`, `rotation_engine.py`, `scoring.py`, `suitability.py`, `water_wallet.py`: inspect the actual callable signatures and limits. The root M2 `API_CONTRACT.md` is absent.
4. `backend/mappingM3/API_CONTRACT.md`: confirm field coordinates and m3 budget.
5. `backend/intelligenceM4/API_CONTRACT.md`, `evidence_passport.py`: source metadata schema.
6. `backend/shared/schemas.py`, `units.py`, `provenance.py`: reuse common contracts if compatible, no blind overwrite.
7. `frontend/src/api/resilience.ts`, `pages/ResilienceLab.tsx`: existing UI design and API client rules.

## Non-overwriting integration

Add this import and include call in `backend/app.py`:

```python
from resilienceM5.routes import router as resilience_router
# After app = FastAPI(...) existing instantiation:
app.include_router(resilience_router)
```

Do not create a new app, package environment, or backendM5 directory.

## Adapt M1 in place

M5 prefers M1-provided farm climate. Use an `register_m1_provider` adapter that
returns `MonthlyClimate(historical_temp12, historical_rain12, provenance)` and
`MonthlyClimate(future_temp12, future_rain12, provenance)`.

- Historical and projected precipitation arrays must be **mm/month**, not mm/day.
- M1's NEX-GDDP-CMIP6 source is NASA's bias-corrected/downscaled product. Preserve
  that classification and do not apply a second climate-delta adjustment.
- Require NASA source URLs, date range, model and scenario.
- Candidate location data can remain M5 downloaded/cached real NASA historical
  data at `backend/data/raw/nasa_power/m5_analogs/`.

## Adapt M2 in place

Do not rely on endpoint URLs or names from the superseded standalone kit. M5's
`m2_adapter.py` is registered in the unified `backend/app.py` and calls M2's
`score_rotations()` plus `check_crop_suitability()`:

```python
from resilienceM5.stress_test import register_m2_evaluator

from resilienceM5.m2_adapter import evaluate_m2_scenario
# register_m2_evaluator(evaluate_m2_scenario)
```

Wrapper exact signature:

```python
# evaluator(original_request: dict, climate: MonthlyClimate,
#           water_budget_m3: float | None) -> dict:
#   ... call REAL M2 engine and normalize response to {"rotations": [...]}.
```

The request is `{ "rotations": [{"id": "...", "crops": ["...", "..."]}, ...] }`
with at least three rotations. M5 copies it for each scenario and maps
caller-owned IDs to M2's positional comparison IDs. It runs the existing M2
monthly temperature screening function as a diagnostic, but the current crop
catalog has no temperature/pH/rainfall reference ranges or crop calendar. The
M2 water-demand function needs daily ET0, does not calculate irrigation
requirement, and does not accept a monthly water budget. As a result, M5 returns
null feasibility, scores, and water requirements rather than inventing them.
Monthly precipitation and reduced irrigation are recorded but are not consumed
by current M2 logic. Climate sensitivity and irrigation feasibility remain
unverified; do not present unknown as feasible.

## End-to-end acceptance

- [ ] `/docs` exposes the four M5 routes under unified FastAPI.
- [ ] M1 source/units accepted; same exact calendar-month definitions.
- [ ] `climate-twin` matches 3+ real NASA candidate locations and links sources.
- [x] `stress-test` calls the SAME M2 rotation scorer and preserves 3+ IDs.
- [ ] M2 returns climate- and water-based feasibility; currently unavailable.
- [ ] Changing the CMIP6 future inputs changes a climate-dependent M2 calculation
      OR the report honestly shows no change; no forced visual 'effect'.
- [x] Reducing m3 budget is kept separate from projected rainfall and passed to
      the adapter; current M2 does not use it to change feasibility.
- [ ] M3 frontend shows analog seasonal curves and rotation feasibility matrix.
- [ ] M4 Evidence Passport captures NASA sources and farmer what-if provenance.
- [x] `rescue-mode` counts known feasibility only; unknown outcomes do not pass
      and no 'survival %' is generated.
- [ ] Run `python -m pytest -q tests/test_m5_resilience.py` from `backend/`.
- [ ] Validate historical acquisition against the [NASA POWER monthly API](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/) and projections against [NASA NEX-GDDP-CMIP6](https://www.nccs.nasa.gov/data-collections/nex-gddp-cmip6/).
