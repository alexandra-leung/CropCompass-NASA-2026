# Dataset Validation

## Scientific sources in use

### NASA POWER
Used for historical climate observations and climate variable normalization. The backend includes a climate history processor and NASA POWER service layer under `backend/climateM1/`.

### NASA NEX-GDDP-CMIP6 / climate projections
Used for future-climate scenario comparison and climate projection workflows under the climate intelligence module.

### FAO / GAEZ / agronomic reference data
Used for crop catalog and agronomic suitability logic under `backend/agricultureM2/` and associated data files in `backend/data/reference/`.

## Geographic and temporal scope
The project is designed for the Mauritius demonstration case and uses region-specific climate and agronomic reference data. The exact live-scope verification depends on the available NASA and FAO source payloads in the runtime environment.

## Units and conversions
The implementation documents expected meteorological units and conversion handling in the climate and water calculations. Historical climate processing normalizes values to expected scientific units before downstream use. The project also explicitly treats daily and monthly agronomic calculations as a local model-layer concern and does not claim direct farm forecast certainty from projection values alone.

## Missing-data handling
The backend uses explicit missing-data and validation paths for incomplete results, failed model results, and unavailable external data. The suite expects graceful degradation rather than invented fallback values.

## Provenance and limitations
The code and tests clearly distinguish between:

- deterministic local validation,
- external-service integration,
- and scientific limitations of the current M2/M5 agronomic model.

The backend does not claim certified agronomic forecasting or deterministic yield prediction. The README and project validation documents explicitly note that some resilience and agronomic scoring remains under development and may be reported as unknown or null when evidence is incomplete.

## Verification status
- Local source code validation: complete
- Live NASA fetch validation: not executed in this session
- FAO live-source verification: not executed in this session
- Scientific dataset provenance: code-level validation complete; live external validation remains pending in a network-enabled environment

## Summary
The repository follows a scientifically aware design using NASA and FAO source references. Local validation confirms code-level integrity and contract consistency, while live remote dataset verification remains a deployment-time check rather than a confirmed local fact.
