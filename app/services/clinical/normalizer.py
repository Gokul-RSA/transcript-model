import re

class ClinicalNormalizer:
    def __init__(self):
        # Mappings of colloquial layman/descriptive terms to canonical terms.
        # We use regex with word boundaries and support flexible spacing and hyphens.
        self.mappings = {
            # Headache variations (e.g. "head ache", "headaches")
            r"\bhead\s+ache\b": "headache",
            r"\bheadaches\b": "headache",
            r"\bhead\s+(?:is\s+|has\s+been\s+|was\s+)?pounding\b": "headache",
            r"\bpounding\s+head\b": "headache",
            
            # Dizziness variations (e.g. "dizzy", "light-headed")
            r"\bdizzy\b": "dizziness",
            r"\blight\s*-?\s*headed\b": "dizziness",
            r"\broom\s+is\s+spinning\b": "dizziness",
            
            # Nausea and vomiting variations (e.g. "nauseous", "throwing up", "vomited")
            r"\bnauseous\b": "nausea",
            r"\bthrowing\s*-?\s*up\b": "nausea",
            r"\bsick\s+to\s+my\s+stomach\b": "nausea",
            r"\bvomited\b": "vomiting",
            r"\bvomiting\b": "vomiting",
            
            # Shortness of breath variations
            r"\bdifficulty\s+breathing\b": "shortness of breath",
            r"\bbreathless\b": "shortness of breath",
            
            # Plurals and general variations
            r"\bfevers\b": "fever",
            r"\bcoughs\b": "cough",
            r"\bmigraines\b": "migraine",
            r"\binfections\b": "infection",
            
            # General mappings
            r"\bhigh\s+blood\s+pressure\b": "hypertension",
            r"\bblood\s+sugar\s+problem\b": "diabetes",
            r"\bpain\s*-?\s*killers?\b": "analgesic"
        }

    def normalize(self, text: str) -> str:
        """
        Normalizes colloquial layman clinical terms to their canonical equivalents.
        Handles complex multi-word variations and punctuation boundaries.
        """
        if not text:
            return ""
        
        normalized_text = text
        for pattern, replacement in self.mappings.items():
            normalized_text = re.sub(pattern, replacement, normalized_text, flags=re.IGNORECASE)
        
        return normalized_text
