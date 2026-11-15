"""
Grounded assistant — answers questions about ONE CropCompass analysis.

Answers are built only from the Evidence Passport and blind spots produced
from the supplied AnalysisBundle by evidence_passport / blind_spot_detector.

Template mode (default, no LLM)
-------------------------------
1. Out-of-scope check (yield, money, input doses, quantified soil improvement,
   "what should I plant", anything not about this analysis) -> mode "refused".
2. Keyword intent classification:
   missing_data, confidence, compare_rotations, water, why_crop, climate_outlook.
3. The intent composes an answer from EvidenceRecords, blind spots and their
   citations, recording exactly which evidence ids and blind-spot codes it used.

Answer guard (template AND LLM answers): every number in the text must be a
value of a cited evidence record or a cited blind-spot citation (allowlisted
identifiers such as M2 / 2050 / SSP3-7.0 excepted); no outcome-promise phrases;
every cited id/code must exist in the passport.

Optional LLM mode (use_llm=true): the LLM only rephrases the template answer,
given the cited evidence and nothing else. Providers: "anthropic" (default,
claude-haiku-5-5) or "gemini" (gemini-3.8-flash). Configuration comes from the
environment or backend/.env only. Any problem (not configured, package
missing, timeout, API error, decline, guard rejection) returns the template
answer with `fallback_reason` set; the request never fails because of the LLM.
"""

from __future__ import annotations

import importlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from intelligenceM4.evidence_passport import (
    M4_LIMITATION,
    _scenario_context,
    alternative_label,
    build_passport,
)
from intelligenceM4.schemas import (
    AnalysisBundle,
    AssistantRequest,
    AssistantResponse,
    BlindSpot,
    EvidencePassport,
    EvidenceRecord,
    strip_allowed_tokens,
)

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

OUT_OF_SCOPE: list[tuple[str, re.Pattern[str]]] = [(code, re.compile(p)) for code, p in [
    ("yield_prediction",
     r"\byields?\b|\bharvests?\b|\bproductivity\b|\btonnes?\b|\b(?:t|kg)\s*/\s*ha\b"),
    ("financial_outcome",
     r"\bprofit|\bincome\b|\bmoney\b|\brevenue\b|\bearn|\bprices?\b|\bmarket\b|\bsell\b"
     r"|\bcosts?\b|\bworth\b"),
    ("input_dosage",
     r"\bfertili[sz]|\bpesticid|\bherbicid|\bfungicid|\binsecticid|\bdos(?:e|es|age)\b"
     r"|\bspray|\bnpk\b|\burea\b|\bmanure\b"),
    ("quantified_soil_improvement",
     r"(?:%|\bpercent).*(?:\bsoil|\bimprov)|(?:\bsoil|\bimprov).*(?:%|\bpercent)"
     r"|\bhow much\b.*\bsoil\b"),
    ("crop_choice",
     r"\bwhat (?:should|can|do) i (?:plant|grow|sow)\b"
     r"|\bwhich crops? (?:should|to) (?:i )?(?:plant|grow|sow)\b"
     r"|\brecommend (?:a |some |me )?crops?\b|\bbest crops?\b"),
]]

INTENTS: list[tuple[str, re.Pattern[str]]] = [(code, re.compile(p)) for code, p in [
    ("missing_data",
     r"\bmissing\b|\bgaps?\b|\bblind[ -]?spots?\b|\bincomplete\b|\bwhat do you need\b"
     r"|\bwhat (?:data|information|else) (?:is|do you|does it)\b"
     r"|\bwhat (?:should|can) i provide\b"),
    ("confidence",
     r"\bhow sure\b|\bconfiden|\bcertain|\breliab|\btrust\b|\baccura"
     r"|\bhow (?:good|solid|strong) is\b"),
    ("compare_rotations",
     r"\b(?:rotation|alternative|option)\s+[a-z]\b|\balternatives?\b|\bcompar|\bpreferab"
     r"|\bprefer\b|\bbetter\b|\bversus\b|\bvs\.?\b|\bwhich rotation\b|\bbest rotation\b"
     r"|\bswitch\b"),
    ("water", r"\bwater\b|\birrigat\w*|\bdrought\b|\bevapotranspiration\b"),
    # why_crop is detected from crop names, between water and climate_outlook
    ("climate_outlook",
     r"\bclimate\b|\btemperatur\w*|\brain\w*|\b20\d\d\b|\bfuture\b|\bprojection\w*"
     r"|\bscenario\w*|\bssp\w*|\bheat\b|\bhot\b|\bcold\b|\bwarm\w*|\bdry\b|\bweather\b"
     r"|\bforecast\w*"
     r"|\boutlook\b"),
]]

