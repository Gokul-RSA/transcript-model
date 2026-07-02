import re
from typing import List, Optional
from app.services.clinical.models import DiagnosisEntity
from app.services.clinical.dictionary.loader import dictionary_manager
from app.services.clinical.extractors.negation import NegationDetector
from app.services.clinical.extractors.confidence import ConfidenceScorer

class DiagnosisExtractor:
    def __init__(self):
        self.negation_detector = NegationDetector()
        self.diseases_dict = dictionary_manager.get_diseases()

    def extract_diagnoses(self, text: str, speaker_id: Optional[str] = None) -> List[DiagnosisEntity]:
        results = []
        if not text or not text.strip():
            return results

        processed_text = self.negation_detector.expand_contractions(text)
        sentences = [s.strip() for s in re.split(r'[.!?\n]', processed_text) if s.strip()]
        if not sentences:
            sentences = [processed_text]

        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            for canonical, synonyms in self.diseases_dict.items():
                all_names = [canonical] + synonyms
                for name in all_names:
                    pattern = r'\b' + re.escape(name) + r'\b'
                    for match in re.finditer(pattern, sentence_lower):
                        span_start = match.start()
                        span_end = match.end()
                        
                        if not any(d.name == canonical for d in results):
                            is_neg = self.negation_detector.is_negated(sentence, name, span_start, span_end)
                            
                            # Expected speaker: Doctor diagnosing or patient stating medical history
                            expected_speaker = (speaker_id in ["doctor", "patient"])
                            
                            exact_match = (name.lower() == canonical.lower())
                            synonym_match = not exact_match

                            confidence_score = ConfidenceScorer.calculate_confidence(
                                exact_match=exact_match,
                                synonym_match=synonym_match,
                                expected_speaker=expected_speaker,
                                cross_turn_confirmed=False,
                                duration_attached=False,
                                severity_attached=False,
                                negation_ambiguity=False
                            )
                            
                            results.append(DiagnosisEntity(
                                name=canonical,
                                present=not is_neg,
                                confidence=confidence_score
                            ))
                            break
                            
        return results
