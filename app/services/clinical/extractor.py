import re
from typing import List, Optional, Dict, Any
from app.services.clinical.models import (
    SymptomEntity,
    MedicationEntity,
    DiagnosisEntity,
    ProcedureEntity,
    RiskFactorEntity,
    FamilyHistoryEntity
)

class ClinicalEntityExtractor:
    def __init__(self):
        # Define lists of clinical entities to detect
        self.symptom_terms = [
            "headache",
            "fever",
            "cough",
            "dizziness",
            "nausea",
            "vomiting",
            "fatigue",
            "chest pain",
            "shortness of breath"
        ]
        
        # Expanded severity terms (sorted by length descending for regex safety)
        self.severity_terms = [
            "very severe",
            "excruciating",
            "moderate",
            "extreme",
            "minimal",
            "severe",
            "slight",
            "mild"
        ]
        
        # Static duration terms
        self.duration_terms = [
            "today",
            "yesterday",
            "two days",
            "three days",
            "one week",
            "two weeks",
            "one month"
        ]
        
        self.medication_terms = [
            "paracetamol",
            "acetaminophen",
            "ibuprofen",
            "aspirin",
            "antibiotic",
            "antibiotics",
            "analgesic",
            "amlodipine"
        ]
        
        self.diagnosis_terms = [
            "hypertension",
            "diabetes",
            "migraine",
            "infection"
        ]
        
        self.procedure_terms = [
            "mri",
            "ct scan",
            "x-ray",
            "blood test"
        ]
        
        # Risk factor terms matching Box 4 of technical architecture
        self.risk_factor_terms = [
            "smoking",
            "smoke",
            "tobacco",
            "alcohol",
            "drinking",
            "obesity",
            "obese",
            "high cholesterol"
        ]
        
        # Family relationship terms matching Box 4
        self.family_members = [
            "mother",
            "father",
            "parent",
            "parents",
            "brother",
            "sister",
            "sibling",
            "family"
        ]

        # Negation triggers (extended with habit/risk factor cessation terms like 'stopped', 'quit', 'former')
        self.pre_negation_triggers = {
            "no", "not", "denies", "deny", "denied", "without", "never", 
            "negative", "don", "doesn", "didn", "haven", "hadn", "wasn", 
            "weren", "isn", "aren", "won", "wouldn", "shouldn", "couldn", 
            "does", "exclude", "excluded", "free", "stopped", "quit", 
            "ceased", "former", "ex"
        }
        
        self.post_negation_triggers = {
            "negative", "ruled", "resolved", "absent"
        }

    def _expand_contractions(self, text: str) -> str:
        """
        Expands common English contractions in the text to assist in accurate word-level negation parsing.
        """
        if not text:
            return ""
        
        contractions = {
            r"\bdon't\b": "do not",
            r"\bdoesn't\b": "does not",
            r"\bdidn't\b": "did not",
            r"\bhaven't\b": "have not",
            r"\bhadn't\b": "had not",
            r"\bwasn't\b": "was not",
            r"\bweren't\b": "were not",
            r"\bisn't\b": "is not",
            r"\baren't\b": "are not",
            r"\bwon't\b": "will not",
            r"\bwouldn't\b": "would not",
            r"\bshouldn't\b": "should not",
            r"\bcouldn't\b": "could not",
            r"\bcan't\b": "cannot"
        }
        
        expanded = text
        for pattern, replacement in contractions.items():
            expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
        return expanded

    def _is_question(self, text: str) -> bool:
        """
        Detects if a given text is a question.
        Checks for question marks or typical question-starting words.
        """
        text_stripped = text.strip()
        if not text_stripped:
            return False
        if text_stripped.endswith("?"):
            return True
        
        # Common question starting patterns (case-insensitive)
        question_starts = [
            r"^do\b", r"^does\b", r"^did\b", r"^have\b", r"^has\b", r"^had\b",
            r"^is\b", r"^are\b", r"^was\b", r"^were\b", r"^can\b", r"^could\b",
            r"^should\b", r"^would\b", r"^will\b", r"^what\b", r"^how\b", r"^why\b",
            r"^where\b", r"^when\b", r"^who\b", r"^any\b"
        ]
        # Check clean text prefix after stripping non-alphanumeric leading chars
        clean_text = re.sub(r'^[^\w]+', '', text_stripped).lower()
        for pattern in question_starts:
            if re.match(pattern, clean_text):
                return True
                
        return False

    def _is_negated(self, clause: str, entity_name: str, start_char: int, end_char: int) -> bool:
        """
        Determines if an entity mention in a clause is negated.
        Uses a sliding-window negation logic and handles double-negation edge cases.
        """
        clause_lower = clause.lower()
        
        # Check for double negations first (e.g., "not ruled out")
        # Double negation means the symptom IS present (negation is canceled)
        double_negations = ["not ruled out", "never ruled out", "cannot be ruled out", "not negative"]
        for dn in double_negations:
            if dn in clause_lower:
                return False

        # Get the prefix text in the clause before the entity
        prefix = clause[:start_char].strip()
        # Get the suffix text in the clause after the entity
        suffix = clause[end_char:].strip()
        
        # Tokenize prefix and suffix into words (ignoring punctuation)
        prefix_words = [w.lower() for w in re.findall(r'\b\w+\b', prefix)]
        suffix_words = [w.lower() for w in re.findall(r'\b\w+\b', suffix)]
        
        # Under clause-isolation, check the ENTIRE prefix for pre-negation triggers.
        for w in prefix_words:
            if w in self.pre_negation_triggers:
                return True
                
        # Check suffix for post-negation triggers (within a tight 3-word window)
        suffix_window = suffix_words[:3]
        for w in suffix_window:
            if w in self.post_negation_triggers:
                return True
                
        return False

    def _clean_duration_value(self, val: str) -> str:
        """
        Cleans extracted duration string by stripping leading 'for' or 'since' to isolate the core duration.
        """
        return re.sub(r'^(?:for|since)\s+', '', val, flags=re.IGNORECASE).strip()

    def _detect_durations(self, clause: str) -> List[Dict[str, Any]]:
        """
        Detects duration mentions in a clause using both static terms and flexible regex.
        Supports patterns like "since Monday", "for years", "for about a month", etc.
        """
        durations = []
        
        # 1. Regex patterns for flexible durations (with optional quantity)
        # Pattern A: "for [X] years/days/weeks/months"
        pattern_for = r'\bfor\s+(?:\d+(?:-\d+)?|about\s+a|several|a\s+few|a|one|two|three|four|five|six|seven)?\s*(?:day|week|month|year)s?\b'
        # Pattern B: "since [last] Monday/week/etc."
        pattern_since = r'\bsince\s+(?:last\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month|year|college|childhood)\b'
        
        for pattern in [pattern_for, pattern_since]:
            for match in re.finditer(pattern, clause, re.IGNORECASE):
                durations.append({
                    "value": self._clean_duration_value(match.group(0)),
                    "start": match.start()
                })
                
        # 2. Static duration terms
        for term in self.duration_terms:
            pattern = r'\b' + re.escape(term) + r'\b'
            for match in re.finditer(pattern, clause, re.IGNORECASE):
                # Avoid duplicate matches if already covered by regex
                if not any(d["start"] <= match.start() < d["start"] + len(d["value"]) for d in durations):
                    durations.append({
                        "value": self._clean_duration_value(term),
                        "start": match.start()
                    })
                    
        return durations

    def _consolidate_entities(self, results: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        """
        Deduplicates and consolidates extracted entities of the same type and name.
        Combines properties like severity and duration, and determines final negation status.
        """
        consolidated = {
            "symptoms": [],
            "medications": [],
            "diagnoses": [],
            "procedures": [],
            "risk_factors": [],
            "family_histories": []
        }

        # 1. Consolidate Symptoms
        symptom_groups = {}
        for sym in results["symptoms"]:
            symptom_groups.setdefault(sym.name.lower(), []).append(sym)
            
        for name, group in symptom_groups.items():
            any_present = any(s.present for s in group)
            
            final_severity = None
            for s in group:
                if s.severity:
                    final_severity = s.severity
                    break
            
            final_duration = None
            for s in group:
                if s.duration:
                    final_duration = s.duration
                    break
                    
            max_confidence = max(s.confidence for s in group)
            
            consolidated["symptoms"].append(SymptomEntity(
                name=group[0].name,
                severity=final_severity,
                duration=final_duration,
                present=any_present,
                confidence=max_confidence
            ))

        # 2. Consolidate Medications
        med_groups = {}
        for med in results["medications"]:
            med_groups.setdefault(med.name.lower(), []).append(med)
        for name, group in med_groups.items():
            any_present = any(m.present for m in group)
            consolidated["medications"].append(MedicationEntity(
                name=group[0].name,
                present=any_present,
                confidence=max(m.confidence for m in group)
            ))

        # 3. Consolidate Diagnoses
        diag_groups = {}
        for diag in results["diagnoses"]:
            diag_groups.setdefault(diag.name.lower(), []).append(diag)
        for name, group in diag_groups.items():
            any_present = any(d.present for d in group)
            consolidated["diagnoses"].append(DiagnosisEntity(
                name=group[0].name,
                present=any_present,
                confidence=max(d.confidence for d in group)
            ))

        # 4. Consolidate Procedures
        proc_groups = {}
        for proc in results["procedures"]:
            proc_groups.setdefault(proc.name.lower(), []).append(proc)
        for name, group in proc_groups.items():
            any_present = any(p.present for p in group)
            consolidated["procedures"].append(ProcedureEntity(
                name=group[0].name,
                present=any_present,
                confidence=max(p.confidence for p in group)
            ))
            
        # 5. Consolidate Risk Factors
        rf_groups = {}
        for rf in results.get("risk_factors", []):
            rf_groups.setdefault(rf.name.lower(), []).append(rf)
        for name, group in rf_groups.items():
            any_present = any(r.present for r in group)
            consolidated["risk_factors"].append(RiskFactorEntity(
                name=group[0].name,
                present=any_present,
                confidence=max(r.confidence for r in group)
            ))

        # 6. Consolidate Family Histories
        fh_groups = {}
        for fh in results.get("family_histories", []):
            key = f"{fh.relationship.lower()}:{fh.condition.lower()}"
            fh_groups.setdefault(key, []).append(fh)
        for key, group in fh_groups.items():
            any_present = any(f.present for f in group)
            consolidated["family_histories"].append(FamilyHistoryEntity(
                relationship=group[0].relationship,
                condition=group[0].condition,
                present=any_present,
                confidence=max(f.confidence for f in group)
            ))

        return consolidated

    def extract(self, text: str, speaker_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts clinical entities from text using deterministic, case-insensitive regex rules.
        Symptom entities are enriched with associated severity and duration found in proximity.
        Applies negation detection across all entities and uses clause boundaries to isolate context.
        
        CLINICIAN QUESTION IGNORING: If the speaker is a doctor and the text is a question,
        this method returns empty results to prevent clinician queries from registering as findings.
        """
        results = {
            "symptoms": [],
            "medications": [],
            "diagnoses": [],
            "procedures": [],
            "risk_factors": [],
            "family_histories": []
        }
        
        if not text or not text.strip():
            return results

        # Clinician Question Ignoring: If speaker is doctor and it's a question, ignore entirely.
        if speaker_id == "doctor" and self._is_question(text):
            return results

        # Pre-process text to expand contractions (assures negation tokens like 'not' are fully parsed)
        processed_text = self._expand_contractions(text)

        # 1. Split text into sentences
        sentences = [s.strip() for s in re.split(r'[.!?\n]', processed_text) if s.strip()]
        if not sentences:
            sentences = [processed_text]

        # 2. Process sentence-by-sentence and clause-by-clause
        for sentence in sentences:
            # Clause isolation: We split by semicolons and contrast conjunctions.
            # We do NOT split by commas here to avoid separating conversational negation prefixes
            # (e.g. "No, I don't have a fever") from the target entities.
            clauses = [c.strip() for c in re.split(r'[;]|\bbut\b|\bhowever\b|\balthough\b|\bexcept\b', sentence, flags=re.IGNORECASE) if c.strip()]
            if not clauses:
                clauses = [sentence]

            for clause in clauses:
                # --- Symptom Extraction ---
                detected_symptoms = []
                for term in self.symptom_terms:
                    pattern = r'\b' + re.escape(term) + r'\b'
                    for match in re.finditer(pattern, clause, re.IGNORECASE):
                        detected_symptoms.append({
                            "name": term,
                            "start": match.start(),
                            "end": match.end()
                        })
                
                if detected_symptoms:
                    # Detect severities in this clause
                    detected_severities = []
                    for term in self.severity_terms:
                        pattern = r'\b' + re.escape(term) + r'\b'
                        for match in re.finditer(pattern, clause, re.IGNORECASE):
                            # Overlap filtering: Avoid adding if this span is already covered by a longer match
                            span_start = match.start()
                            span_end = match.end()
                            if not any(s["start"] <= span_start and span_end <= s["end"] for s in detected_severities):
                                detected_severities.append({
                                    "value": term,
                                    "start": span_start,
                                    "end": span_end
                                })
                    
                    # Detect durations in this clause using the upgraded detector
                    detected_durations = self._detect_durations(clause)
                    
                    # Associate and check negation for each symptom in the clause
                    for sym in detected_symptoms:
                        associated_severity = None
                        if detected_severities:
                            closest_sev = min(detected_severities, key=lambda x: abs(x["start"] - sym["start"]))
                            associated_severity = closest_sev["value"]
                        
                        associated_duration = None
                        if detected_durations:
                            closest_dur = min(detected_durations, key=lambda x: abs(x["start"] - sym["start"]))
                            associated_duration = closest_dur["value"]
                        
                        is_neg = self._is_negated(clause, sym["name"], sym["start"], sym["end"])
                        
                        results["symptoms"].append(SymptomEntity(
                            name=sym["name"],
                            severity=associated_severity,
                            duration=associated_duration,
                            present=not is_neg,
                            confidence=1.0
                        ))

                # --- Medication Extraction ---
                for term in self.medication_terms:
                    pattern = r'\b' + re.escape(term) + r'\b'
                    for match in re.finditer(pattern, clause, re.IGNORECASE):
                        is_neg = self._is_negated(clause, term, match.start(), match.end())
                        results["medications"].append(MedicationEntity(
                            name=term,
                            present=not is_neg,
                            confidence=1.0
                        ))

                # --- Diagnosis Extraction ---
                for term in self.diagnosis_terms:
                    pattern = r'\b' + re.escape(term) + r'\b'
                    for match in re.finditer(pattern, clause, re.IGNORECASE):
                        is_neg = self._is_negated(clause, term, match.start(), match.end())
                        results["diagnoses"].append(DiagnosisEntity(
                            name=term,
                            present=not is_neg,
                            confidence=1.0
                        ))

                # --- Procedure Extraction ---
                for term in self.procedure_terms:
                    pattern = r'\b' + re.escape(term) + r'\b'
                    for match in re.finditer(pattern, clause, re.IGNORECASE):
                        is_neg = self._is_negated(clause, term, match.start(), match.end())
                        
                        canonical_name = term
                        if term.lower() == "mri":
                            canonical_name = "MRI"
                        elif term.lower() == "ct scan":
                            canonical_name = "CT scan"
                        elif term.lower() == "x-ray":
                            canonical_name = "X-ray"
                        elif term.lower() == "blood test":
                            canonical_name = "blood test"
                        
                        results["procedures"].append(ProcedureEntity(
                            name=canonical_name,
                            present=not is_neg,
                            confidence=1.0
                        ))
                        
                # --- Risk Factor Extraction ---
                for term in self.risk_factor_terms:
                    pattern = r'\b' + re.escape(term) + r'\b'
                    for match in re.finditer(pattern, clause, re.IGNORECASE):
                        is_neg = self._is_negated(clause, term, match.start(), match.end())
                        
                        canonical_name = term
                        if term == "smoke":
                            canonical_name = "smoking"
                        elif term == "obese":
                            canonical_name = "obesity"
                        elif term == "drinking":
                            canonical_name = "alcohol"
                            
                        results["risk_factors"].append(RiskFactorEntity(
                            name=canonical_name,
                            present=not is_neg,
                            confidence=1.0
                        ))
                        
                # --- Family History Extraction ---
                # Find all family members with their offsets in the clause
                detected_families = []
                for fm in self.family_members:
                    pattern = r'\b' + re.escape(fm) + r'\b'
                    for match in re.finditer(pattern, clause, re.IGNORECASE):
                        detected_families.append({
                            "relationship": fm,
                            "start": match.start()
                        })
                        
                if detected_families:
                    # Check if a disease condition is also mentioned in the same clause
                    conditions_to_check = self.diagnosis_terms + self.symptom_terms + ["cancer", "heart disease"]
                    for cond in conditions_to_check:
                        cond_pattern = r'\b' + re.escape(cond) + r'\b'
                        for match in re.finditer(cond_pattern, clause, re.IGNORECASE):
                            # Associate this condition with the closest family member in the clause
                            closest_fm = min(detected_families, key=lambda x: abs(x["start"] - match.start()))
                            
                            is_neg = self._is_negated(clause, cond, match.start(), match.end())
                            results["family_histories"].append(FamilyHistoryEntity(
                                relationship=closest_fm["relationship"],
                                condition=cond,
                                present=not is_neg,
                                confidence=1.0
                            ))

        # Apply Entity Deduplication and Consolidation
        return self._consolidate_entities(results)