LETTER = re.compile(r"\b(?:rotation|alternative|option)\s+([a-z])\b")
FAMILY_COMMON_NAMES = {"Fabaceae": "the legume family"}


def _normalise(question: str) -> str:
    return (question.lower().replace("’", "'").replace("“", '"').replace("”", '"'))


def _crop_aliases(bundle: AnalysisBundle) -> dict[str, str]:
    """Names a farmer might use -> crop_id, for crops in this analysis only."""
    sequences = []
    if bundle.agriculture.rotation is not None:
        sequences.append(bundle.agriculture.rotation.sequence)
    if bundle.agriculture.alternatives is not None:
        sequences += [r.sequence for r in bundle.agriculture.alternatives.alternative_rotations]
    aliases: dict[str, str] = {}
    for crop in bundle.farm.current_rotation or []:
        aliases[crop.lower()] = crop
    for seq in sequences:
        for item in seq:
            for alias in (item.crop_id, item.crop_id.replace("_", " "),
                          item.crop_name, item.crop_name.split("(")[0]):
                aliases[alias.strip().lower()] = item.crop_id
    return aliases


def classify(question: str, bundle: AnalysisBundle) -> tuple[str, str | None]:
    """Return (intent, detail). Out-of-scope intents are prefixed "refuse:"."""
    q = _normalise(question)
    for code, pattern in OUT_OF_SCOPE:
        if pattern.search(q):
            return f"refuse:{code}", None
    for code, pattern in INTENTS[:4]:
        if pattern.search(q):
            return code, None
    for alias in sorted(_crop_aliases(bundle), key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return "why_crop", _crop_aliases(bundle)[alias]
    code, pattern = INTENTS[4]
    if pattern.search(q):
        return code, None
    return "refuse:not_about_this_analysis", None


# ---------------------------------------------------------------------------
# Answer guard
# ---------------------------------------------------------------------------

NUMBER = re.compile(r"\d+(?:\.\d+)?")

PROMISE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r"\bguarantee\w*",
    r"\bprofit\w*",
    r"\bwill\s+(?:\w+\s+){0,3}(?:increase|improve|boost|raise|double|triple|maximi[sz]e)\w*",
    r"\b(?:increase|improve|boost|raise|maximi[sz]e)\w*\s+(?:\w+\s+){0,2}"
    r"(?:yields?|harvests?|income)\b",
    r"\b(?:higher|better|bigger|increased|more)\s+(?:yields?|harvests?)\b",
    r"%\s*(?:\w+\s+)?(?:improvement|increase|gain|more|higher|better)\b",
    r"\bpercent\w*\s+(?:improvement|increase|gain)\b",
]]


def _numbers_in(value: Any) -> set[float]:
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float)):
        return {abs(float(value))}
    if isinstance(value, str):
        return {float(n) for n in NUMBER.findall(value)}
    if isinstance(value, list):
        return set().union(*(_numbers_in(v) for v in value)) if value else set()
    return set()


def check_answer(answer: str, cited_evidence: list[str], blind_spots: list[str],
                 passport: EvidencePassport) -> list[str]:
    """Return a list of guard violations (empty = answer accepted)."""
    violations: list[str] = []
    evidence = {e.id: e for e in passport.evidence}
    spots = {s.code: s for s in passport.blind_spots}

    violations += [f"cited evidence '{i}' is not in the passport"
                   for i in cited_evidence if i not in evidence]
    violations += [f"cited blind spot '{c}' is not in the passport"
                   for c in blind_spots if c not in spots]
    for pattern in PROMISE_PATTERNS:
        match = pattern.search(answer)
        if match:
            violations.append(f"outcome promise: '{match.group(0)}'")

    allowed: set[float] = set()
    for i in cited_evidence:
        if i in evidence:
            allowed |= _numbers_in(evidence[i].value)
    for c in blind_spots:
        if c in spots:
            for citation in spots[c].citations:
                allowed |= _numbers_in(citation.value)
    for token in NUMBER.findall(strip_allowed_tokens(answer)):
        if float(token) not in allowed:
            violations.append(f"number {token} is not in the cited evidence")
    return violations


# ---------------------------------------------------------------------------
# Template answers
# ---------------------------------------------------------------------------

@dataclass
class Draft:
    intent: str
    text: str = ""
    cited: list[str] = field(default_factory=list)
    spots: list[str] = field(default_factory=list)
    modules: set[str] = field(default_factory=lambda: {"M4"})
    refusal: str | None = None


