import re
from typing import Optional

class NameExtractor:
    def __init__(self):
        # Name extraction patterns (with optional title period support)
        self.intro_patterns = [
            r"\b(?:my\s+name\s+is|i'm|i\s+am|called|call\s+me)\s+((?:mr\b\.?|mrs\b\.?|ms\b\.?|miss\b|dr\b\.?)\s*[A-Z][a-zA-Z]+)\b",
            r"\b(?:my\s+name\s+is|i'm|i\s+am|called|call\s+me)\s+([A-Z][a-zA-Z]+)\b",
            r"\bthis\s+is\s+((?:mr\b\.?|mrs\b\.?|ms\b\.?|miss\b|dr\b\.?)\s*[A-Z][a-zA-Z]+)\s+speaking\b",
            r"\bthis\s+is\s+([A-Z][a-zA-Z]+)\s+speaking\b"
        ]
        self.addressing_patterns = [
            r"\b(?:hello|hi|morning|good\s+morning|afternoon|good\s+afternoon|evening|good\s+evening)\s*,?\s*((?:mr\b\.?|mrs\b\.?|ms\b\.?|miss\b|dr\b\.?)\s*[A-Z][a-zA-Z]+)\b",
            r"\b(?:hello|hi|morning|good\s+morning|afternoon|good\s+afternoon|evening|good\s+evening)\s+([A-Z][a-zA-Z]+)\b"
        ]

    def extract_name(self, text: str, speaker_id: Optional[str] = None) -> Optional[str]:
        """
        Extracts patient name from natural conversations.
        Avoids doctor names and doctor introductions.
        """
        if not text:
            return None

        # 1. If speaker is a doctor, they might be introducing themselves and/or addressing the patient.
        # We look for addressing patterns directly.
        if speaker_id == "doctor":
            for pattern in self.addressing_patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    candidate = match.group(1).strip()
                    # A doctor won't address another doctor as the patient under normal consultation flows.
                    if not candidate.lower().startswith("dr"):
                        return candidate
            return None

        # 2. If speaker is patient (or unknown/default), check introductions first
        for pattern in self.intro_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                return candidate

        # Fallback check for addressing patterns in patient turns
        for pattern in self.addressing_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if not candidate.lower().startswith("dr"):
                    return candidate

        return None
