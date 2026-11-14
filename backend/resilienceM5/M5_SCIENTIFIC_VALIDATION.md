# M5 scientific validity and demonstration checklist

## Evidence classes

- Historical: NASA POWER gridded estimated meteorological values, **not**
  temperature or rainfall measured at the actual farmer's parcel.
- Projected: NASA NEX-GDDP-CMIP6 bias-corrected/downscaled ensemble under a stated
  M1-supported SSP pathway, **not** a deterministic forecast or exact field-level future.
- Derived: 12-month climate normals and transparent candidate-pool standardization;
  M5 applies no additional climate-delta correction.
- User what-if: irrigation reduction factor or budget provided by the farmer,
  **not** NASA observation.
- Modeled decision: M2 crop rotation feasibility/score under scenario inputs,
  **not** measured crop survival, soil nutrients or yield change.

## Validation: mark every item pass/fail with screenshots or JSON evidence

| Gate | Test | Pass evidence |
|---|---|---|
| NASA coverage | Require all requested year-months for each 12-month normal | Recorded NASA response URLs and monthly coverage counts |
| Units | `T2M` degC, `PRECTOTCORR` mm/day -> calendar-month totals mm; NEX `tas` K and `pr` kg m-2 s-1 | Raw response units and conversion method |
| Time | Baseline 2015–2024, projection 2041–2060 | Start/end and scenario metadata |
| Source identity | POWER historical vs projection labeled separately | Source URL, data type and model ID |
| Resolution | Report selected cell + 0.25-degree projection grid | NASA endpoint metadata and limitations |
| Missing data | Reject -999 and incomplete series, no interpolation disguised as data | Test or actual error response |
| Analog math | Identical climate vector should rank with zero distance | `test_climate_twin_identical_candidate_wins` |
| Limited search | Do not claim global best-climate analog | Candidate pool and excluded locations list |
| M2 invariance | Current + alternatives retain IDs across scenarios | Engine-backed integration test; four-scenario output |
| M2 sensitivity | Verify whether actual M2 intermediate calculations change | Current result: **not verified**. `check_crop_suitability` receives changed monthly temperatures, but the catalog reference ranges are blank, so it returns the same insufficient-data result. M2 does not consume monthly precipitation. |
| What-if | Farmer budget reduction affects M2 only through its legitimate rules | Current result: **not supported**. The M2 scorer has no water-budget input; reduced budget is preserved as a user what-if but does not alter feasibility. |
| M2 feasibility | Obtain actual pass/fail constraints and water requirements | **Pending M2 agronomic logic.** Current `score_rotations` returns only sequence diagnostics and a null score/ranking; the water utility requires daily ET0 and does not calculate irrigation requirement. |
| Rescue | Show robust *tested* alternatives, not percent survival chance | Uses stress-test results only; unknown M2 feasibility is not counted as a pass |
| Scope | No yield/profit/market forecast | Readme, API response and UI review |

## Assessment cautions

- **Climate Twin**: cosine or Euclidean similarity does not establish identical soil,
  pests, crops, land use or irrigation.
- **Water**: a projected precipitation difference and farmer irrigation budget are
  separate variables. Do not convert a 10% rainfall reduction to 10% irrigation
  reduction unless an explicit justified management model is added.
- **M2 climate sensitivity**: monthly temperature and precipitation are
  source-validated by M1, but M2 currently lacks crop reference ranges/calendar,
  rainfall balance, and daily ET0 inputs. Do not describe the current output as
  climate- or irrigation-sensitive feasibility.
- **Future**: no climate scenario is guaranteed to be hotter or drier at every
  month/location; display actual direction and size of NASA-derived changes.
- **Rescue**: null M2 feasibility means unknown and is not a pass. Even a future
  M2 feasible status will indicate modeled constraints only, not guaranteed crop
  performance.
- **Data caching**: cache real NASA source bytes, HTTP URL, retrieval time,
  processing version, licensing note and missingness. Cached does not mean synthetic.
- **NDVI/Bare Soil** (stretch): low NDVI is not proof of bare soil; cloud masks,
  residue and mulch complicate inferences. No production bare-soil output is
  included in this starter pending a verified imagery source and field boundary.
- **Disaster Replay** (stretch): needs a documented event date and independent
  historical evidence. Do not invent avoided losses from the rotation engine.

Sources:

- https://power.larc.nasa.gov/docs/services/api/temporal/monthly/
- https://www.nccs.nasa.gov/data-collections/nex-gddp-cmip6/
- https://ds.nccs.nasa.gov/thredds/catalog/AMES/NEX/GDDP-CMIP6/catalog.html
- https://power.larc.nasa.gov/docs/methodology/data/processing/
- https://power.larc.nasa.gov/docs/methodology/data/sources_hydrology/
