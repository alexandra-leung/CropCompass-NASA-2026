"""
Evidence Passport — deterministic evidence collection.

Given an AnalysisBundle (outputs already produced by M1/M2/M3/M5), build an
EvidencePassport that records, for the analysed rotation:

* each claim, from a fixed template (CLAIMS), with no measured numbers in it
* the upstream value it rests on, copied verbatim, with the exact field_path
  in the bundle (serialised by alias, i.e. as the JSON the API exchanges)
* the rule that produced it (RULES) and the upstream provenance
* upstream limitations, copied verbatim
* blind spots (from blind_spot_detector)
* an overall recommendation_status

M4 computes nothing agronomic here. It only reads, cites and classifies.
After building, every upstream value is re-resolved from its field_path and
compared, so a passport can never cite a value that is not in the bundle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from intelligenceM4 import blind_spot_detector
from intelligenceM4.providers import climate_provider
from intelligenceM4.traceability import (  # noqa: F401 (re-exported for callers)
    TraceabilityError,
    check_value,
    resolve_field_path,
    verify_citations,
)
from intelligenceM4.schemas import (
    UPSTREAM_MODULES,
    AnalysisBundle,
    BlindSpot,
    EvidencePassport,
    EvidenceRecord,
    EvidenceStatus,
    Limitation,
    Provenance,
    RecommendationStatus,
    RuleApplied,
    SourceModule,
    claim_has_disallowed_digits,
)

# Units as documented in climateM1/API_CONTRACT.md §5.2 and M2 suitability factors.
RAINFALL_UNIT = "mm/year"
TEMPERATURE_UNIT = "°C"
FACTOR_UNITS = {"temperature_c": "°C", "soil_ph": "pH"}

M4_LIMITATION = (
    "M4 explains results produced by other CropCompass modules. It does not "
    "establish agronomic suitability, predict yields or quantify soil benefits."
)

# ---------------------------------------------------------------------------
# Claim templates (no measured numbers; "{context}" may add registry ids)
# ---------------------------------------------------------------------------

CLAIMS: dict[str, str] = {
    "crop_family": "Crop family is taken from the sourced crop catalog",
    "nfix_present": "The rotation contains a nitrogen-fixing crop",
    "nfix_absent": "The rotation contains no crop marked as nitrogen-fixing in the crop catalog",
    "family_repeat_none": "No crop family is repeated in consecutive seasons",
    "family_repeat": "A crop family is repeated in consecutive seasons",
    "soil_score_missing": "Soil health score has not been calibrated",
    "soil_score": "Soil health score reported by the agriculture module",
    "alt_feasibility": "Agronomic feasibility status of the alternative rotations",
    "alt_ranking": "Ranking status of the alternative rotations",
    "suit_within": "Crop is within the checked reference ranges",
    "suit_outside": "Crop is outside at least one checked reference range",
    "suit_insufficient": "Crop suitability could not be fully screened",
    "suit_not_screened": "Crop suitability has not been screened",
    "suit_factor_pass": "Supplied value is within the crop reference range",
    "suit_factor_fail": "Supplied value is outside the crop reference range",
    "proj_available": "Future climate projections are available",
    "proj_unavailable": "Future climate projections are unavailable",
    "proj_not_selected": "No climate scenario and year were selected",
    "proj_not_found": "The selected scenario and year are not present in the projections{context}",
    "proj_rain_mean": "Projected annual rainfall ensemble mean{context}",
    "proj_rain_spread": "Projected annual rainfall spread across climate models{context}",
    "proj_temp_mean": "Projected annual mean temperature ensemble mean{context}",
    "proj_temp_spread": "Projected annual mean temperature spread across climate models{context}",
    "proj_models": "Number of climate models contributing{context}",
    "hist_available": "Historical climate observations are available",
    "hist_unavailable": "Historical climate observations are unavailable",
    "hist_completeness": "Completeness of the historical daily record",
    "hist_rain_trend": "Observed annual rainfall trend direction",
    "hist_temp_trend": "Observed annual temperature trend direction",
    "hist_dry_spell": "Longest observed dry spell",
    "farm_soil_ph": "Soil acidity was supplied for this farm",
    "water_missing": "Crop water demand has not been calculated",
    "water_supplied": "Water analysis results were supplied",
    "resilience_missing": "Climate resilience stress tests are unavailable",
    "resilience_supplied": "Climate resilience results were supplied",
}

RULES: dict[str, str] = {
    "R-CROP-FAMILY": "Report each crop's family from the M2 crop catalog",
    "R-NFIX": "Report nitrogen-fixing crops flagged in the M2 crop catalog",
    "R-FAMILY-REPEAT": "Report M2's adjacent-season crop family repetition check",
    "R-SOIL-SCORE": "Report the M2 soil health score only if M2 has calculated it",
    "R-ALTERNATIVES": "Report M2's feasibility and ranking status for alternatives",
    "R-SUITABILITY": "Report M2's preliminary suitability screening for each crop",
    "R-CLIMATE-PROJ": "Report M1 ensemble projections for the selected scenario and year",
    "R-CLIMATE-HIST": "Report M1 historical observations and their completeness",
    "R-FARM-INPUTS": "Report farm inputs that were supplied",
    "R-WATER": "Report M2 water results only if M2 has supplied them",
    "R-RESILIENCE": "Report M5 resilience results only if M5 has supplied them",
}


# ---------------------------------------------------------------------------
# Traceability guard (evidence values + blind-spot citations)
# ---------------------------------------------------------------------------

def verify_traceability(passport: EvidencePassport, bundle_json: dict[str, Any]) -> None:
    for record in passport.evidence:
        prov = record.provenance
        if prov.source_module in UPSTREAM_MODULES and record.value is not None:
            check_value(bundle_json, record.id, record.value, prov.field_path)
    verify_citations(passport.blind_spots, bundle_json)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _scenario_context(scenario: str, year: int) -> str:
    """' for 2050 under SSP3-7.0' when allowed by the claim allowlist, else ''."""
    labels = climate_provider.registered_scenarios() or {}
    context = f" for {year} under {labels.get(scenario, scenario)}"
    return "" if claim_has_disallowed_digits(context) else context


class _PassportBuilder:
    def __init__(self, bundle: AnalysisBundle):
        self.bundle = bundle
        self.evidence: list[EvidenceRecord] = []
        self.rules: list[RuleApplied] = []
        self.limitations: list[Limitation] = []
        self._ids: set[str] = set()

    # -- helpers ------------------------------------------------------------

    def add(
        self,
        record_id: str,
        claim_key: str,
        status: EvidenceStatus,
        source_module: SourceModule,
        *,
        value: Any = None,
        unit: str | None = None,
        subject: str | None = None,
        field_path: str | None = None,
        context: str = "",
        qualifications: list[str] | None = None,
        **provenance: Any,
    ) -> str:
        base, n = record_id, 2
        while record_id in self._ids:
            record_id, n = f"{base}-{n}", n + 1
        self._ids.add(record_id)
        self.evidence.append(EvidenceRecord(
            id=record_id,
            claim=CLAIMS[claim_key].format(context=context),
            subject=subject,
            value=value,
            unit=unit,
            status=status,
            provenance=Provenance(
                source_module=source_module, field_path=field_path, **provenance),
            qualifications=qualifications or [],
        ))
        return record_id

    def rule(self, rule_id: str, inputs: list[str], outcome: str) -> None:
        self.rules.append(RuleApplied(
            rule_id=rule_id, description=RULES[rule_id], inputs=inputs, outcome=outcome))

    def limit(self, text: str | None, module: SourceModule) -> None:
        if text and all(l.text != text for l in self.limitations):
            self.limitations.append(Limitation(text=text, source_module=module))

    # -- M2 rotation ----------------------------------------------------------

    def rotation(self) -> None:
        rot = self.bundle.agriculture.rotation
        if rot is None:
            return
        base = "agriculture.rotation"

        for i, item in enumerate(rot.sequence):
            self.add(
                f"ev-family-{item.crop_id}", "crop_family", "supported", "M2",
                subject=item.crop_id, value=item.family,
                field_path=f"{base}.sequence[{i}].family",
                source_url=item.source_url, method="Crop catalog lookup",
            )
        self.rule("R-CROP-FAMILY", [f"{base}.sequence"], "Families reported for every season")

        if rot.nitrogen_fixing_crops:
            for i, crop in enumerate(rot.nitrogen_fixing_crops):
                url = next((s.source_url for s in rot.sequence if s.crop_id == crop), None)
                self.add(
                    f"ev-nfix-{crop}", "nfix_present", "supported", "M2",
                    subject=crop, value=crop,
                    field_path=f"{base}.nitrogen_fixing_crops[{i}]",
                    source_url=url, method="Sourced crop trait lookup",
                    qualifications=[
                        "This identifies a nitrogen-fixing opportunity; it does not "
                        "quantify a nitrogen benefit.",
                        "It does not establish that the crop is suitable for this farm; "
                        "climate and soil checks are still required.",
                    ],
                )
            outcome = "Nitrogen-fixing crop(s) present"
        else:
            self.add(
                "ev-nfix-none", "nfix_absent", "supported", "M2",
                subject="rotation", value=list(rot.nitrogen_fixing_crops),
                field_path=f"{base}.nitrogen_fixing_crops",
                method="Sourced crop trait lookup",
            )
            outcome = "No nitrogen-fixing crop present"
        self.rule("R-NFIX", [f"{base}.nitrogen_fixing_crops"], outcome)

        repeated = rot.has_adjacent_family_repetition
        self.add(
            "ev-family-repeat", "family_repeat" if repeated else "family_repeat_none",
            "supported", "M2", subject="rotation", value=repeated,
            field_path=f"{base}.has_adjacent_family_repetition",
            method="Adjacent-season family comparison (M2)",
            qualifications=[
                f"Repeated family: {r.crop_family}" for r in rot.repeated_families
            ],
        )
        self.rule("R-FAMILY-REPEAT", [f"{base}.has_adjacent_family_repetition"],
                  "Repetition found" if repeated else "No repetition")

        if rot.soil_health_score is None:
            self.add(
                "ev-soil-score", "soil_score_missing", "not_evaluated", "M2",
                subject="rotation", field_path=f"{base}.soil_health_score",
                qualifications=[f"M2 score status: {rot.score_status}"],
            )
            outcome = "Not reported: M2 has not calculated a score"
        else:
            self.add(
                "ev-soil-score", "soil_score", "partial", "M2", subject="rotation",
                value=rot.soil_health_score, field_path=f"{base}.soil_health_score",
                qualifications=[f"M2 score status: {rot.score_status}"],
            )
            outcome = "Reported as calculated by M2"
        self.rule("R-SOIL-SCORE", [f"{base}.soil_health_score", f"{base}.score_status"], outcome)

    def alternatives(self) -> None:
        alt = self.bundle.agriculture.alternatives
        if alt is None:
            return
        base = "agriculture.alternatives"
        notes = [alt.note] if alt.note else []
        self.add(
            "ev-alt-feasibility", "alt_feasibility", "not_evaluated"
            if alt.agronomic_feasibility == "not_evaluated" else "partial", "M2",
            subject="alternatives", value=alt.agronomic_feasibility,
            field_path=f"{base}.agronomic_feasibility",
            method=alt.selection_method, qualifications=notes,
        )
        self.add(
            "ev-alt-ranking", "alt_ranking", "not_evaluated"
            if alt.ranking_status == "not_calibrated" else "partial", "M2",
            subject="alternatives", value=alt.ranking_status,
            field_path=f"{base}.ranking_status",
        )
        self.limit(alt.note, "M2")
        self.rule("R-ALTERNATIVES",
                  [f"{base}.agronomic_feasibility", f"{base}.ranking_status"],
                  f"Feasibility: {alt.agronomic_feasibility}; ranking: {alt.ranking_status}")

    # -- M2 suitability -------------------------------------------------------

    def suitability(self) -> None:
        crops = list(dict.fromkeys(self._rotation_crops()))
        results = self.bundle.agriculture.suitability
        status_map: dict[str, tuple[str, EvidenceStatus]] = {
            "within_checked_ranges": ("suit_within", "supported"),
            "outside_reference_range": ("suit_outside", "unsupported"),
        }
        for crop in crops:
            idx = next((i for i, r in enumerate(results) if r.crop_id == crop), None)
            if idx is None:
                self.add(f"ev-suit-{crop}", "suit_not_screened", "not_evaluated", "M2",
                         subject=crop)
                continue
            res, base = results[idx], f"agriculture.suitability[{idx}]"
            claim, status = status_map.get(
                res.status,
                ("suit_insufficient", "partial" if res.checks else "not_evaluated"),
            )
            self.add(
                f"ev-suit-{crop}", claim, status, "M2", subject=crop, value=res.status,
                field_path=f"{base}.status", source_url=res.source_url,
                method="Preliminary range screening (M2)",
                qualifications=[f"Missing for screening: {m}" for m in res.missing],
            )
            for j, check in enumerate(res.checks):
                if check.actual is None:
                    continue
                self.add(
                    f"ev-suit-{crop}-{check.factor}",
                    "suit_factor_pass" if check.passed else "suit_factor_fail",
                    "supported" if check.passed else "unsupported", "M2",
                    subject=f"{crop}:{check.factor}", value=check.actual,
                    unit=FACTOR_UNITS.get(check.factor),
                    field_path=f"{base}.checks[{j}].actual", source_url=res.source_url,
                    qualifications=[
                        f"Reference minimum: {check.minimum}",
                        f"Reference maximum: {check.maximum}",
                    ],
                )
            self.limit(res.note, "M2")
        if crops:
            self.rule("R-SUITABILITY", ["agriculture.suitability"],
                      "Screening reported per crop where M2 supplied it")

    # -- M1 projections -------------------------------------------------------

    def projections(self) -> None:
        scen = self.bundle.climate.scenarios
        if scen is None:
            self.add("ev-proj", "proj_unavailable", "unavailable", "M1", subject="climate")
            self.rule("R-CLIMATE-PROJ", ["climate.scenarios"], "M1 projections unavailable")
            return

        prov = scen.provenance
        complete = not prov.missing_data and all(
            m.status == "success" for m in scen.model_results)
        status: EvidenceStatus = "supported" if complete else "partial"
        meta = dict(dataset=prov.source, product=prov.product,
                    grid_resolution=prov.grid_resolution, retrieved_at=prov.retrieved_at)

        self.add(
            "ev-proj", "proj_available", status, "M1", subject="climate",
            value=prov.source, field_path="climate.scenarios.provenance.source",
            method="Multi-model ensemble (M1)", **meta,
        )
        for caveat in [*scen.caveats, prov.caveat]:
            self.limit(caveat, "M1")

        scenario, year = self.bundle.selected_scenario, self.bundle.selected_year
        if scenario is None or year is None:
            self.add("ev-proj-selection", "proj_not_selected", "not_evaluated", "M4",
                     subject="climate")
            self.rule("R-CLIMATE-PROJ", ["selected_scenario", "selected_year"],
                      "No scenario/year selected")
            return

        context = _scenario_context(scenario, year)
        subject = f"climate:{scenario}:{year}"
        i = next((k for k, e in enumerate(scen.ensemble) if e.id == scenario), None)
        j = None if i is None else next(
            (k for k, v in enumerate(scen.ensemble[i].values) if v.year == year), None)
        if i is None or j is None:
            self.add("ev-proj-selection", "proj_not_found", "unavailable", "M1",
                     subject=subject, context=context)
            self.rule("R-CLIMATE-PROJ", ["climate.scenarios.ensemble"],
                      "Selected scenario/year not found in M1 ensemble")
            return

        point = scen.ensemble[i].values[j]
        base = f"climate.scenarios.ensemble[{i}].values[{j}]"
        spread_note = ("Spread is the difference between the highest and lowest model "
                       "values; it is not a probability interval.")
        n_models = len(scen.model_results)
        models_status: EvidenceStatus = (
            "supported" if n_models and point.rainfall_mm.count == n_models else "partial")

        for rec_id, claim, stats, alias, unit in (
            ("ev-proj-rain", "rain", point.rainfall_mm, "rainfallMm", RAINFALL_UNIT),
            ("ev-proj-temp", "temp", point.temperature_c, "temperatureC", TEMPERATURE_UNIT),
        ):
            self.add(f"{rec_id}-mean", f"proj_{claim}_mean", status, "M1",
                     subject=subject, value=stats.mean, unit=unit,
                     field_path=f"{base}.{alias}.mean", context=context, **meta)
            self.add(f"{rec_id}-spread", f"proj_{claim}_spread", status, "M1",
                     subject=subject, value=stats.spread, unit=unit,
                     field_path=f"{base}.{alias}.spread", context=context,
                     qualifications=[spread_note], **meta)
        self.add(
            "ev-proj-models", "proj_models", models_status, "M1", subject=subject,
            value=point.rainfall_mm.count, unit="models",
            field_path=f"{base}.rainfallMm.count", context=context,
            qualifications=[f"Contributing: {', '.join(point.contributing_models)}"],
        )
        self.rule("R-CLIMATE-PROJ", [base, "climate.scenarios.provenance.missingData",
                                     "climate.scenarios.modelResults"],
                  "Complete ensemble reported" if complete
                  else "Ensemble reported; M1 flags incomplete data")

    # -- M1 history -----------------------------------------------------------

    def history(self) -> None:
        hist = self.bundle.climate.history
        if hist is None:
            self.add("ev-hist", "hist_unavailable", "unavailable", "M1", subject="climate")
            self.rule("R-CLIMATE-HIST", ["climate.history"], "M1 history unavailable")
            return
        if not hist.provenance:
            self.add("ev-hist", "hist_unavailable", "unavailable", "M1", subject="climate",
                     qualifications=["M1 history response carried no provenance"])
            return

        prov = hist.provenance[0]
        status: EvidenceStatus = (
            "partial" if any(p.missing_data for p in hist.provenance) else "supported")
        meta = dict(dataset=prov.source, product=prov.product,
                    grid_resolution=prov.grid_resolution, retrieved_at=prov.retrieved_at)
        m = hist.metrics
        base = "climate.history.metrics"

        self.add("ev-hist", "hist_available", status, "M1", subject="climate:history",
                 value=prov.source, field_path="climate.history.provenance[0].source",
                 qualifications=[f"Period: {prov.date_range}"], **meta)
        self.add("ev-hist-completeness", "hist_completeness", status, "M1",
                 subject="climate:history", value=m.data_completeness, unit="%",
                 field_path=f"{base}.dataCompleteness", **meta)
        for rec_id, claim, trend, alias in (
            ("ev-hist-rain-trend", "hist_rain_trend", m.annual_rainfall_trend,
             "annualRainfallTrend"),
            ("ev-hist-temp-trend", "hist_temp_trend", m.annual_temperature_trend,
             "annualTemperatureTrend"),
        ):
            self.add(
                rec_id, claim, status, "M1", subject="climate:history",
                value=trend.direction, field_path=f"{base}.{alias}.direction",
                method="Mann-Kendall trend test (M1)",
                qualifications=[
                    "Statistically significant" if trend.significant
                    else "Not statistically significant",
                    f"Based on {trend.observations} annual observations",
                ],
                **meta,
            )
        self.add("ev-hist-dry-spell", "hist_dry_spell", status, "M1",
                 subject="climate:history", value=m.longest_dry_spell, unit="days",
                 field_path=f"{base}.longestDrySpell", **meta)
        for p in hist.provenance:
            self.limit(p.caveat, "M1")
        self.rule("R-CLIMATE-HIST", [base, "climate.history.provenance"],
                  "Observations reported" if status == "supported"
                  else "Observations reported; M1 flags missing data")

    # -- Farm, water, resilience ---------------------------------------------

    def farm(self) -> None:
        farm = self.bundle.farm
        if farm.soil_ph is not None:
            self.add("ev-farm-soil-ph", "farm_soil_ph", "supported", farm.source,
                     subject="farm", value=farm.soil_ph, unit="pH",
                     field_path="farm.soil_ph")
        self.rule("R-FARM-INPUTS", ["farm"], "Supplied farm inputs reported")

    def water(self) -> None:
        water = self.bundle.agriculture.water
        if water is None:
            self.add("ev-water", "water_missing", "unavailable", "M2", subject="water")
            self.rule("R-WATER", ["agriculture.water"], "No M2 water results")
            return
        assumption = water.get("assumption_status")
        hypothetical = assumption is not None and "hypothetical" in str(assumption)
        self.add(
            "ev-water", "water_supplied", "partial" if hypothetical else "not_evaluated",
            "M2", subject="water", value=assumption,
            field_path="agriculture.water.assumption_status" if assumption is not None else None,
            qualifications=(["M2 marks these water figures as based on hypothetical "
                             "assumptions"] if hypothetical else []),
        )
        for text in water.get("limitations", []) or []:
            self.limit(str(text), "M2")
        self.rule("R-WATER", ["agriculture.water"],
                  "Water results supplied" + (" (hypothetical)" if hypothetical else ""))

    def resilience(self) -> None:
        res = self.bundle.resilience
        if res is None:
            self.add("ev-resilience", "resilience_missing", "unavailable", "M5",
                     subject="resilience")
            self.rule("R-RESILIENCE", ["resilience"], "No M5 results")
            return
        self.add("ev-resilience", "resilience_supplied", "partial", "M5",
                 subject="resilience",
                 qualifications=["M4 does not yet interpret M5 stress-test fields "
                                 "(M5 contract pending)."])
        for text in res.limitations:
            self.limit(text, "M5")
        self.rule("R-RESILIENCE", ["resilience"], "M5 results supplied")

    # -- Status ---------------------------------------------------------------

    def _rotation_crops(self) -> list[str]:
        return blind_spot_detector.rotation_crops(self.bundle)

    def recommendation_status(self, blind_spots: list[BlindSpot]) -> RecommendationStatus:
        """
        insufficient_evidence  - rotation or projections missing, or any critical blind spot
        supported              - every crop within checked ranges, complete projections,
                                 AND no critical or warning blind spots
        requires_further_validation - everything else
        """
        b = self.bundle
        if (b.agriculture.rotation is None or b.climate.scenarios is None
                or any(s.severity == "critical" for s in blind_spots)):
            return "insufficient_evidence"
        by_id = {e.id: e for e in self.evidence}
        crops = set(self._rotation_crops())
        suitability_ok = bool(crops) and all(
            by_id.get(f"ev-suit-{c}") is not None
            and by_id[f"ev-suit-{c}"].value == "within_checked_ranges" for c in crops)
        climate_ok = (
            by_id.get("ev-proj") is not None and by_id["ev-proj"].status == "supported"
            and "ev-proj-rain-mean" in by_id)
        no_blocking = not any(s.severity in ("critical", "warning") for s in blind_spots)
        if suitability_ok and climate_ok and no_blocking:
            return "supported"
        return "requires_further_validation"

    def build(self, now: datetime | None = None) -> EvidencePassport:
        self.rotation()
        self.alternatives()
        self.suitability()
        self.projections()
        self.history()
        self.farm()
        self.water()
        self.resilience()
        self.limit(M4_LIMITATION, "M4")

        blind_spots = blind_spot_detector.detect_blind_spots(self.bundle)
        return EvidencePassport(
            analysis_id=self.bundle.analysis_id,
            location_id=self.bundle.farm.location_id,
            rotation=self._rotation_crops(),
            evidence=self.evidence,
            rules_applied=self.rules,
            limitations=self.limitations,
            blind_spots=blind_spots,
            recommendation_status=self.recommendation_status(blind_spots),
            generated_at=(now or datetime.now(timezone.utc)).isoformat(),
        )


def build_passport(bundle: AnalysisBundle, now: datetime | None = None) -> EvidencePassport:
    passport = _PassportBuilder(bundle).build(now)
    verify_traceability(passport, bundle.model_dump(by_alias=True, mode="json"))
    return passport