REFUSAL_TEXT = {
    "yield_prediction": "CropCompass does not predict yields.",
    "financial_outcome": "CropCompass does not estimate financial outcomes such as income or prices.",
    "input_dosage": "CropCompass does not prescribe fertiliser, pesticide or other input amounts.",
    "quantified_soil_improvement": ("CropCompass does not quantify soil improvement, and M2 "
                                    "has not calibrated a soil health score."),
    "crop_choice": ("CropCompass does not choose crops for you; it explains the evidence "
                    "behind the rotations in this analysis."),
    "not_about_this_analysis": "That question is not about this CropCompass analysis.",
    "ungrounded": "CropCompass could not ground an answer in this analysis's evidence.",
}

STATUS_TEXT = {
    "supported": ("Every rotation crop passed M2's checked reference ranges, the climate "
                  "projections are complete and no warnings are open. This is still a "
                  "screening result, not a field trial."),
    "requires_further_validation": ("Some evidence is in place, but open warnings mean "
                                    "CropCompass cannot treat this analysis as supported yet."),
    "insufficient_evidence": ("Core evidence is missing, so CropCompass cannot assess this "
                              "rotation yet."),
}


BLIND_SPOT_LABELS = {
    "ROTATION_UNAVAILABLE": "rotation analysis unavailable",
    "CLIMATE_PROJECTIONS_UNAVAILABLE": "climate projections unavailable",
    "CLIMATE_PROJECTIONS_PARTIAL": "climate projections incomplete",
    "CLIMATE_HISTORY_UNAVAILABLE": "climate history unavailable",
    "CLIMATE_HISTORY_PARTIAL": "climate history incomplete",
    "CROP_REFERENCE_INCOMPLETE": "crop reference ranges missing",
    "SUITABILITY_INPUT_NOT_PASSED": "suitability inputs not passed",
    "CROP_SUITABILITY_NOT_SCREENED": "suitability not screened",
    "SOIL_PH_MISSING": "soil pH missing",
    "IRRIGATION_BUDGET_MISSING": "irrigation budget missing",
    "WATER_DEMAND_NOT_IMPLEMENTED": "water demand not calculated",
    "M2_WATER_DATA_MISSING": "water results not included",
    "M1_REGISTRY_UNREADABLE": "climate registry unreadable",
    "CLIMATE_RESOLUTION": "regional climate resolution",
    "M3_NOT_IMPLEMENTED": "farm profiles not available",
    "M5_RESULTS_NOT_SUPPLIED": "M5 results were not included",
}


def blind_spot_label(spot: BlindSpot) -> str:
    """Short plain-language label; falls back to the (digit-safe) template message."""
    return BLIND_SPOT_LABELS.get(spot.code, spot.message.rstrip("."))


def _join(items: list[str]) -> str:
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "none"
    return str(value)


