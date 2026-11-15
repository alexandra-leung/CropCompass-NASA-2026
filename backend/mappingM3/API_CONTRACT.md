# M3 — Farm Mapping API Contract

**Module:** M3 — Farm mapping, farmer inputs and field boundaries
**Prefix:** `/api/farms` · **Swagger:** `http://127.0.0.1:8000/docs` (tag *M3 - Farm Mapping*)

M3 records what only the farmer can tell us (field, soil, water, crops, priorities, limits)
and where the field is. It does **not** compute climate, suitability, water demand or scores.

## Rules

| Rule | How |
|---|---|
| Missing values stay `null` and are listed, never defaulted | `validate_profile()` → `missing[]` with a farmer prompt |
| Every soil value says where it came from | `farmer` · `map_estimate` · `unknown` |
| Locations are M1's registered climate locations | `location_id` must be in `climateM1.services.locations.LOCATIONS` |
| Crops are M2 catalog ids | checked against `data/reference/crop_catalog.csv` |
| Water: farmer enters **mm per season**, M4 receives **m³** | `m³ = mm × ha × 10` (`mappingM3/units.py`) |
| Automatic field outlines are not invented | `/boundary/suggest` returns `unavailable` until a verified source is cached; manual drawing is the reliable path |
| Demo farms are marked `demo: true` | their farmer answers are illustrative |

## Service function for M4

```python
# mappingM3/farm_profile.py
def get_farm_profile(farm_id: str) -> dict:   # raises KeyError for an unknown farm
    return {
        "farm_id": str, "location_id": str,
        "soil_ph": float | None, "field_area_ha": float | None,
        "irrigation_budget_m3": float | None, "current_rotation": list[str] | None,
        "source": "M3",
    }
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/farms` | Farm list (demo farms first) with summary and `missing_count` |
| GET | `/api/farms/locations` | M1 registered locations for the map |
| GET | `/api/farms/nearest-location?lat=&lon=` | Closest registered location to a tapped point |
| POST | `/api/farms/boundary/measure` | Area (ha), centre and nearest location of a drawn GeoJSON polygon |
| GET | `/api/farms/boundary/suggest?lat=&lon=` | Auto outline (currently `unavailable`, fallback = draw by hand) |
| POST | `/api/farms/validate` | Missing and contradictory inputs for a profile, with prompts |
| POST | `/api/farms` | Create a farm (201). Without a boundary, a placeholder square of the stated area is stored |
| GET | `/api/farms/{farm_id}` | Full profile + `irrigation_budget_m3` + `validation` |
| GET | `/api/farms/{farm_id}/context` | The M4 contract above |
| PUT | `/api/farms/{farm_id}` | Replace a profile |
| PATCH | `/api/farms/{farm_id}` | Change some fields (e.g. water slider: `{"irrigation": {"budget_mm_per_season": 75}}`) |
| PUT | `/api/farms/{farm_id}/boundary` | Save a drawn outline |
| DELETE | `/api/farms/{farm_id}` | Delete a farm you created (demo farms: 403) |

## Profile shape

```json
{
  "farm_id": "pamplemousses-04",
  "name": "Pamplemousses Field 04",
  "location_id": "pamplemousses-04",
  "field_area_ha": 0.6,
  "soil": {"texture": "clay_loam", "texture_source": "map_estimate",
           "ph": null, "ph_source": "unknown", "drainage": "unknown", "drainage_source": "unknown"},
  "irrigation": {"water_source": "tank", "budget_mm_per_season": 150, "budget_source": "farmer"},
  "current_rotation": ["maize", "maize", "maize"],
  "priorities": {"water": 0.4, "soil": 0.4, "climate": 0.1, "income": 0.1},
  "constraints": ["little_labour_at_harvest"],
  "boundary": {"geometry": {"type": "Polygon", "coordinates": [[[57.5714, -20.1065], "..."]]},
               "method": "default_square", "confidence": null, "source": "...", "note": "Placeholder outline: farmer should redraw."},
  "demo": true,
  "updated_at": "2026-11-15T00:00:00+00:00"
}
```

Enumerations: `water_source` ∈ rain_only, tank, borehole, irrigation_scheme, unknown ·
`texture` ∈ sand, loamy_sand, sandy_loam, loam, clay_loam, clay, unknown ·
`drainage` ∈ poor, moderate, good, unknown · `constraints` ∈ little_labour_at_harvest, no_tractor,
must_sell_to_market, need_food_for_home, short_lease. Priority weights are non-negative and stored normalised to sum to 1.

## Storage

Demo farms: `data/farms/demo_farms.json` (committed). Farms created in the app: `data/farms/farms_store.json`
(git-ignored; override with env `M3_FARM_STORE`).

## Tests

`pytest tests/test_m3_mapping.py` — 20 tests (units, soil sources, polygon checks, M1 location registry,
M4 contract, validation prompts, every route).
