"""
Symptom Matcher — Weighted, alias-normalised symptom matching.

For each disease definition the matcher:
1. Builds an alias lookup table from symptoms.yaml.
2. Normalises patient symptom names to canonical names.
3. Computes a raw match score as the weighted sum of present symptoms.
4. Applies negation penalties for negated cardinal symptoms.
5. Returns a list of SymptomMatchResult sorted by raw_score descending.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer

logger = logging.getLogger(__name__)


@dataclass
class SymptomMatchResult:
    """Raw matching output for a single disease."""

    disease_id: str
    disease_name: str
    disease_category: str
    raw_score: float                         # before demographic/vitals modifiers
    max_possible_score: float               # max score if all symptoms present
    matched_cardinal: List[str] = field(default_factory=list)
    matched_supportive: List[str] = field(default_factory=list)
    missing_cardinal: List[str] = field(default_factory=list)
    negated_cardinal: List[str] = field(default_factory=list)
    negation_penalty: float = 0.0
    disease_definition: Dict[str, Any] = field(default_factory=dict)


def _build_alias_map(symptom_rules: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Return a dict mapping every alias (lower-cased) → canonical symptom name.
    The canonical name itself is also included as a key.
    """
    alias_map: Dict[str, str] = {}
    for entry in symptom_rules:
        canonical: str = entry.get("canonical", "").lower().strip()
        if not canonical:
            continue
        alias_map[canonical] = canonical
        for alias in entry.get("aliases", []):
            alias_map[alias.lower().strip()] = canonical
    return alias_map


def _normalise(name: str, alias_map: Dict[str, str]) -> str:
    """Return the canonical symptom name for the given name, or the name itself."""
    key = name.lower().strip()
    return alias_map.get(key, key)


def _partial_match(name: str, alias_map: Dict[str, str]) -> Optional[str]:
    """
    Attempt a substring / word-boundary partial match for symptom names that
    contain extra qualifiers (e.g. 'chest pain severe' → 'chest pain').
    """
    key = name.lower().strip()
    # Direct lookup first
    if key in alias_map:
        return alias_map[key]
    # Try all alias_map keys that appear as a substring of 'key'
    best: Optional[str] = None
    best_len = 0
    for alias, canonical in alias_map.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', key) and len(alias) > best_len:
            best = canonical
            best_len = len(alias)
    return best