class _Composer:
    def __init__(self, bundle: AnalysisBundle, passport: EvidencePassport):
        self.bundle = bundle
        self.passport = passport
        self.evidence = {e.id: e for e in passport.evidence}
        self.spots = {s.code: s for s in passport.blind_spots}

    # -- helpers ------------------------------------------------------------

    def rec(self, draft: Draft, record_id: str) -> EvidenceRecord | None:
        record = self.evidence.get(record_id)
        if record is not None and record_id not in draft.cited:
            draft.cited.append(record_id)
        return record

    def spot(self, draft: Draft, code: str) -> BlindSpot | None:
        spot = self.spots.get(code)
        if spot is not None and code not in draft.spots:
            draft.spots.append(code)
        return spot

    def crop_name(self, crop: str) -> str:
        rot = self.bundle.agriculture.rotation
        sequences = [rot.sequence] if rot else []
        if self.bundle.agriculture.alternatives:
            sequences += [r.sequence for r in self.bundle.agriculture.alternatives.alternative_rotations]
        for seq in sequences:
            for item in seq:
                if item.crop_id == crop:
                    return item.crop_name.split("(")[0].strip()
        return crop.replace("_", " ").capitalize()

    def context(self) -> str:
        b = self.bundle
        if b.selected_scenario and b.selected_year:
            return _scenario_context(b.selected_scenario, b.selected_year)
        return ""

    def alt_labels(self) -> list[str]:
        alt = self.bundle.agriculture.alternatives
        return [alternative_label(i) for i in range(len(alt.alternative_rotations))] if alt else []

    # -- why_crop -------------------------------------------------------------

    def why_crop(self, crop: str) -> Draft:
        d = Draft("why_crop", modules={"M2", "M4"})
        name = self.crop_name(crop)
        if crop not in self.passport.rotation:
            labels = [l for l in self.alt_labels()
                      if crop in (self.evidence.get(f"ev-alt-{l}-rotation").value or [])]
            if not labels:
                return self.refusal("not_about_this_analysis")
            parts = [f"{name} is not in your current rotation. It appears only in "
                     f"alternative rotation {', '.join(labels)}."]
            for label in labels:
                self.rec(d, f"ev-alt-{label}-rotation")
            fam = self.rec(d, f"ev-alt-{labels[0]}-family-{crop}")
            if fam:
                parts.append(f"In M2's crop catalog it belongs to the {fam.value} family"
                             f"{self._common(fam.value)}.")
            nfix = self.rec(d, f"ev-alt-{labels[0]}-nfix")
            if nfix is not None:
                parts.append("M2's crop catalog identifies it as a nitrogen-fixing crop."
                             if crop in nfix.value else
                             "M2's crop catalog does not mark it as nitrogen-fixing.")
            rank = self.rec(d, "ev-alt-ranking")
            feas = self.rec(d, "ev-alt-feasibility")
            parts.append(f'M2 has not ranked the alternatives (ranking status "{rank.value}", '
                         f'agronomic feasibility "{feas.value}"), and their suitability for '
                         "your field has not been screened.")
            d.text = " ".join(parts)
            return d

        parts = []
        fam = self.rec(d, f"ev-family-{crop}")
        if fam:
            parts.append(f"{name} is in your current rotation. In M2's crop catalog it "
                         f"belongs to the {fam.value} family{self._common(fam.value)}.")
        nfix = self.rec(d, f"ev-nfix-{crop}")
        if nfix:
            parts.append("M2's crop catalog identifies it as a nitrogen-fixing crop.")
            # The generic "does not establish suitability" qualification is left out:
            # the specific M2 suitability sentence below says it for this crop.
            parts += [q for q in nfix.qualifications if "suitable" not in q]
        else:
            parts.append("M2's crop catalog does not mark it as nitrogen-fixing.")
        repeat = self.rec(d, "ev-family-repeat")
        if repeat is not None:
            parts.append("Across the rotation, M2 reports that a crop family is repeated in "
                         "consecutive seasons." if repeat.value else
                         "Across the rotation, M2 reports no crop family repeated in "
                         "consecutive seasons.")
        parts.append(self._suitability_sentence(d, crop, name.lower()))
        soil = self.rec(d, "ev-soil-score")
        if soil is not None and soil.value is None:
            parts.append("M2 has not calibrated a soil health score, so no soil benefit is "
                         "quantified.")
        gaps = [s for s in self.passport.blind_spots if crop in s.affects]
        if gaps:
            for s in gaps:
                self.spot(d, s.code)
            parts.append("Still open for this crop: "
                         + _join([blind_spot_label(s) for s in gaps]) + ".")
        d.text = " ".join(parts)
        return d

    @staticmethod
    def _common(family: str) -> str:
        common = FAMILY_COMMON_NAMES.get(family)
        return f" ({common})" if common else ""

    def _suitability_sentence(self, d: Draft, crop: str, name: str) -> str:
        suit = self.rec(d, f"ev-suit-{crop}")
        status = suit.value if suit else None
        if status == "within_checked_ranges":
            return (f"M2's preliminary screening found {name} within the checked reference "
                    "ranges; this is a screen, not a full suitability assessment.")
        if status == "outside_reference_range":
            return (f"M2's preliminary screening found at least one supplied value outside "
                    f"{name}'s reference range.")
        if status == "insufficient_data":
            return (f"M2 has not established that {name} is suitable for your field: its "
                    "suitability screening returned insufficient data.")
        return f"M2 has not screened {name}'s suitability for your field."

    # -- compare_rotations ----------------------------------------------------

    def compare(self, question: str) -> Draft:
        d = Draft("compare_rotations", modules={"M2", "M5", "M4"})
        labels = self.alt_labels()
        match = LETTER.search(_normalise(question))
        letter = match.group(1).upper() if match else None
        parts: list[str] = []

        if not labels:
            parts.append("M2 has not supplied alternative rotations for this analysis, so "
                         "there is nothing to compare against, and CropCompass has not "
                         "ranked any rotation.")
        else:
            rank = self.rec(d, "ev-alt-ranking")
            feas = self.rec(d, "ev-alt-feasibility")
            target = f"Rotation {letter}" if letter in labels else "any of these rotations"
            if rank.value == "not_calibrated":
                parts.append(f"CropCompass has not ranked these rotations, so it cannot say "
                             f"that {target} is preferable{self.context()}.")
            else:
                parts.append(f"M4 does not yet interpret M2's ranking, so it cannot say that "
                             f"{target} is preferable{self.context()}.")
            parts.append(f'M2 reports the ranking status as "{rank.value}" and agronomic '
                         f'feasibility as "{feas.value}": the alternatives are exploratory '
                         "sequences, not recommendations.")
            if letter and letter not in labels:
                parts.append(f"There is no Rotation {letter} in this analysis. M2 supplied "
                             f"alternatives {', '.join(labels)}.")

        parts.append("What M2 does report:")
        if self.bundle.agriculture.rotation is not None:
            parts.append(self._describe_current(d))
        shown = [letter] if letter in labels else labels
        parts += [self._describe_alternative(d, label) for label in shown]

        m5 = self.spot(d, "M5_RESULTS_NOT_SUPPLIED")
        if m5 is not None:
            parts.append("M5 provides separate Climate Twin and Stress Test endpoints, "
                         "but their results were not included in this M4 analysis, so "
                         "resilience under the projected climate was not assessed.")
        d.text = "\n".join(parts)
        return d

    def _describe_current(self, d: Draft) -> str:
        crops = self.passport.rotation
        families = [self.rec(d, f"ev-family-{c}") for c in dict.fromkeys(crops)]
        nfix = [c for c in dict.fromkeys(crops) if self.rec(d, f"ev-nfix-{c}")]
        if not nfix:
            self.rec(d, "ev-nfix-none")
        repeat = self.rec(d, "ev-family-repeat")
        return (f"- Your current rotation ({' → '.join(crops)}): families "
                f"{', '.join(f.value for f in families if f)}; nitrogen-fixing crops: "
                f"{_fmt(nfix)}; {self._repeat_text(repeat)}.")

    def _describe_alternative(self, d: Draft, label: str) -> str:
        seq = self.rec(d, f"ev-alt-{label}-rotation")
        families = [self.rec(d, f"ev-alt-{label}-family-{c}") for c in dict.fromkeys(seq.value)]
        nfix = self.rec(d, f"ev-alt-{label}-nfix")
        repeat = self.rec(d, f"ev-alt-{label}-repeat")
        return (f"- Rotation {label} ({' → '.join(seq.value)}): families "
                f"{', '.join(f.value for f in families if f)}; nitrogen-fixing crops: "
                f"{_fmt(nfix.value)}; {self._repeat_text(repeat)}.")

    @staticmethod
    def _repeat_text(repeat: EvidenceRecord | None) -> str:
        if repeat is None:
            return "family repetition not reported"
        return ("a crop family is repeated in consecutive seasons" if repeat.value
                else "no crop family repeated in consecutive seasons")

    # -- climate_outlook ------------------------------------------------------

    def climate(self) -> Draft:
        d = Draft("climate_outlook", modules={"M1", "M4"})
        parts: list[str] = []
        proj = self.rec(d, "ev-proj")
        if proj is None or proj.status == "unavailable":
            self.spot(d, "CLIMATE_PROJECTIONS_UNAVAILABLE")
            parts.append("No future climate projections from M1 are available for this analysis.")
        elif "ev-proj-rain-mean" in self.evidence:
            rain = self.rec(d, "ev-proj-rain-mean")
            rain_spread = self.rec(d, "ev-proj-rain-spread")
            temp = self.rec(d, "ev-proj-temp-mean")
            temp_spread = self.rec(d, "ev-proj-temp-spread")
            models = self.rec(d, "ev-proj-models")
            ctx = self.context().strip()
            lead = f"{ctx[0].upper()}{ctx[1:]}, " if ctx else ""
            parts.append(
                f"{lead}M1's {proj.value} ensemble of {models.value} climate models projects "
                f"an annual rainfall of {rain.value} {rain.unit} (spread "
                f"across models: {rain_spread.value} {rain_spread.unit}) and an annual mean "
                f"temperature of {temp.value} {temp.unit} (spread: {temp_spread.value} "
                f"{temp_spread.unit}).")
            parts.append("The spread is the gap between the highest and lowest model value, "
                         "not a probability range.")
            if proj.status == "partial":
                self.spot(d, "CLIMATE_PROJECTIONS_PARTIAL")
                parts.append("M1 flags these projections as incomplete.")
        else:
            selection = self.rec(d, "ev-proj-selection")
            if selection is not None:
                parts.append(selection.claim + ".")

        hist = self.rec(d, "ev-hist")
        if hist is not None and hist.status != "unavailable":
            rain_t = self.rec(d, "ev-hist-rain-trend")
            temp_t = self.rec(d, "ev-hist-temp-trend")
            dry = self.rec(d, "ev-hist-dry-spell")
            comp = self.rec(d, "ev-hist-completeness")
            parts.append(
                f"Observed record ({hist.value}): annual rainfall trend: {rain_t.value} "
                f"({rain_t.qualifications[0].lower()}); annual temperature trend: "
                f"{temp_t.value} ({temp_t.qualifications[0].lower()}); longest dry spell: "
                f"{dry.value} {dry.unit}; completeness of the daily record: {comp.value} "
                f"{comp.unit}.")
        else:
            self.spot(d, "CLIMATE_HISTORY_UNAVAILABLE")
            parts.append("No historical climate observations from M1 are available.")

        res = self.spot(d, "CLIMATE_RESOLUTION")
        if res is not None and res.citations:
            parts.append(f"These are regional model-grid values ({res.citations[0].value}), "
                         "not a forecast for your field.")
        d.text = " ".join(parts)
        return d

    # -- water ----------------------------------------------------------------

    def water(self) -> Draft:
        d = Draft("water", modules={"M2", "M1", "M4"})
        parts: list[str] = []
        water = self.rec(d, "ev-water")
        missing = water is None or water.status == "unavailable"
        if missing:
            reasons = [s.message for code in ("WATER_DEMAND_NOT_IMPLEMENTED",
                                              "M2_WATER_DATA_MISSING")
                       if (s := self.spot(d, code)) is not None]
            parts += reasons or ["Crop water demand has not been calculated for this rotation."]
        elif water.status == "partial":
            parts.append("M2 supplied water results, but marks them as based on hypothetical "
                         "assumptions.")
        else:
            parts.append("M2 supplied water results, which M4 does not yet interpret.")

        budget = self.rec(d, "ev-farm-irrigation-budget")
        if budget is not None:
            parts.append(f"Your irrigation budget: {budget.value} cubic metres for the whole "
                         "rotation.")
        else:
            spot = self.spot(d, "IRRIGATION_BUDGET_MISSING")
            if spot:
                parts.append(f"{spot.message} {spot.farmer_action}")

        rain = self.evidence.get("ev-proj-rain-mean")
        if rain is not None:
            self.rec(d, "ev-proj-rain-mean")
            parts.append(f"For context, M1 projects an annual rainfall of {rain.value} "
                         f"{rain.unit}{self.context()}; this is a regional annual total, not "
                         "the rainfall your crops can use, so it does not replace a "
                         "water-demand calculation.")
        if missing or budget is None:
            parts.append("CropCompass therefore cannot yet say whether this rotation fits "
                         "your water supply.")
        d.text = " ".join(parts)
        return d

    # -- missing_data ---------------------------------------------------------

    def missing(self) -> Draft:
        d = Draft("missing_data", modules={"M1", "M2", "M3", "M5", "M4", "farmer"})
        spots = self.passport.blind_spots
        if not spots:
            d.text = "No blind spots were detected for this analysis."
            return d
        headings = {
            "critical": "Critical gaps (the analysis cannot be assessed without these):",
            "warning": "Gaps that keep this analysis from being supported:",
            "info": "For context:",
        }
        lines: list[str] = []
        for severity, heading in headings.items():
            group = [s for s in spots if s.severity == severity]
            if not group:
                continue
            lines.append(heading)
            for s in group:
                self.spot(d, s.code)
                line = f"- {s.message}"
                if s.farmer_action:
                    line += f" What you can do: {s.farmer_action}"
                if s.team_action and severity != "info":
                    line += f" Who needs to act: {s.team_action}"
                lines.append(line)
        d.text = "\n".join(lines)
        return d

    # -- confidence -----------------------------------------------------------

    def confidence(self) -> Draft:
        d = Draft("confidence", modules={"M1", "M2", "M3", "M5", "M4", "farmer"})
        status = self.passport.recommendation_status
        parts = [f"Overall status: {status.replace('_', ' ')}. {STATUS_TEXT[status]}"]

        def claims(statuses: set[str]) -> list[str]:
            out: list[str] = []
            for e in self.passport.evidence:
                if e.status in statuses and not e.id.startswith(("ev-alt-", "ev-family-")):
                    self.rec(d, e.id)
                    if e.claim not in out:
                        out.append(e.claim)
            return out

        backed = claims({"supported"})
        if backed:
            parts.append("Backed by upstream data: " + "; ".join(backed) + ".")
        open_ = claims({"partial", "not_evaluated", "unavailable", "unsupported"})
        if open_:
            parts.append("Not yet established: " + "; ".join(open_) + ".")
        blocking = [s for s in self.passport.blind_spots if s.severity in ("critical", "warning")]
        for s in blocking:
            self.spot(d, s.code)
        if blocking:
            parts.append("Ask “What data is missing?” to see the open gaps and what would "
                         "close them.")
        d.text = "\n".join(parts)
        return d

    # -- refusal --------------------------------------------------------------

    def refusal(self, reason: str) -> Draft:
        crops = self.passport.rotation
        nfix = [c for c in crops if f"ev-nfix-{c}" in self.evidence]
        suggestions = []
        if crops:
            suggestions.append(f"“Why {self.crop_name((nfix or crops)[0]).lower()}?”")
        suggestions += ["“What data is missing?”", "“How sure is this analysis?”"]
        text = (f"{REFUSAL_TEXT.get(reason.split(':')[0], REFUSAL_TEXT['ungrounded'])} It can "
                "only explain the climate, crop and data evidence in this analysis. You could "
                f"ask instead: {', '.join(suggestions)}.")
        return Draft("refused", text=text, refusal=reason)


