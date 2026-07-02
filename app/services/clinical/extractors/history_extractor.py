import re
from typing import List, Dict, Any, Optional
from app.services.clinical.models import FamilyHistoryEntity, RiskFactorEntity
from app.services.clinical.dictionary.loader import dictionary_manager
from app.services.clinical.extractors.negation import NegationDetector
from app.services.clinical.extractors.confidence import ConfidenceScorer

class HistoryExtractor:
    def __init__(self):
        self.negation_detector = NegationDetector()
        self.family_dict = dictionary_manager.get_family()
        self.diseases_dict = dictionary_manager.get_diseases()
        self.symptoms_dict = dictionary_manager.get_symptoms()
        
        # Risk factor keywords and terms (social history)
        self.risk_factor_terms = {
            "smoking": ["smoking", "smoke", "smoker", "cigarettes", "tobacco", "nicotine"],
            "alcohol": ["alcohol", "drinking", "drink", "beer", "wine", "liquor", "social drinker"],
            "drug abuse": ["recreational drugs", "drug abuse", "drugs", "marijuana", "cocaine", "heroin", "substance use"],
            "obesity": ["obesity", "obese", "overweight"],
            "high cholesterol": ["high cholesterol", "hypercholesterolemia", "cholesterol problem"],
            "occupation": ["occupation", "job", "works as", "employed", "retired", "student", "occupation is"],
            "exercise": ["exercise", "working out", "runs", "gym", "sedentary", "physical activity"],
            "diet": ["diet", "eating habits", "vegan", "vegetarian", "nutrition"]
        }

    def extract_history(self, text: str, speaker_id: Optional[str] = None) -> Dict[str, List[Any]]:
        results = {
            "risk_factors": [],
            "family_histories": []
        }
        
        if not text or not text.strip():
            return results

        processed_text = self.negation_detector.expand_contractions(text)
        sentences = [s.strip() for s in re.split(r'[.!?\n]', processed_text) if s.strip()]
        if not sentences:
            sentences = [processed_text]

        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            # 1. Family History Extraction
            detected_family_members = []
            for relation, synonyms in self.family_dict.items():
                all_syns = [relation] + synonyms
                for syn in all_syns:
                    pattern = r'\b' + re.escape(syn) + r'\b'
                    for match in re.finditer(pattern, sentence_lower):
                        detected_family_members.append({
                            "relationship": relation,
                            "start": match.start(),
                            "end": match.end()
                        })

            if detected_family_members:
                conditions_to_check = (
                    list(self.diseases_dict.keys()) + 
                    list(self.symptoms_dict.keys()) + 
                    ["cancer", "heart disease", "stroke", "high blood pressure", "hypertension", "diabetes", "asthma"]
                )
                conditions_to_check = list(set(conditions_to_check))
                
                for cond in conditions_to_check:
                    cond_pattern = r'\b' + re.escape(cond) + r'\b'
                    for match in re.finditer(cond_pattern, sentence_lower):
                        closest_fm = min(detected_family_members, key=lambda x: abs(x["start"] - match.start()))
                        is_neg = self.negation_detector.is_negated(sentence, cond, match.start(), match.end())
                        
                        expected_speaker = (speaker_id == "patient")
                        confidence_score = ConfidenceScorer.calculate_confidence(
                            exact_match=True,
                            synonym_match=False,
                            expected_speaker=expected_speaker,
                            cross_turn_confirmed=False,
                            duration_attached=False,
                            severity_attached=False,
                            negation_ambiguity=False
                        )
                        
                        results["family_histories"].append(FamilyHistoryEntity(
                            relationship=closest_fm["relationship"],
                            condition=cond,
                            present=not is_neg,
                            confidence=confidence_score
                        ))

            # 2. Risk Factors (Social History) - processed clause-by-clause
            clauses = [c.strip() for c in re.split(r'[;,]|\bbut\b|\bhowever\b|\balthough\b|\bexcept\b', sentence, flags=re.IGNORECASE) if c.strip()]
            if not clauses:
                clauses = [sentence]

            for clause in clauses:
                clause_lower = clause.lower()
                for rf_canonical, synonyms in self.risk_factor_terms.items():
                    for syn in synonyms:
                        pattern = r'\b' + re.escape(syn) + r'\b'
                        for match in re.finditer(pattern, clause_lower):
                            is_neg = self.negation_detector.is_negated(clause, syn, match.start(), match.end())
                            
                            expected_speaker = (speaker_id == "patient")
                            
                            if rf_canonical == "smoking" and any(q in clause_lower for q in ["stopped", "quit", "former", "non-smoker"]):
                                is_neg = True
                            if rf_canonical == "alcohol" and any(q in clause_lower for q in ["stopped", "quit", "non-drinker"]):
                                is_neg = True

                            confidence_score = ConfidenceScorer.calculate_confidence(
                                exact_match=(syn.lower() == rf_canonical.lower()),
                                synonym_match=(syn.lower() != rf_canonical.lower()),
                                expected_speaker=expected_speaker,
                                cross_turn_confirmed=False,
                                duration_attached=False,
                                severity_attached=False,
                                negation_ambiguity=False
                            )
                            
                            # Deduplicate within this turn
                            if not any(r.name == rf_canonical for r in results["risk_factors"]):
                                results["risk_factors"].append(RiskFactorEntity(
                                    name=rf_canonical,
                                    present=not is_neg,
                                    confidence=confidence_score
                                ))
                        
        return results
