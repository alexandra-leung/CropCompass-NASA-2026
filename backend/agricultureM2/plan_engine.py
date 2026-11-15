"""M2 plan engine: feasible, scored and ranked crop rotation plans for one farm.

Pipeline (project plan, section 11): validate -> generate -> screen -> estimate -> compare -> stress-test -> explain.

Everything is deterministic and every assumption is returned with the result:
  * Season calendar (Mauritius): 3 seasons of 4 months starting November (Nov-Feb, Mar-Jun, Jul-Oct);
    2-season rotations use Nov-Apr and May-Oct. A crop occupies ceil(growth_days / 30) months
    from the start of its season; the remaining months are bare.
  * Climate: NASA POWER seasonal means from M1 (DJF, MAM, JJA, SON) for the farm's location.
  * Reference evapotranspiration: FAO-24 Blaney-Criddle, ET0 = p (0.46 T + 8) mm/day, p for 20 deg S.
  * Crop water use: ETc = Kc x ET0 with FAO-56 Kc curves and stage lengths (crop_water_coefficients.csv).
  * Effective rainfall: USDA-SCS monthly method. Irrigation efficiency 75 %.
  * Suitability: season mean temperature against FAO ECOCROP optimal ranges (crop_ranges.csv, approximate).
  * Score = farmer-weighted mean of water, soil and climate sub-scores (0-1). Income is not scored
    because no verified prices exist. Infeasible plans (water) are ranked after feasible ones.
Outputs are model estimates (indices), not measured yields or soil changes.
"""

from __future__ import annotations

import csv
import itertools
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1] / "data" / "reference"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
# Mean daily percentage of annual daytime hours, latitude 20 deg S (FAO-24, Table 1).
P_20S = [0.30, 0.29, 0.28, 0.26, 0.25, 0.25, 0.25, 0.26, 0.27, 0.28, 0.29, 0.30]


def p_factor(latitude: float | None) -> list[float]:
    """Blaney-Criddle p (mean daily % of annual daytime hours) for any latitude, from FAO-56 eq. 34 day length."""
    if latitude is None or abs(latitude + 20) < 0.5:
        return P_20S
    phi = math.radians(max(-66.0, min(66.0, latitude)))
    mid = [15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349]
    hours = []
    for j in mid:
        dec = 0.409 * math.sin(2 * math.pi / 365 * j - 1.39)
        ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(dec))))
        hours.append(24 / math.pi * ws)
    total = sum(h * d for h, d in zip(hours, DAYS))
    return [round(h / total * 100, 3) for h in hours]


def month_span(start: int, end: int) -> list[int]:
    """Calendar months from start to end inclusive (wraps over the new year)."""
    out, m = [], start
    while True:
        out.append(m)
        if m == end or len(out) == 12:
            return out
        m = m % 12 + 1
