# M5 Integration checklist — aligned to shared repository

## Read before modifying teammates' files

1. `backend/app.py`: confirm existing `FastAPI()` variable name and include-router pattern.
2. `backend/climateM1/API_CONTRACT.md` and `api/climate.py`: identify actual historical and projected outputs.
3. `backend/agricultureM2/API_CONTRACT.md`, `routes.py`, `rotation_engine.py`, `scoring.py`, `water_wallet.py`: identify the callable that recomputes exactly the same rotations with modified climate and water.
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

Do not rely on endpoint URLs or names from the superseded standalone kit. Define a
**real** thin wrapper after inspection, then register it with M5:

```python
from resilienceM5.stress_test import register_m2_evaluator

# Map the verified M2 callable and contracts here, then:
# register_m2_evaluator(actual_team_m2_wrapper)
```

Wrapper exact signature:

```python
# evaluator(original_request: dict, climate: MonthlyClimate,
#           water_budget_m3: float | None) -> dict:
#   ... call REAL M2 engine and normalize response to {"rotations": [...]}.
```

Use a copy of the original request for every scenario. Climate must affect actual
M2 suitability or water demand. Keep failed rotations with `feasible:false`.
No M5 crop coefficients, crop catalog, yield model, or independent scoring rules.

## End-to-end acceptance

- [ ] `/docs` exposes the four M5 routes under unified FastAPI.
- [ ] M1 source/units accepted; same exact calendar-month definitions.
- [ ] `climate-twin` matches 3+ real NASA candidate locations and links sources.
- [ ] `stress-test` returns 3+ rotations evaluated by the SAME M2 engine.
- [ ] Changing the CMIP6 future inputs changes a climate-dependent M2 calculation
      OR the report honestly shows no change; no forced visual 'effect'.
- [ ] Reducing m3 budget changes relevant M2 feasibility only if its rules say so.
- [ ] M3 frontend shows analog seasonal curves and rotation feasibility matrix.
- [ ] M4 Evidence Passport captures NASA sources and farmer what-if provenance.
- [ ] `rescue-mode` ranks by scenario feasibility, not invented 'survival %'.
- [ ] Run `python -m pytest -q tests/test_m5_resilience.py` from `backend/`.
- [ ] Validate historical acquisition against the [NASA POWER monthly API](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/) and projections against [NASA NEX-GDDP-CMIP6](https://www.nccs.nasa.gov/data-collections/nex-gddp-cmip6/).
