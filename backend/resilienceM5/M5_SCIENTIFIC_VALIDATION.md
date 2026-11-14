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
| M2 invariance | Current + alternatives retain IDs across scenarios | Four comparison outputs |
| M2 sensitivity | Real change in climate inputs affects a relevant calculation, or no change is truthfully reported | Trace M2 intermediate water/suitability values |
| What-if | Farmer budget reduction affects M2 only through its legitimate rules | Restricted-water comparison and failed constraints |
| Rescue | Show robust *tested* alternatives, not percent survival chance | Actual stress-test JSON used by rescue output |
| Scope | No yield/profit/market forecast | Readme, API response and UI review |

## Assessment cautions

- **Climate Twin**: cosine or Euclidean similarity does not establish identical soil,
  pests, crops, land use or irrigation.
- **Water**: a projected precipitation difference and farmer irrigation budget are
  separate variables. Do not convert a 10% rainfall reduction to 10% irrigation
  reduction unless an explicit justified management model is added.
- **Future**: no climate scenario is guaranteed to be hotter or drier at every
  month/location; display actual direction and size of NASA-derived changes.
- **Rescue**: an M2 feasible status indicates passed model constraints, not
  guaranteed crop performance.
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