SEASON_OF_MONTH = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM", 6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}
CALENDAR = {3: [[11, 12, 1, 2], [3, 4, 5, 6], [7, 8, 9, 10]], 2: [[11, 12, 1, 2, 3, 4], [5, 6, 7, 8, 9, 10]], 1: [[11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]}
SEASON_LABEL = {3: ["Nov–Feb", "Mar–Jun", "Jul–Oct"], 2: ["Nov–Apr", "May–Oct"], 1: ["Nov–Oct"]}
IRRIGATION_EFFICIENCY = 0.75
KEYS = ("water", "soil", "climate", "income")
HEAVY_RAIN_MM = 150.0

ASSUMPTIONS = [
    "Seasons: Nov–Feb, Mar–Jun, Jul–Oct (3-season rotation); a crop uses ceil(growth days / 30) months of its season.",
    "Climate: NASA POWER seasonal means for the farm's M1 location (regional grid, not a field sensor).",
    "ET0: FAO-24 Blaney-Criddle with daylight factor for 20° S; crop water use ETc = Kc × ET0 (FAO-56 Kc).",
    "Effective rain: USDA-SCS monthly method; irrigation efficiency 75 %.",
    "Suitability: season mean temperature vs FAO ECOCROP optimal range (approximate ranges, verify locally).",
    "Profit: harvest value minus growing cost per hectare for each crop (example costs unless you enter yours).",
    "Explainable AI: SHAP values split each plan's score into the push from water, soil, climate and income compared with the average plan.",
    "Harvest value: Mauritius average yield (Statistics Mauritius 2023-24) x your price per kg x field area; marginal climate x0.75, unsuitable x0.3, water short of need x (water you have / water needed). Gross value, costs not deducted.",
    "Score: farmer-weighted water, soil, climate and income indices; water and income are relative to the best plan compared.",
]
SOURCES = [
    {"name": "FAO Irrigation and Drainage Paper 56 (Kc, growth stages)", "url": "https://www.fao.org/4/x0490e/x0490e0b.htm"},
    {"name": "FAO Irrigation and Drainage Paper 24 (Blaney-Criddle ET0)", "url": "https://www.fao.org/4/s2022e/s2022e07.htm"},
    {"name": "FAO ECOCROP crop requirements", "url": "https://gaez.fao.org/pages/ecocrop"},
    {"name": "NASA POWER (via M1)", "url": "https://power.larc.nasa.gov/"},
    {"name": "Statistics Mauritius & FAREI: area and production of food crops 2024", "url": "https://mauritius-chamber-of-agriculture.org/wp-content/uploads/2025/04/Area-harvested-production-of-foodcrops-2024.pdf"},
]


# ------------------------------------------------------------------ reference data

def _csv(name: str) -> list[dict[str, str]]:
    text = (BASE / name).read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return list(csv.DictReader(lines))


@lru_cache(maxsize=1)
def crops() -> dict[str, dict[str, Any]]:
    cat = {r["crop_id"]: r for r in _csv("crop_catalog.csv")}
    kc = {r["crop_id"]: r for r in _csv("crop_water_coefficients.csv")}
    rng = {r["crop_id"]: r for r in _csv("crop_ranges.csv")} if (BASE / "crop_ranges.csv").exists() else {}
    eco = {r["crop_id"]: r for r in _csv("crop_economics.csv")} if (BASE / "crop_economics.csv").exists() else {}
    out: dict[str, dict[str, Any]] = {}
    for cid, c in cat.items():
        k, r, e = kc.get(cid), rng.get(cid), eco.get(cid)
        out[cid] = {
            "crop_id": cid, "name": c["crop_name"], "family": c["family"],
            "legume": str(c["nitrogen_fixing"]).strip().lower() == "true",
            "growth_days": int(float(c["growth_days"])) if c.get("growth_days") else 120,
            "kc": None if not k else {
                "ini": float(k["kc_initial"]), "mid": float(k["kc_mid"]), "end": float(k["kc_end"]),
                "stages": [int(k["days_initial"]), int(k["days_development"]), int(k["days_mid"]), int(k["days_late"])],
            },
            "yield_t_ha": float(e["yield_t_per_ha"]) if e else None,
            "price_rs_kg": float(e["example_price_rs_per_kg"]) if e else None,
            "cost_rs_ha": float(e["example_cost_rs_per_ha"]) if e and e.get("example_cost_rs_per_ha") else None,
            "range": None if not r else {
                "tmin": float(r["temp_opt_min_c"]), "tmax": float(r["temp_opt_max_c"]),
                "amin": float(r["temp_abs_min_c"]), "amax": float(r["temp_abs_max_c"]),
                "phmin": float(r["ph_opt_min"]), "phmax": float(r["ph_opt_max"]), "source": r["source"],
            },
        }
    return out


def kc_at(kc: dict[str, Any], day: float) -> float:
    """FAO-56 piecewise-linear crop coefficient curve."""
    a, b, c, d = kc["stages"]
    if day < a:
        return kc["ini"]
    if day < a + b:
        return kc["ini"] + (kc["mid"] - kc["ini"]) * (day - a) / b
    if day < a + b + c:
        return kc["mid"]
    if day < a + b + c + d:
        return kc["mid"] + (kc["end"] - kc["mid"]) * (day - a - b - c) / d
    return kc["end"]


# ------------------------------------------------------------------ climate

def monthly_climate(seasonal: list[dict[str, Any]], d_temp: float = 0.0, d_rain_pct: float = 0.0, latitude: float | None = None) -> list[dict[str, Any]] | None:
    """12 months of temperature, rain and ET0 from M1 seasonal records (e.g. '2023-DJF')."""
    acc: dict[str, list[tuple[float, float]]] = {}
    for rec in seasonal or []:
        code = str(rec.get("period", ""))[-3:]
        if code in ("DJF", "MAM", "JJA", "SON") and rec.get("temperatureC") is not None and rec.get("rainfallMm") is not None:
            acc.setdefault(code, []).append((float(rec["temperatureC"]), float(rec["rainfallMm"])))
    if len(acc) < 4:
        return None
    out = []
    for m in range(1, 13):
        vals = acc[SEASON_OF_MONTH[m]]
        t = sum(v[0] for v in vals) / len(vals) + d_temp
        rain = sum(v[1] for v in vals) / len(vals) / 3 * (1 + d_rain_pct / 100)
        et0 = p_factor(latitude)[m - 1] * (0.46 * t + 8) * DAYS[m - 1]
        peff = rain * (125 - 0.2 * rain) / 125 if rain <= 250 else 125 + 0.1 * rain
        out.append({"month": m, "label": MONTHS[m - 1], "temperature_c": round(t, 2), "rain_mm": round(rain, 1),
                    "et0_mm": round(et0, 1), "effective_rain_mm": round(max(0.0, peff), 1), "heavy_rain": rain >= HEAVY_RAIN_MM})
    return out


# ------------------------------------------------------------------ one plan

def climate_from_monthly(temperature_c: list[float], rain_mm: list[float], latitude: float | None = None) -> list[dict[str, Any]]:
    """Same 12-month climate rows as monthly_climate(), from monthly means (e.g. a CMIP6 projection)."""
    out = []
    for m in range(1, 13):
        t, rain = float(temperature_c[m - 1]), max(0.0, float(rain_mm[m - 1]))
        et0 = p_factor(latitude)[m - 1] * (0.46 * t + 8) * DAYS[m - 1]
        peff = rain * (125 - 0.2 * rain) / 125 if rain <= 250 else 125 + 0.1 * rain
        out.append({"month": m, "label": MONTHS[m - 1], "temperature_c": round(t, 2), "rain_mm": round(rain, 1),
                    "et0_mm": round(et0, 1), "effective_rain_mm": round(max(0.0, peff), 1), "heavy_rain": rain >= HEAVY_RAIN_MM})
    return out


def evaluate(rotation: list[str], climate: list[dict[str, Any]] | None, budget_mm: float | None,
             area_ha: float | None, soil_ph: float | None, weights: dict[str, float],
             prices: dict[str, float] | None = None, costs: dict[str, float] | None = None,
             months: list[list[int]] | None = None, north: bool = False) -> dict[str, Any]:
    cat = crops()
    n = len(rotation)
    seasons = CALENDAR.get(n) or CALENDAR[3]
    labels = SEASON_LABEL.get(n) or SEASON_LABEL[3]
    if north:  # northern hemisphere: the same seasons, six months later (May-Aug, Sep-Dec, Jan-Apr ...)
        seasons = [[(m + 5) % 12 + 1 for m in ss] for ss in seasons]
        labels = [f"{MONTHS[ss[0] - 1]}–{MONTHS[ss[-1] - 1]}" for ss in seasons]
    cal: list[str | None] = [None] * 12
    monthly_need = [0.0] * 12
    per_season: list[float | None] = []
    crop_rows, suit_scores, notes = [], [], []
    for i, cid in enumerate(rotation):
        c = cat[cid]
        if months and i < len(months) and months[i]:
            # the farmer's own planting window: the crop grows in exactly those months
            own = [m for m in months[i] if cal[m - 1] is None] or months[i]
            grow = months_ = own
            used = len(grow)
            label_i = f"{MONTHS[grow[0] - 1]}–{MONTHS[grow[-1] - 1]}"
        else:
            months_ = seasons[i % len(seasons)]
            used = min(len(months_), max(1, math.ceil(c["growth_days"] / 30)))
            grow = months_[:used]
            label_i = labels[i % len(labels)]
        for m in grow:
            cal[m - 1] = cid
        need = None
        if climate and c["kc"]:
            need = 0.0
            for k, m in enumerate(grow):
                cm = climate[m - 1]
                kc = kc_at(c["kc"], k * 30 + 15)
                net = max(0.0, kc * cm["et0_mm"] - cm["effective_rain_mm"])
                monthly_need[m - 1] += net / IRRIGATION_EFFICIENCY
                need += net / IRRIGATION_EFFICIENCY
            need = round(need, 1)
        per_season.append(need)
        temp = round(sum(climate[m - 1]["temperature_c"] for m in grow) / len(grow), 1) if climate else None
        status, why = "unknown", "No climate data for this location."
        r = c["range"]
        if r and temp is not None:
            if r["tmin"] <= temp <= r["tmax"]:
                status, why = "suitable", f"{temp} °C is inside its {r['tmin']:.0f}–{r['tmax']:.0f} °C best range."
            elif r["amin"] <= temp <= r["amax"]:
                status, why = "marginal", f"{temp} °C is outside its {r['tmin']:.0f}–{r['tmax']:.0f} °C best range."
            else:
                status, why = "unsuitable", f"{temp} °C is beyond what it tolerates ({r['amin']:.0f}–{r['amax']:.0f} °C)."
            if soil_ph is not None and not (r["phmin"] - 0.3 <= soil_ph <= r["phmax"] + 0.3):
                why += f" Soil pH {soil_ph} is outside {r['phmin']}–{r['phmax']}."
                status = "marginal" if status == "suitable" else status
        suit_scores.append({"suitable": 1.0, "marginal": 0.5, "unsuitable": 0.0}.get(status))
        crop_rows.append({"season": i + 1, "season_label": label_i, "crop_id": cid, "name": c["name"],
                          "family": c["family"], "legume": c["legume"], "months": [MONTHS[m - 1] for m in grow],
                          "bare_months": [MONTHS[m - 1] for m in months_[used:]], "longer_than_season": c["growth_days"] > len(months_) * 30,
                          "season_temperature_c": temp, "suitability": status, "suitability_reason": why,
                          "irrigation_need_mm": need})

    fams = [cat[c]["family"] for c in rotation]
    repeats = [i + 1 for i in range(n) if n > 1 and fams[i] == fams[(i - 1) % n]]
    legumes = [c for c in rotation if cat[c]["legume"]]
    bare = [MONTHS[m] for m in range(12) if cal[m] is None]
    bare_heavy = [MONTHS[m] for m in range(12) if cal[m] is None and climate and climate[m]["heavy_rain"]]

    known_need = [s for s in per_season if s is not None]
    peak = max(known_need) if known_need else None
    feasible, failed = True, []
    if peak is not None and budget_mm is not None and peak > budget_mm + 1e-6:
        feasible = False
        failed.append({"constraint": "water", "message": f"Needs {peak:.0f} mm in its thirstiest season; you can give {budget_mm:.0f} mm."})
    if any(cr["suitability"] == "unsuitable" for cr in crop_rows):
        feasible = False
        bad = [cr["name"] for cr in crop_rows if cr["suitability"] == "unsuitable"]
        failed.append({"constraint": "climate", "message": f"Too hot or cold for {', '.join(bad)}."})

    # harvest value (gross, Rs): average yield x price x area, cut for poor climate fit or too little water
    harvest, income, cost_total = [], 0.0, 0.0
    for cr, need in zip(crop_rows, per_season):
        c = cat[cr["crop_id"]]
        price = (prices or {}).get(cr["crop_id"], c["price_rs_kg"])
        if c["yield_t_ha"] is None or price is None:
            harvest.append(None)
            continue
        f_clim = {"suitable": 1.0, "marginal": 0.75, "unsuitable": 0.3}.get(cr["suitability"], 1.0)
        f_water = 1.0 if (need is None or budget_mm is None or need <= budget_mm or need == 0) else max(0.0, budget_mm / need)
        t = c["yield_t_ha"] * f_clim * f_water * (area_ha or 1.0)
        value = t * 1000 * price
        cost_ha = (costs or {}).get(cr["crop_id"], c["cost_rs_ha"]) or 0.0
        cost = cost_ha * (area_ha or 1.0)
        income += value
        cost_total += cost
        cr["harvest"] = {"tonnes": round(t, 2), "price_rs_per_kg": price, "value_rs": round(value), "cost_rs": round(cost),
                         "profit_rs": round(value - cost), "climate_factor": f_clim, "water_factor": round(f_water, 2)}
        harvest.append(value)
    income_rs = round(income) if any(h is not None for h in harvest) else None

    soil = 0.4 * bool(legumes) + 0.3 * (not repeats) + 0.2 * (len(set(fams)) / max(1, n)) + 0.1 * (not bare_heavy)
    clim_vals = [v for v in suit_scores if v is not None]
    climate_score = sum(clim_vals) / len(clim_vals) if clim_vals else None
    total_mm = round(sum(known_need), 1) if known_need else None
    return {
        "rotation": rotation, "crops": crop_rows,
        "calendar": [{"month": MONTHS[m], "crop_id": cal[m], "heavy_rain": bool(climate and climate[m]["heavy_rain"])} for m in range(12)],
        "dna": {"legumes": legumes, "repeated_family_seasons": repeats, "families": len(set(fams)),
                "bare_months": bare, "bare_months_in_heavy_rain": bare_heavy},
        "water": {"per_season_mm": per_season, "peak_season_mm": peak, "total_mm": total_mm,
                  "total_m3": round(total_mm * area_ha * 10) if (total_mm is not None and area_ha) else None,
                  "monthly_mm": [round(v, 1) for v in monthly_need] if climate else None, "budget_mm_per_season": budget_mm},
        "feasible": feasible, "failed_constraints": failed,
        "income": {"harvest_value_rs": income_rs, "cost_rs": round(cost_total) if income_rs is not None else None,
                   "profit_rs": round(income - cost_total) if income_rs is not None else None,
                   "area_ha": area_ha or 1.0, "area_assumed": not area_ha},
        "scores": {"water": None, "soil": round(soil, 3), "climate": None if climate_score is None else round(climate_score, 3), "income": None},
    }


# ------------------------------------------------------------------ compare

def _reasons(p: dict[str, Any], cur: dict[str, Any]) -> list[str]:
    out = []
    w, cw = p["water"]["total_mm"], cur["water"]["total_mm"]
    if p is not cur and w is not None and cw:
        d = round((1 - w / cw) * 100)
        out.append(f"Needs {abs(d)}% {'less' if d >= 0 else 'more'} irrigation than today ({w:.0f} vs {cw:.0f} mm a year).")
    elif w is not None:
        out.append(f"Needs about {w:.0f} mm of irrigation a year.")
    pf, cpf = p["income"]["profit_rs"], cur["income"]["profit_rs"]
    if p is not cur and pf is not None and cpf is not None:
        d = pf - cpf
        out.append(f"Profit about Rs {pf:,.0f} a year: Rs {abs(d):,.0f} {'more' if d >= 0 else 'less'} than today.")
    elif pf is not None:
        out.append(f"Profit about Rs {pf:,.0f} a year (harvest Rs {p['income']['harvest_value_rs']:,.0f} minus costs).")
    out.append(f"Has a legume ({', '.join(crops()[c]['name'] for c in p['dna']['legumes'])}) that adds nitrogen." if p["dna"]["legumes"] else "No legume, so no nitrogen fixing.")
    out.append("Same crop family twice in a row: pests and disease build up." if p["dna"]["repeated_family_seasons"] else "Crop family changes every season: breaks pest cycles.")
    if p["dna"]["bare_months_in_heavy_rain"]:
        out.append(f"Soil is bare in heavy-rain months ({', '.join(p['dna']['bare_months_in_heavy_rain'])}): erosion risk.")
    for cr in p["crops"]:
        if cr["suitability"] in ("marginal", "unsuitable"):
            out.append(f"{cr['name']} in {cr['season_label']}: {cr['suitability_reason']}")
    for f in p["failed_constraints"]:
        out.append(f["message"])
    return out


def candidate_rotations(current: list[str], k: int = 40) -> list[list[str]]:
    """Rotations of the same length that change family every season and include a legume."""
    cat = crops()
    n = max(1, len(current))
    ids = sorted(cat)
    out = []
    for combo in itertools.product(ids, repeat=n):
        fams = [cat[c]["family"] for c in combo]
        if n > 1 and any(fams[i] == fams[(i - 1) % n] for i in range(n)):
            continue
        if not any(cat[c]["legume"] for c in combo):
            continue
        if list(combo) == list(current):
            continue
        out.append(list(combo))
    return out


def build_plans(*, current: list[str], seasonal: list[dict[str, Any]] | None, budget_mm: float | None,
                area_ha: float | None, soil_ph: float | None, priorities: dict[str, float] | None,
                d_temp: float = 0.0, d_rain_pct: float = 0.0, max_alternatives: int = 3,
                fixed_rotations: list[list[str]] | None = None, prices: dict[str, float] | None = None,
                costs: dict[str, float] | None = None, latitude: float | None = None,
                current_months: list[list[int]] | None = None,
                climate_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    pr = priorities or {}
    w = {k: max(0.0, float(pr.get(k, 0.25) or 0)) for k in KEYS}
    if sum(w.values()) == 0:
        w = {k: 0.25 for k in KEYS}
    north = bool(latitude and latitude > 0)
    climate = climate_rows if climate_rows is not None else monthly_climate(seasonal or [], d_temp, d_rain_pct, latitude)
    cur = evaluate(current, climate, budget_mm, area_ha, soil_ph, w, prices, costs, current_months, north)
    rots = [r for r in fixed_rotations if r] if fixed_rotations else candidate_rotations(current)
    cands = [evaluate(r, climate, budget_mm, area_ha, soil_ph, w, prices, costs, None, north) for r in rots]
    pool = [cur] + cands
    needs = [p["water"]["total_mm"] for p in pool if p["water"]["total_mm"]]
    low = min(needs) if needs else None
    profits = [p["income"]["profit_rs"] for p in pool if p["income"]["profit_rs"] is not None]
    lo, hi = (min(profits), max(profits)) if profits else (None, None)
    for p in pool:
        pr_ = p["income"]["profit_rs"]
        p["scores"]["income"] = None if pr_ is None else (1.0 if hi == lo else round((pr_ - lo) / (hi - lo) * 0.8 + 0.2, 3))
        tm = p["water"]["total_mm"]
        p["scores"]["water"] = None if (tm is None or low is None) else round(min(1.0, (low + 1) / (tm + 1)), 3)
        parts = [(w[k], p["scores"][k]) for k in KEYS if p["scores"][k] is not None]
        tw = sum(x for x, _ in parts)
        p["score"] = round(sum(x * v for x, v in parts) / tw, 3) if tw else None
        p["score_breakdown"] = {k: (round(w[k] / tw * p["scores"][k], 3) if (tw and p["scores"][k] is not None) else None) for k in KEYS}
    key = lambda p: (not p["feasible"], -(p["score"] or 0))
    seen, alts = set(), []
    for p in (cands if fixed_rotations else sorted(cands, key=key)):
        sig = tuple(sorted(p["rotation"]))
        if sig in seen and not fixed_rotations:
            continue
        seen.add(sig)
        alts.append(p)
        if len(alts) >= max_alternatives and not fixed_rotations:
            break
    plans = [cur] + alts
    for i, p in enumerate(plans):
        p["id"] = "current" if i == 0 else f"plan_{chr(96 + i)}"
        p["label"] = "Today" if i == 0 else f"Plan {chr(64 + i)}"
    for r, p in enumerate(sorted(plans, key=key), 1):
        p["rank"] = r
    for p in plans:
        p["reasons"] = _reasons(p, cur)
    # Explainable AI: exact SHAP values. The score is additive (sum of weight x index), so the
    # Shapley value of each factor is weight x (its index - its mean over the compared plans).
    tw_all = sum(w.values())
    feats = [k for k in KEYS if all(p["scores"][k] is not None for p in plans)]
    tw = sum(w[k] for k in feats) or 1.0
    means = {k: sum(p["scores"][k] for p in plans) / len(plans) for k in feats}
    base = sum(w[k] / tw * means[k] for k in feats)
    for p in plans:
        p["shap"] = {"method": "SHAP (exact Shapley values for an additive score; background = the plans compared)",
                     "base_value": round(base, 4),
                     "values": {k: round(w[k] / tw * (p["scores"][k] - means[k]), 4) for k in feats},
                     "features": {k: {"index": p["scores"][k], "weight": round(w[k] / tw_all, 3), "mean_index": round(means[k], 3)} for k in feats}}
    return {
        "climate": climate, "weights": {k: round(v / sum(w.values()), 3) for k, v in w.items()}, "prices_rs_per_kg": {c: (prices or {}).get(c, v["price_rs_kg"]) for c, v in crops().items()},
        "scenario": {"temperature_change_c": d_temp, "rainfall_change_pct": d_rain_pct, "budget_mm_per_season": budget_mm},
        "plans": plans, "best_plan_id": sorted(plans, key=key)[0]["id"],
        "assumptions": ASSUMPTIONS, "sources": SOURCES,
        "status": "modelled" if climate else "no_climate",
    }
