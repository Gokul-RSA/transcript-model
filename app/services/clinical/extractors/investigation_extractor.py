import re
from typing import List, Optional
from app.services.clinical.models import ProcedureEntity
from app.services.clinical.dictionary.loader import dictionary_manager
from app.services.clinical.extractors.negation import NegationDetector
from app.services.clinical.extractors.confidence import ConfidenceScorer

class InvestigationExtractor:
    def __init__(self):
        self.negation_detector = NegationDetector()
        self.procedures_dict = dictionary_manager.get_procedures()

    def extract_investigations(self, text: str, speaker_id: Optional[str] = None) -> List[ProcedureEntity]:
        results = []
        if not text or not text.strip():
            return results

        processed_text = self.negation_detector.expand_contractions(text)
        sentences = [s.strip() for s in re.split(r'[.!?\n]', processed_text) if s.strip()]
        if not sentences:
            sentences = [processed_text]

        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            for canonical, synonyms in self.procedures_dict.items():
                all_names = [canonical] + synonyms
                for name in all_names:
                    pattern = r'\b' + re.escape(name) + r'\b'
                    for match in re.finditer(pattern, sentence_lower):
                        span_start = match.start()
                        span_end = match.end()
                        
                        # Overlap check
                        if not any(p.name == canonical for p in results):
                            is_neg = self.negation_detector.is_negated(sentence, name, span_start, span_end)
                            
                            # Expected speaker: Doctor ordering or patient reporting
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
                            
                            results.append(ProcedureEntity(
                                name=canonical,
                                present=not is_neg,
                                confidence=confidence_score
                            ))
                            break # Match found, move to next procedure type
                            
        return results