class SymptomMatcher:
    """
    Matches a patient's symptom set against all disease definitions
    and returns weighted match results.
    """

    def __init__(
        self,
        disease_rules: List[Dict[str, Any]],
        symptom_rules: List[Dict[str, Any]],
    ) -> None:
        self._disease_rules = disease_rules
        self._alias_map = _build_alias_map(symptom_rules)

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def match(
        self,
        *,
        present_symptoms: List[Dict[str, Any]],
        negated_symptoms: List[str],
        tracer: ExplainabilityTracer,
    ) -> List[SymptomMatchResult]:
        """
        Run weighted symptom matching against all diseases.

        Parameters
        ----------
        present_symptoms:
            List of symptom dicts from ClinicalState.symptoms with
            status == 'Active'. Each dict has at least {'name': str}.
        negated_symptoms:
            List of symptom names that are explicitly absent/negated.
        tracer:
            Explainability tracer for recording matching steps.

        Returns
        -------
        List[SymptomMatchResult] sorted by raw_score descending.
        """
        # Normalise incoming symptom sets
        present_canonical: Set[str] = set()
        present_with_conf: Dict[str, float] = {}
        for sym in present_symptoms:
            raw_name = sym.get("name", "")
            canonical = _partial_match(raw_name, self._alias_map) or _normalise(raw_name, self._alias_map)
            conf_str = sym.get("confidence", "High")
            conf = self._conf_str_to_float(conf_str)
            present_canonical.add(canonical)
            # Keep the highest confidence seen for a given symptom
            present_with_conf[canonical] = max(present_with_conf.get(canonical, 0.0), conf)

        negated_canonical: Set[str] = {
            _partial_match(n, self._alias_map) or _normalise(n, self._alias_map)
            for n in negated_symptoms
        }

        results: List[SymptomMatchResult] = []

        for disease in self._disease_rules:
            result = self._match_disease(
                disease=disease,
                present=present_canonical,
                present_conf=present_with_conf,
                negated=negated_canonical,
                tracer=tracer,
            )
            tracer.increment_evaluated()
            if result.raw_score > 0 or result.negation_penalty > 0:
                tracer.increment_matched()
            results.append(result)

        results.sort(key=lambda r: r.raw_score - r.negation_penalty, reverse=True)
        return results

    # ──────────────────────────────────────────────
    # Internal matching logic
    # ──────────────────────────────────────────────

    def _match_disease(
        self,
        *,
        disease: Dict[str, Any],
        present: Set[str],
        present_conf: Dict[str, float],
        negated: Set[str],
        tracer: ExplainabilityTracer,
    ) -> SymptomMatchResult:
        """Compute the weighted match score for a single disease."""
        disease_id: str = disease.get("id", "unknown")
        disease_name: str = disease.get("name", disease_id)
        category: str = disease.get("category", "unknown")
        negation_penalty_per: float = float(disease.get("negation_penalty", 0.20))

        cardinal_syms: List[Dict[str, Any]] = disease.get("cardinal_symptoms", [])
        supportive_syms: List[Dict[str, Any]] = disease.get("supportive_symptoms", [])

        max_possible = sum(s.get("weight", 0.0) for s in cardinal_syms) + \
                       sum(s.get("weight", 0.0) for s in supportive_syms)

        raw_score = 0.0
        matched_cardinal: List[str] = []
        matched_supportive: List[str] = []
        missing_cardinal: List[str] = []
        negated_cardinal: List[str] = []
        total_negation_penalty = 0.0

        # ── Cardinal symptoms ──
        for sym_def in cardinal_syms:
            sym_name_raw: str = sym_def.get("name", "")
            weight: float = float(sym_def.get("weight", 0.0))
            canonical = _partial_match(sym_name_raw, self._alias_map) or _normalise(sym_name_raw, self._alias_map)

            if canonical in present:
                conf = present_conf.get(canonical, 1.0)
                contribution = weight * conf
                raw_score += contribution
                matched_cardinal.append(sym_name_raw)
                tracer.add_step(
                    component="Matcher",
                    description=f"Cardinal symptom '{sym_name_raw}' matched for {disease_name}",
                    input_facts=[f"symptom: {sym_name_raw} (canonical: {canonical}, confidence: {conf:.2f})"],
                    output=f"raw_score += {contribution:.3f} (weight={weight}, conf={conf:.2f})",
                    confidence_delta=contribution,
                )
            elif canonical in negated:
                total_negation_penalty += negation_penalty_per
                negated_cardinal.append(sym_name_raw)
                tracer.add_step(
                    component="Matcher",
                    description=f"Cardinal symptom '{sym_name_raw}' negated for {disease_name}",
                    input_facts=[f"symptom: {sym_name_raw} — negated/absent"],
                    output=f"negation_penalty += {negation_penalty_per:.3f}",
                    confidence_delta=-negation_penalty_per,
                )
            else:
                missing_cardinal.append(sym_name_raw)

        # ── Supportive symptoms ──
        for sym_def in supportive_syms:
            sym_name_raw = sym_def.get("name", "")
            weight = float(sym_def.get("weight", 0.0))
            canonical = _partial_match(sym_name_raw, self._alias_map) or _normalise(sym_name_raw, self._alias_map)

            if canonical in present:
                conf = present_conf.get(canonical, 1.0)
                contribution = weight * conf
                raw_score += contribution
                matched_supportive.append(sym_name_raw)
                tracer.add_step(
                    component="Matcher",
                    description=f"Supportive symptom '{sym_name_raw}' matched for {disease_name}",
                    input_facts=[f"symptom: {sym_name_raw} (confidence: {conf:.2f})"],
                    output=f"raw_score += {contribution:.3f}",
                    confidence_delta=contribution,
                )

        return SymptomMatchResult(
            disease_id=disease_id,
            disease_name=disease_name,
            disease_category=category,
            raw_score=raw_score,
            max_possible_score=max_possible if max_possible > 0 else 1.0,
            matched_cardinal=matched_cardinal,
            matched_supportive=matched_supportive,
            missing_cardinal=missing_cardinal,
            negated_cardinal=negated_cardinal,
            negation_penalty=total_negation_penalty,
            disease_definition=disease,
        )

    @staticmethod
    def _conf_str_to_float(conf: Any) -> float:
        """Convert a confidence string label or numeric to a float [0, 1]."""
        if isinstance(conf, (int, float)):
            return float(conf)
        mapping = {"high": 1.0, "medium": 0.75, "low": 0.5}
        return mapping.get(str(conf).lower(), 1.0)
