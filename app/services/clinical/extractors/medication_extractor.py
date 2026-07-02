import re
from typing import List, Optional
from app.services.clinical.models import MedicationEntity
from app.services.clinical.dictionary.loader import dictionary_manager
from app.services.clinical.extractors.negation import NegationDetector
from app.services.clinical.extractors.confidence import ConfidenceScorer

class MedicationExtractor:
    def __init__(self):
        self.negation_detector = NegationDetector()
        self.drugs_dict = dictionary_manager.get_drugs()

    def extract_medications(self, text: str, speaker_id: Optional[str] = None) -> List[MedicationEntity]:
        results = []
        if not text or not text.strip():
            return results

        processed_text = self.negation_detector.expand_contractions(text)
        sentences = [s.strip() for s in re.split(r'[.!?\n]', processed_text) if s.strip()]
        if not sentences:
            sentences = [processed_text]

        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            # Identify which drugs are mentioned
            detected_drugs = []
            for generic, brands in self.drugs_dict.items():
                all_names = [generic] + brands
                for name in all_names:
                    pattern = r'\b' + re.escape(name) + r'\b'
                    for match in re.finditer(pattern, sentence_lower):
                        span_start = match.start()
                        span_end = match.end()
                        if not any(d["start"] <= span_start and span_end <= d["end"] for d in detected_drugs):
                            detected_drugs.append({
                                "generic": generic,
                                "matched_name": name,
                                "start": span_start,
                                "end": span_end
                            })

            for drug in detected_drugs:
                # Extract dosage
                dose_match = re.search(r'\b(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|tablets?|capsules?|pills?))\b', sentence_lower)
                dosage = dose_match.group(1) if dose_match else None
                
                # Extract frequency
                freq_match = re.search(r'\b(twice daily|twice a day|three times a day|three times daily|four times a day|once daily|daily|every other day|regularly|at bedtime|before bedtime)\b', sentence_lower)
                frequency = freq_match.group(1).capitalize() if freq_match else None
                
                # Extract duration
                dur_match = re.search(r'\b(?:for)?\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten|several|a\s+few)\s*(?:day|week|month)s?\b', sentence_lower)
                duration = dur_match.group(0).strip() if dur_match else None
                if duration and duration.lower().startswith("for "):
                    duration = duration[4:]
                
                # Extract route
                route_match = re.search(r'\b(by mouth|oral|orally|intravenous|subcutaneous|topical|iv|im|po)\b', sentence_lower)
                route = route_match.group(1).capitalize() if route_match else None
                
                # Extract instructions
                inst_match = re.search(r'\b(after meals|before meals|with food|on an empty stomach|after food|before food|with meals)\b', sentence_lower)
                instructions = inst_match.group(1).capitalize() if inst_match else None
                
                # Extract PRN
                prn = any(prn_term in sentence_lower for prn_term in ["prn", "as needed", "if needed", "when required", "when necessary"])
                
                # Negation
                is_neg = self.negation_detector.is_negated(sentence, drug["matched_name"], drug["start"], drug["end"])
                
                # Expected speaker: Doctor prescribing, or patient taking
                expected_speaker = False
                if speaker_id == "doctor" and not is_neg:
                    expected_speaker = True
                elif speaker_id in ["patient", "attender"]:
                    expected_speaker = True

                # Confidence calculation
                exact_match = (drug["matched_name"].lower() == drug["generic"].lower())
                synonym_match = not exact_match

                # Check for negation ambiguity
                low_hedging = {"maybe", "perhaps", "possibly", "suspect", "suspected", "might"}
                negation_ambiguity = any(w in sentence_lower for w in low_hedging)

                confidence_score = ConfidenceScorer.calculate_confidence(
                    exact_match=exact_match,
                    synonym_match=synonym_match,
                    expected_speaker=expected_speaker,
                    cross_turn_confirmed=False,
                    duration_attached=bool(duration),
                    severity_attached=False,
                    negation_ambiguity=negation_ambiguity
                )

                results.append(MedicationEntity(
                    name=drug["generic"],
                    present=not is_neg,
                    confidence=confidence_score,
                    dosage=dosage,
                    frequency=frequency,
                    duration=duration,
                    route=route,
                    instructions=instructions,
                    prn=prn
                ))
        
        return results
