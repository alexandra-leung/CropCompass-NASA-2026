# 🌱 CropCompass 2.0

### Climate-Resilient Agriculture Powered by NASA Earth Data

**NASA Space Apps Challenge 2026 | Team Marigold**

**Challenge:** [Field Shift: Adapting Farms with NASA Data](https://www.spaceappschallenge.org/2026/challenges/field-shift-adapting-farms-with-nasa-data/)

---

## 1. Project Overview

CropCompass 2.0 is a climate-smart agricultural decision-support platform designed to help farmers explore crop rotation strategies that respond to changing environmental conditions.

Using NASA Earth observation data, FAO agricultural references, and farmer-provided information, CropCompass aims to support decisions involving:

- Climate-resilient crop rotation planning
- Soil health and agricultural sustainability
- Water conservation and crop water requirements
- Crop suitability under current and projected climate conditions
- Long-term agricultural adaptation and resilience

The initial demonstration focuses on **Mauritius**, where changing rainfall patterns, temperature conditions, and water availability create important agricultural planning challenges.

**Our goal is not simply to recommend what to plant today, but to help farmers explore how their farming strategies may need to adapt in the future.**

CropCompass is a research prototype, not a certified agronomic advisory or forecasting service.

## 2. Core Features

### M1 — Climate Intelligence

Provides environmental information derived from NASA climate datasets.

**Responsibilities:**
- Historical temperature and rainfall analysis
- Climate projections for 2030, 2040, and 2050
- Multi-model climate comparisons
- Climate data normalization and caching
- Climate trends and environmental indicators
- Data provenance and spatial-resolution limitations

**Primary sources:** NASA POWER and NASA NEX-GDDP-CMIP6.

### M2 — Agricultural Intelligence

Evaluates crop rotation strategies using agricultural reference data and environmental constraints.

**Responsibilities:**
- Crop catalog and characteristics
- Crop-family rotation analysis (Rotation DNA)
- Identification of nitrogen-fixing crops
- Generation of alternative crop sequences
- Crop and soil suitability screening
- Water Wallet using FAO crop coefficients
- Feasibility checks and transparent rotation comparisons

**Primary sources:** FAO agricultural references, FAO-56, FAO GAEZ, relevant soil datasets, and M1 climate outputs.

### M3 — Farm Mapping and User Experience

Provides the farmer-facing interface.

**Planned capabilities:**
- Interactive farm selection
- Field boundary management
- Farm profile and soil inputs
- Water availability and agricultural preferences
- Climate and crop rotation visualizations
- Interactive scenario controls

### M4 — Explainable AI and System Integration

Connects the project modules and explains the evidence behind agricultural recommendations.

**Planned capabilities:**
- Shared API contracts and orchestration
- Explainable AI assistant
- Evidence Passport
- Dataset provenance
- Missing-data and uncertainty detection
- Grounded recommendations and explanations

### M5 — Climate Resilience and Future Adaptation

Explores how crop rotation options may respond to future environmental conditions.

**Implemented:** Climate Twin 2.0 is mounted as a router in the unified FastAPI
application. It compares an M1 future monthly climate target with a limited
pool of historical NASA POWER candidate locations. It reports three closest
matches by default, monthly comparisons, error metrics, distance components,
source provenance and limitations.

Farm climate comes from M1 in-process; M5 does not make HTTP requests back to
the same app. The separate M2-backed stress test is not active yet: without a
registered M2 climate evaluator, it returns HTTP 503 rather than inventing
climate sensitivity or crop outcomes.

## 3. System Architecture

CropCompass uses a modular FastAPI backend, with separate Python packages for each feature.

```text
CropCompass-NASA-2026/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   ├── climateM1/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── services/
│   │   └── config/
│   ├── agricultureM2/
│   │   ├── providers/
│   │   ├── routes.py
│   │   ├── crop_catalog.py
│   │   ├── rotation_engine.py
│   │   ├── rotation_generator.py
│   │   ├── suitability.py
│   │   ├── water_wallet.py
│   │   └── scoring.py
│   ├── mappingM3/
│   ├── intelligenceM4/
│   ├── resilienceM5/
│   ├── shared/
│   └── data/
│       ├── reference/
│       ├── processed/
│       └── raw/
├── frontend/
├── README.md
└── .gitignore
```

The folder layout may evolve as the team integrates additional features.

### Data Flow

```text
NASA Earth Data ──→ M1 Climate Intelligence
                            │
                            ▼
FAO Crop Data ─────→ M2 Agricultural Intelligence
                            ▲
                            │
Farmer Inputs ─────→ M3 Farm Interface
                            │
                            ▼
                Rotation Comparisons
                            │
                   ┌────────┴────────┐
                   ▼                 ▼
              M4 Explainability   M5 Resilience
                   │                 │
                   └────────┬────────┘
                            ▼
                   Farmer Dashboard
```

This diagram represents the intended integrated architecture. Some connections are still under development.

## 4. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic |
| Data processing | Pandas, NumPy |
| HTTP communication | HTTPX, Requests |
| Climate analysis | NASA climate datasets and Python scientific libraries |
| Local cache | SQLite |
| API documentation | FastAPI OpenAPI / Swagger |
| Version control | Git and GitHub |

Additional libraries may be introduced when required by the implementation.

## 5. Backend Installation

### Prerequisites

- Python 3.11 or newer
- Git
- Internet connection for uncached data requests

### Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd CropCompass-NASA-2026
```

Replace `<YOUR_REPOSITORY_URL>` with the actual GitHub clone URL.

### Create the Python environment

Open Git Bash:

```bash
cd backend

python -m venv .venv

source .venv/Scripts/activate

python -m pip install --upgrade pip

python -m pip install -r requirements.txt
```

The requirements include the backend test runner. Run the backend suite from
`backend/` with:

```bash
python -m pytest -q tests
```

### Start the backend

```bash
python -m uvicorn app:app --reload --port 8000
```

Keep this terminal open while using the API. If port 8000 is already in use,
stop the existing backend process or choose another port and use that port in
the requests below.

**Local URLs:**

- Backend: http://127.0.0.1:8000
- Health check: http://127.0.0.1:8000/health
- Swagger documentation: http://127.0.0.1:8000/docs

## 6. Frontend Setup

If the React frontend is present:

```bash
cd frontend

npm install

cp .env.example .env

npm run dev
```

The frontend should be configured to communicate with the FastAPI backend, using the appropriate `VITE_API_BASE_URL`.

## 7. API Endpoints

### M1 — Climate Intelligence

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/climate/history` | Historical climate information |
| GET | `/api/climate/scenarios` | Climate projection scenarios |

Prepared Mauritius locations:

- `pamplemousses-04`
- `flacq-02`
- `black-river-01`

**Example:**

```bash
curl "http://127.0.0.1:8000/api/climate/history?location_id=pamplemousses-04"
```

### M2 — Agricultural Intelligence

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/agriculture/crops` | List reference crops |
| POST | `/api/agriculture/rotation` | Analyze a crop sequence |
| POST | `/api/agriculture/generate` | Generate alternative crop sequences |
| GET | `/api/agriculture/suitability/{crop_id}` | Preliminary crop suitability screening |

**Example:**

```bash
curl -X POST \
  "http://127.0.0.1:8000/api/agriculture/rotation" \
  -H "Content-Type: application/json" \
  -d '{"crops":["maize","cowpea","cabbage"]}'
```

Additional FAO suitability endpoints may be registered as their data providers are implemented.

### M5 — Climate Resilience

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/resilience/health` | M1/M2 connection and offline-cache status |
| POST | `/api/resilience/climate-twin` | Compare an M1 future climate with historical NASA POWER candidates |
| POST | `/api/resilience/stress-test` | Run scenario comparisons through a registered M2 evaluator; currently returns 503 until connected |
| POST | `/api/resilience/rescue-mode` | Summarize an existing stress-test result |

Check readiness:

```bash
curl http://127.0.0.1:8000/api/resilience/health
```

Run Climate Twin with a **technical-test point**, not a verified farmer parcel:

```bash
curl -X POST http://127.0.0.1:8000/api/resilience/climate-twin \
  -H 'Content-Type: application/json' \
  -d '{"latitude":-20.103,"longitude":57.575,"scenario":"ssp245","start_year":2041,"end_year":2060,"top_k":3}'
```

The request supports `ssp245` and `ssp370`, periods from 2027–2100 (maximum
30 years), and `top_k` from 1–10. A successful response contains historical
and future Jan–Dec climate vectors, source provenance, candidate count,
excluded candidates, and up to the requested number of analogs. Each analog
includes its coordinates, 12 monthly comparisons, temperature RMSE,
precipitation MAE and standardized distance components. The score ranks
similarity only within a fixed pool of 10 locations; it is not a global search
or evidence of crop suitability.

On a cold cache, the default 2041–2060 period may require up to 200 NEX
per-model/year/variable requests (five models × 20 years × two variables), so
the first request can take time. Incomplete M1 model data or fewer than three
valid candidates returns HTTP 503; invalid inputs return HTTP 422. Candidate
NASA POWER JSON responses are cached under
`backend/data/raw/nasa_power/m5_analogs/`. M1 history and projection source
records are cached separately in `backend/data/climate_cache.sqlite3`. These
are runtime caches, not source fixtures; do not commit generated cache data.

`python -m resilienceM5.scenario_engine ...` is **not** a data-fetch command.
Candidate downloads are triggered by the `/api/resilience/climate-twin` route.

## 8. Data Sources

CropCompass prioritizes authentic, traceable scientific and agricultural datasets.

| Source | Intended application |
|---|---|
| NASA POWER | Historical gridded climate estimates |
| NASA NEX-GDDP-CMIP6 | Climate projections |
| FAO GAEZ | Crop suitability and agro-ecological context |
| FAO-56 | Crop evapotranspiration and crop coefficients |
| SoilGrids | Modeled soil properties |
| Farmer-provided information | Local soil, crop history and water constraints |

**References:**

- [NASA POWER](https://power.larc.nasa.gov/)
- [NASA NEX-GDDP-CMIP6](https://www.nasa.gov/ames/earth-science/nasa-earth-exchange-nex/gddp/downscaled-climate-projections-nex-gddp-cmip6/)
- [FAO GAEZ](https://gaez.fao.org/)
- [FAO Irrigation and Drainage Paper 56](https://www.fao.org/4/x0490e/x0490e00.htm)
- [ISRIC SoilGrids](https://soilgrids.org/)

The use of a dataset in this list does not imply that every corresponding integration is already operational.

## 9. Current Development Status

| Component | Status |
|---|---|
| Unified FastAPI backend | Initial integration working |
| M1 historical climate API | Tested successfully |
| M1 public climate projections | Annual model/ensemble endpoint; separate M5 monthly in-process service added |
| M1 → M2 historical climate communication | Tested successfully |
| M2 crop catalog | Initial reference catalog |
| M2 Rotation DNA | Tested successfully |
| M2 alternative rotation generation | Implementation available; further testing required |
| M2 crop suitability | Preliminary implementation |
| M2 FAO GAEZ provider | Under development |
| M2 Water Wallet | Not fully integrated with M1 |
| M2 numerical rotation ranking | Not calibrated |
| M3 mapping and UX | Team development |
| M4 explainable AI | Team development |
| M5 Climate Twin 2.0 | Integrated; 2040 one-year live NASA pipeline test completed |
| M5 default 2041–2060 live request | Not yet end-to-end validated on a cold cache |
| M5 → M2 stress-test adapter | Not connected; stress-test returns HTTP 503 |
| M3 verified farm-coordinate integration | Not available; demo coordinates are technical-test points |
| Backend test suite | 26 tests passed in the last recorded run |

The project is currently under active development.

## 10. Scientific Integrity and Scope

CropCompass follows an evidence-first development approach.

- NASA climate products must not be represented as exact field-level measurements.
- Climate projections are modeled scenarios, not guaranteed future conditions.
- Missing agricultural observations must not be replaced with fabricated real-world values.
- Crop suitability must consider available evidence and explicitly identify incomplete data.
- Soil-health indicators must not be presented as direct nutrient measurements without supporting observations.
- Rotation feasibility must be checked before making recommendations.
- AI-generated explanations must be grounded in actual data, rules and calculation results.

### Explicit Scope Restriction

CropCompass does **not** implement:

- Crop yield prediction
- Profit estimation
- Revenue forecasting
- Market-price optimization

The project focuses on climate resilience, water conservation, crop rotation and environmental sustainability.

## 11. Known Limitations

**Climate spatial resolution:** Nearby Mauritian fields may share identical gridded NASA POWER observations. Regional climate values should not be interpreted as independent plot-level measurements.

**Climate Twin cold-cache latency:** The 2041–2060 M5 request can need up to 200 NEX files, in addition to POWER history for candidate locations. A one-year 2040 live test succeeded; the full default period and its cold-cache latency have not yet been validated end-to-end.

**Farm coordinates:** The endpoint accepts coordinates supplied in the request, but there is no verified M3 farm-profile handoff yet. Technical-test coordinates must not be presented as a real farmer's parcel.

**M2 climate sensitivity:** M2's current rotation engine does not consume monthly temperature or precipitation. Its water-demand function expects daily ET₀ inputs, which the M1 monthly adapter does not provide. Do not treat the M5 stress-test as operational until an evidence-based M2 adapter and required climate inputs are agreed and tested.

**Crop reference coverage:** The initial M2 catalog contains a limited number of sourced crops. Further authoritative agricultural data integration is planned.

**Rotation analysis:** Basic crop-family analysis does not establish agronomic feasibility. Seasonal constraints, water requirements and soil suitability must be evaluated before a rotation is recommended.

**Scientific validation:** CropCompass is a hackathon research prototype. Real-world farming recommendations would require additional local agricultural data and expert validation.

## 12. Development Workflow

Each team member works on a dedicated development branch.

```bash
git switch <branch-name>
git pull origin <branch-name>
```

After implementing a feature:

```bash
git add .
git commit -m "Describe implemented feature"
git push origin <branch-name>
```

Changes should be reviewed and merged into `main` through pull requests.

The `main` branch should represent the team's integrated, tested application.

## 13. Next Development Milestones

1. Validate the full 2041–2060 Climate Twin request on a cold cache and measure response time.
2. Connect verified M3 farm coordinates and the Climate Twin response to the frontend.
3. Agree and test an M2 climate-input contract, including an authoritative ET₀ source for water-demand calculations.
4. Connect M5 stress testing only after M2 demonstrably responds to changed climate inputs.
5. Integrate M4 explanations and Evidence Passport with source and uncertainty metadata.
6. Complete cross-module end-to-end validation before presenting recommendations.

## 14. Team

**Team Marigold — NASA Space Apps Challenge 2026**

Team members:

- Sanjana
- Alexandra
- Kentish
- Shruti
- Khushi

Feature ownership and responsibilities are coordinated within the team.

## 15. Project Disclaimer

CropCompass 2.0 is an independently developed NASA Space Apps Challenge project. It is not an official NASA or FAO product and is not endorsed by those organizations.

All external datasets remain subject to their respective attribution, licensing and usage conditions.