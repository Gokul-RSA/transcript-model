import re
from app.services.clinical.dictionary.loader import dictionary_manager

class ClinicalNormalizer:
    def __init__(self):
        self.mappings = {}
        self._build_mappings()

    def _build_mappings(self):
        # 1. Load from symptoms dictionary
        symptoms = dictionary_manager.get_symptoms()
        for canonical, synonyms in symptoms.items():
            for syn in synonyms:
                if syn.lower() != canonical.lower():
                    # Create word boundary pattern (handling variable spacing/hyphens)
                    escaped = re.escape(syn)
                    # Normalize spaces/hyphens in regex
                    pattern_str = r'\b' + re.sub(r'\\\s+|\\-', lambda m: r'\s*-?\s*', escaped) + r'\b'
                    self.mappings[pattern_str] = canonical

        # 2. Load from diseases dictionary
        diseases = dictionary_manager.get_diseases()
        for canonical, synonyms in diseases.items():
            for syn in synonyms:
                if syn.lower() != canonical.lower():
                    escaped = re.escape(syn)
                    pattern_str = r'\b' + re.sub(r'\\\s+|\\-', lambda m: r'\s*-?\s*', escaped) + r'\b'
                    self.mappings[pattern_str] = canonical

        # 3. Load from drug dictionary (brand-to-generic and colloquial painkiller terms)
        drugs = dictionary_manager.get_drugs()
        for canonical, synonyms in drugs.items():
            for syn in synonyms:
                if syn.lower() != canonical.lower():
                    escaped = re.escape(syn)
                    pattern_str = r'\b' + re.sub(r'\\\s+|\\-', lambda m: r'\s*-?\s*', escaped) + r'\b'
                    self.mappings[pattern_str] = canonical

    def normalize(self, text: str) -> str:
        """
        Normalizes colloquial layman clinical terms to their canonical equivalents.
        Handles complex multi-word variations and punctuation boundaries.
        """
        if not text:
            return ""
        
        # We process replacements case-sensitively or preserve case if possible,
        # but standard is lowercased canonical output.
        # To maintain the case preservation requirement from existing tests:
        # e.g., "High blood pressure" -> "Hypertension"
        # We can implement a smart case-preserving replacement helper.
        normalized_text = text
        for pattern_str, replacement in self.mappings.items():
            def case_preserve_replace(match):
                matched_text = match.group(0)
                if matched_text.isupper():
                    return replacement.upper()
                if matched_text[0].isupper():
                    # Title case the canonical term
                    return ' '.join(w.capitalize() for w in replacement.split(' '))
                return replacement

            normalized_text = re.sub(pattern_str, case_preserve_replace, normalized_text, flags=re.IGNORECASE)
        
        return normalized_text
