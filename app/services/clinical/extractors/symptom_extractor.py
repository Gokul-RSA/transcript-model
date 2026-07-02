import re
from typing import List, Dict, Any, Optional
from app.services.clinical.models import SymptomEntity
from app.services.clinical.dictionary.loader import dictionary_manager
from app.services.clinical.extractors.negation import NegationDetector
from app.services.clinical.extractors.confidence import ConfidenceScorer
from app.services.clinical.extractors.context import context_manager

class SymptomExtractor:
    def __init__(self):
        self.negation_detector = NegationDetector()
        self.symptoms_dict = dictionary_manager.get_symptoms()
        self.anatomy_dict = dictionary_manager.get_anatomy()
        
        # Expanded severity terms
        self.severity_terms = [
            "very severe", "excruciating", "moderate", "extreme", 
            "minimal", "severe", "slight", "mild"
        ]
        
        # General duration terms
        self.duration_terms = [
            "today", "yesterday", "two days", "three days", 
            "one week", "two weeks", "one month"
        ]

    def _clean_duration_value(self, val: str) -> str:
        return re.sub(r'^(?:for|since)\s+', '', val, flags=re.IGNORECASE).strip()

    def _detect_durations(self, clause: str) -> List[Dict[str, Any]]:
        durations = []
        # Pattern A: "for [X] years/days/weeks/months"
        pattern_for = r'\bfor\s+(?:\d+(?:-\d+)?|about\s+a|several|a\s+few|a|one|two|three|four|five|six|seven)?\s*(?:day|week|month|year)s?\b'
        # Pattern B: "since [last] Monday/week/etc."
        pattern_since = r'\bsince\s+(?:last\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month|year|college|childhood|yesterday|surgery)\b'
        # Pattern C: "on and off for [X]"
        pattern_on_off = r'\bon\s+and\s+off\s+for\s+\w+\s*(?:day|week|month|year)s?\b'
        
        for pattern in [pattern_for, pattern_since, pattern_on_off]:
            for match in re.finditer(pattern, clause, re.IGNORECASE):
                durations.append({
                    "value": self._clean_duration_value(match.group(0)),
                    "start": match.start()
                })
                
        for term in self.duration_terms:
            pattern = r'\b' + re.escape(term) + r'\b'
            for match in re.finditer(pattern, clause, re.IGNORECASE):
                if not any(d["start"] <= match.start() < d["start"] + len(d["value"]) for d in durations):
                    durations.append({
                        "value": self._clean_duration_value(term),
                        "start": match.start()
                    })
        return durations

    def extract_symptoms(self, text: str, speaker_id: Optional[str] = None, session_id: Optional[str] = None, section: str = "Chief Complaint") -> List[SymptomEntity]:
        results = []
        if not text or not text.strip():
            return results

        processed_text = self.negation_detector.expand_contractions(text)
        sentences = [s.strip() for s in re.split(r'[.!?\n]', processed_text) if s.strip()]
        if not sentences:
            sentences = [processed_text]

        entity_counter = 0

        for sentence in sentences:
            # Clause isolation
            clauses = [c.strip() for c in re.split(r'[;]|\bbut\b|\bhowever\b|\balthough\b|\bexcept\b', sentence, flags=re.IGNORECASE) if c.strip()]
            if not clauses:
                clauses = [sentence]

            for clause in clauses:
                detected_symptoms = []
                
                # Search symptoms
                for canonical, synonyms in self.symptoms_dict.items():
                    # We check the canonical term and all synonyms
                    all_syns = [canonical] + synonyms
                    for term in all_syns:
                        pattern = r'\b' + re.escape(term) + r'\b'
                        for match in re.finditer(pattern, clause, re.IGNORECASE):
                            # Overlap check
                            span_start = match.start()
                            span_end = match.end()
                            if not any(s["start"] <= span_start and span_end <= s["end"] for s in detected_symptoms):
                                detected_symptoms.append({
                                    "name": canonical,
                                    "matched_text": term,
                                    "start": span_start,
                                    "end": span_end
                                })

                if detected_symptoms:
                    # Detect severities
                    detected_severities = []
                    for term in self.severity_terms:
                        pattern = r'\b' + re.escape(term) + r'\b'
                        for match in re.finditer(pattern, clause, re.IGNORECASE):
                            span_start = match.start()
                            span_end = match.end()
                            if not any(s["start"] <= span_start and span_end <= s["end"] for s in detected_severities):
                                detected_severities.append({
                                    "value": term,
                                    "start": span_start,
                                    "end": span_end
                                })
                    
                    # Detect durations
                    detected_durations = self._detect_durations(clause)

                    # Map modifiers to closest symptoms in the clause
                    def find_closest_symptom(pos, symptoms):
                        if not symptoms:
                            return None
                        return min(symptoms, key=lambda s: abs(s["start"] - pos))

                    severity_mapping = {}
                    for sev in detected_severities:
                        closest_sym = find_closest_symptom(sev["start"], detected_symptoms)
                        if closest_sym:
                            key = (closest_sym["name"], closest_sym["start"])
                            severity_mapping[key] = sev

                    duration_mapping = {}
                    for dur in detected_durations:
                        closest_sym = find_closest_symptom(dur["start"], detected_symptoms)
                        if closest_sym:
                            key = (closest_sym["name"], closest_sym["start"])
                            duration_mapping[key] = dur

                    for sym in detected_symptoms:
                        key = (sym["name"], sym["start"])
                        
                        sev_match = severity_mapping.get(key)
                        associated_severity = sev_match["value"] if sev_match else None
                        if not associated_severity and len(detected_symptoms) == 1 and detected_severities:
                            associated_severity = detected_severities[0]["value"]

                        dur_match = duration_mapping.get(key)
                        associated_duration = dur_match["value"] if dur_match else None
                        if not associated_duration and len(detected_symptoms) == 1 and detected_durations:
                            associated_duration = detected_durations[0]["value"]

                        # Negation detection
                        is_neg = self.negation_detector.is_negated(clause, sym["matched_text"], sym["start"], sym["end"])

                        # Expected speaker scoring logic: Patient reports symptoms
                        expected_speaker = (speaker_id == "patient")

                        # Ambiguity and confirmation features can be integrated via the context manager
                        exact_match = (sym["matched_text"].lower() == sym["name"].lower())
                        synonym_match = not exact_match

                        # Check for negation ambiguity (like hedging words in the clause)
                        low_hedging = {"maybe", "perhaps", "possibly", "suspect", "suspected", "might"}
                        negation_ambiguity = any(w in clause.lower() for w in low_hedging)

                        confidence_score = ConfidenceScorer.calculate_confidence(
                            exact_match=exact_match,
                            synonym_match=synonym_match,
                            expected_speaker=expected_speaker,
                            cross_turn_confirmed=False,  # Can be updated statefully later
                            duration_attached=bool(associated_duration),
                            severity_attached=bool(associated_severity),
                            negation_ambiguity=negation_ambiguity
                        )

                        results.append(SymptomEntity(
                            name=sym["name"],
                            severity=associated_severity,
                            duration=associated_duration,
                            present=not is_neg,
                            confidence=confidence_score
                        ))

        return results
