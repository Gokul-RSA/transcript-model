from typing import Union

class ConfidenceScorer:
    @staticmethod
    def calculate_confidence(
        exact_match: bool,
        synonym_match: bool,
        expected_speaker: bool,
        cross_turn_confirmed: bool,
        duration_attached: bool,
        severity_attached: bool,
        negation_ambiguity: bool
    ) -> float:
        # Start with a baseline score of 0.50
        score = 0.50
        
        if exact_match:
            score += 0.40
        elif synonym_match:
            score += 0.20
            
        if expected_speaker:
            score += 0.10
            
        if cross_turn_confirmed:
            score += 0.15
            
        if duration_attached:
            score += 0.05
            
        if severity_attached:
            score += 0.05
            
        if negation_ambiguity:
            score -= 0.20
            
        # Bound score between 0.0 and 1.0
        return max(0.0, min(1.0, score))

    @staticmethod
    def get_confidence_label(score: float) -> str:
        if score > 0.85:
            return "High"
        elif score >= 0.60:
            return "Medium"
        else:
            return "Low"
