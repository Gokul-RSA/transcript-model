import re

class ClinicalTerminologyNormalizer:
    def __init__(self):
        # Layman term to standardized clinical terminology mapping
        self.mapping = {
            "high blood pressure": "hypertension",
            "low blood sugar": "hypoglycemia",
            "heart attack": "myocardial infarction",
            "high blood sugar": "hyperglycemia",
            "stroke": "cerebrovascular accident",
            "blood thinner": "anticoagulant",
            "fever medicine": "antipyretic",
            "pain killer": "analgesic",
            "shortness of breath": "dyspnea",
            "chest pain": "angina",
            "high cholesterol": "hyperlipidemia",
            "swelling": "edema",
            "fainting": "syncope",
            "kidney failure": "renal failure",
            "stomach flu": "gastroenteritis",
            "acid reflux": "GERD"
        }
        # Sort keys by length descending to match longer multi-word phrases first
        sorted_keys = sorted(self.mapping.keys(), key=len, reverse=True)
        escaped_keys = [re.escape(k) for k in sorted_keys]
        # Compile a case-insensitive pattern with word boundaries
        self.pattern = re.compile(r'\b(' + '|'.join(escaped_keys) + r')\b', re.IGNORECASE)

    def _preserve_case(self, original: str, replacement: str) -> str:
        """
        Helper method to adapt the replacement word to match the capitalization style
        of the original layman phrase.
        """
        # 1. All Uppercase
        if original.isupper():
            return replacement.upper()
        # 2. All Lowercase
        if original.islower():
            return replacement.lower()
        # 3. Title Case (e.g. "High Blood Pressure" -> "Hypertension")
        words = original.split()
        if len(words) > 1 and all(w[0].isupper() for w in words if w):
            return replacement.title()
        # 4. First Letter Capitalized (e.g. "High blood pressure" -> "Hypertension")
        if original and original[0].isupper():
            return replacement[0].upper() + replacement[1:]
        # Fallback
        return replacement

    def normalize(self, text: str) -> str:
        if not text:
            return ""

        def replace_match(match):
            matched_text = match.group(0)
            layman_term = matched_text.lower()
            medical_term = self.mapping.get(layman_term, layman_term)
            return self._preserve_case(matched_text, medical_term)

        return self.pattern.sub(replace_match, text)