def compose(question: str, bundle: AnalysisBundle, passport: EvidencePassport) -> Draft:
    composer = _Composer(bundle, passport)
    intent, detail = classify(question, bundle)
    if intent.startswith("refuse:"):
        return composer.refusal(intent.split(":", 1)[1])
    if intent == "why_crop":
        return composer.why_crop(detail)
    return {
        "compare_rotations": lambda: composer.compare(question),
        "climate_outlook": composer.climate,
        "water": composer.water,
        "missing_data": composer.missing,
        "confidence": composer.confidence,
    }[intent]()


# ---------------------------------------------------------------------------
# Optional LLM rephrasing
# ---------------------------------------------------------------------------

DEFAULT_MODELS = {
    "anthropic": "claude-haiku-5-5",
    # Latest model marked "Stable" in the Flash family on Google's model page
    # (aistudio.google.com/docs/models, read 2026-11-15). Override with M4_LLM_MODEL.
    "gemini": "gemini-3.8-flash",
}
API_KEY_VARS = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}
MAX_OUTPUT_TOKENS = 4096

# Keys and settings come from the process environment or backend/.env only.
# The environment wins over the file; the file is read, never written or exported.
DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"

LLM_SYSTEM_PROMPT = (
    "You rewrite an explanation from CropCompass, a farm-planning tool, so that a farmer "
    "can read it easily.\n"
    "Rules:\n"
    "- Use only the facts in EXPLANATION, EVIDENCE and BLIND_SPOTS. Add nothing else.\n"
    "- Keep every number exactly as written. Do not add, round or convert numbers.\n"
    "- Keep every limitation and every statement about what is unknown, missing or not "
    "yet evaluated.\n"
    "- Do not recommend crops, predict yields, income or soil improvement, or promise any "
    "outcome.\n"
    "- Reply with plain text only: no headings, tables or markdown."
)


class LLMUnavailable(RuntimeError):
    """The optional LLM could not produce an answer; use the template answer."""


def _config(name: str) -> str | None:
    """Value from the environment, else from backend/.env, else None."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        from dotenv import dotenv_values
        return dotenv_values(DOTENV_PATH).get(name) if DOTENV_PATH.is_file() else None
    except Exception:
        return None


def llm_settings() -> dict[str, Any]:
    """Provider, key, model and timeout from the environment / backend/.env only."""
    provider = (_config("M4_LLM_PROVIDER") or "anthropic").strip().lower()
    if provider not in API_KEY_VARS:
        raise LLMUnavailable(f"unsupported M4_LLM_PROVIDER '{provider}'")
    api_key = _config(API_KEY_VARS[provider])
    if not api_key:
        raise LLMUnavailable(f"{API_KEY_VARS[provider]} is not set")
    try:
        timeout = float(_config("M4_LLM_TIMEOUT_SECONDS") or 20)
    except ValueError:
        timeout = 20.0
    return {
        "provider": provider,
        "api_key": api_key,
        "model": _config("M4_LLM_MODEL") or DEFAULT_MODELS[provider],
        "timeout": timeout,
    }


def _import(module: str, package: str):
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise LLMUnavailable(f"the {package} package is not installed") from exc


def _call_anthropic(settings: dict[str, Any], system: str, user_content: str) -> str:
    anthropic = _import("anthropic", "anthropic")
    # max_retries=0: the SDK retries twice by default, which would let a timing-out
    # call block for ~3x the timeout. The timeout must be the real upper bound.
    client = anthropic.Anthropic(
        api_key=settings["api_key"], timeout=settings["timeout"], max_retries=0)
    try:
        response = client.messages.create(
            model=settings["model"],
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.APITimeoutError as exc:
        raise LLMUnavailable(f"LLM request timed out after {settings['timeout']:g}s") from exc
    except anthropic.RateLimitError as exc:
        raise LLMUnavailable("LLM rate limit reached") from exc
    except anthropic.AuthenticationError as exc:
        raise LLMUnavailable("LLM authentication failed") from exc
    except anthropic.APIStatusError as exc:
        raise LLMUnavailable(f"LLM API error (HTTP {exc.status_code})") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMUnavailable("could not connect to the LLM API") from exc

    if response.stop_reason == "refusal":
        raise LLMUnavailable("the LLM declined the request")
    if response.stop_reason == "max_tokens":
        raise LLMUnavailable("the LLM answer was truncated")
    return "".join(b.text for b in response.content if b.type == "text")


def _call_gemini(settings: dict[str, Any], system: str, user_content: str) -> str:
    genai = _import("google.genai", "google-genai")
    types = _import("google.genai.types", "google-genai")
    errors = _import("google.genai.errors", "google-genai")
    client = genai.Client(
        api_key=settings["api_key"],
        http_options=types.HttpOptions(
            # google-genai's HttpOptions.timeout is in milliseconds.
            timeout=int(settings["timeout"] * 1000),
            # attempts=1 means no retries. google-genai 1.30 already defaults to no
            # retries; pinning it keeps the timeout the upper bound in any version.
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    try:
        response = client.models.generate_content(
            model=settings["model"],
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            ),
        )
    except errors.APIError as exc:
        raise LLMUnavailable(f"LLM API error ({getattr(exc, 'code', 'unknown')})") from exc
    except Exception as exc:
        # The HTTP layer (httpx / httpx2 depending on SDK version) raises *Timeout*.
        if "Timeout" in type(exc).__name__:
            raise LLMUnavailable(
                f"LLM request timed out after {settings['timeout']:g}s") from exc
        raise

    candidates = getattr(response, "candidates", None) or []
    finish = getattr(getattr(candidates[0], "finish_reason", None), "name", "") if candidates else ""
    if finish == "MAX_TOKENS":
        raise LLMUnavailable("the LLM answer was truncated")
    if finish in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION", "SPII"}:
        raise LLMUnavailable("the LLM declined the request")
    return response.text or ""


def _call_llm(settings: dict[str, Any], system: str, user_content: str) -> str:
    """One non-streaming call to the configured provider. Raises LLMUnavailable."""
    call = _call_gemini if settings["provider"] == "gemini" else _call_anthropic
    text = call(settings, system, user_content).strip()
    if not text:
        raise LLMUnavailable("the LLM returned no text")
    return text


def _llm_user_content(question: str, draft: Draft, passport: EvidencePassport) -> str:
    evidence = {e.id: e for e in passport.evidence}
    spots = {s.code: s for s in passport.blind_spots}
    return json.dumps({
        "QUESTION": question,
        "EXPLANATION": draft.text,
        "EVIDENCE": [evidence[i].model_dump(mode="json", include={
            "id", "claim", "subject", "value", "unit", "status", "qualifications"})
            for i in draft.cited],
        "BLIND_SPOTS": [spots[c].model_dump(mode="json", include={
            "code", "message", "farmer_action", "citations"}) for c in draft.spots],
    }, ensure_ascii=False, indent=1)


def rephrase(question: str, draft: Draft, passport: EvidencePassport) -> tuple[str | None, str | None]:
    """Return (llm_text, None) if accepted, else (None, fallback_reason)."""
    try:
        text = _call_llm(llm_settings(), LLM_SYSTEM_PROMPT,
                         _llm_user_content(question, draft, passport))
    except LLMUnavailable as exc:
        return None, f"LLM unavailable: {exc}"
    except Exception as exc:  # never fail the request because of the LLM
        return None, f"LLM unavailable: {type(exc).__name__}"
    violations = check_answer(text, draft.cited, draft.spots, passport)
    if violations:
        return None, "LLM answer rejected by the answer guard: " + "; ".join(violations)
    return text, None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def answer(request: AssistantRequest) -> AssistantResponse:
    passport = build_passport(request.analysis)
    draft = compose(request.question, request.analysis, passport)

    violations = check_answer(draft.text, draft.cited, draft.spots, passport)
    if violations:  # a template bug must never reach the farmer
        draft = _Composer(request.analysis, passport).refusal("ungrounded")
        draft.refusal = "ungrounded: " + "; ".join(violations)

    if draft.refusal is not None:
        return AssistantResponse(
            answer=draft.text, mode="refused", intent=draft.intent,
            limitations=[M4_LIMITATION], refusal_reason=draft.refusal)

    limitations = [l.text for l in passport.limitations if l.source_module in draft.modules]
    text, mode, fallback = draft.text, "template", None
    if request.use_llm:
        llm_text, fallback = rephrase(request.question, draft, passport)
        if llm_text is not None:
            text, mode = llm_text, "llm"

    return AssistantResponse(
        answer=text, mode=mode, intent=draft.intent, cited_evidence=draft.cited,
        blind_spots=draft.spots, limitations=limitations, fallback_reason=fallback)
