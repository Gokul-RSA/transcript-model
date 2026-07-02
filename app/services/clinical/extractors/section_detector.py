import re
from typing import Dict
from threading import RLock

class SectionDetector:
    def __init__(self):
        self._session_sections: Dict[str, str] = {}
        self._lock = RLock()
        
        # Define keywords for transitioning to clinical sections
        self._section_patterns = {
            "Greeting": [
                r"\b(?:hello|hi|good\s+morning|good\s+afternoon|good\s+evening|how\s+are\s+you|how\s+can\s+i\s+help|welcome|greeting)\b"
            ],
            "Chief Complaint": [
                r"\b(?:brings\s+you\s+in|brought\s+you\s+in|reason\s+for\s+visit|chief\s+complaint|complaining\s+of|what\s+seems\s+to\s+be\s+the\s+problem|what\s+can\s+i\s+do|symptoms\s+today)\b"
            ],
            "History of Present Illness": [
                r"\b(?:when\s+did\s+it\s+start|since\s+when|how\s+long|getting\s+worse|getting\s+better|radiat|where\s+does\s+it\s+hurt|severity|triggers|relieving|pain\s+scale)\b"
            ],
            "Past History": [
                r"\b(?:past\s+medical\s+history|any\s+other\s+illnesses|history\s+of|family\s+history|any\s+surgeries|medical\s+conditions\s+in\s+the\s+past|had\s+this\s+before|diagnosed\s+with|father\s+has|mother\s+had)\b"
            ],
            "Medication Review": [
                r"\b(?:current\s+medications|taking\s+any\s+medicine|on\s+any\s+pills|prescriptions\s+you\s+are\s+on|taking\s+regularly|drugs\s+you\s+take|medications|medicine|drugs|pills|prescriptions)\b"
            ],
            "Examination": [
                r"\b(?:let\s+me\s+check|take\s+your\s+blood\s+pressure|listen\s+to\s+your\s+lungs|examine\s+you|on\s+the\s+scale|temp\s+is|bp\s+is|heart\s+rate|pulse\s+is|oxygen\s+sat|pulse\s+was|check\s+your|examination|check)\b"
            ],
            "Assessment": [
                r"\b(?:looks\s+like|diagnosis\s+is|tentative\s+diagnosis|i\s+think\s+it\s+is|rule\s+out|r/o|diagnose|could\s+be\s+a\s+case\s+of|suspect\s+a|suspect|diagnosis|diagnosed)\b"
            ],
            "Treatment": [
                r"\b(?:prescribe|take\s+these|take\s+paracetamol|take\s+ibuprofen|dosage|twice\s+daily|stay\s+hydrated|treatment\s+plan|medication\s+plan|advice\s+you\s+to|prescriptions)\b"
            ],
            "Follow-up": [
                r"\b(?:come\s+back|visit\s+again|see\s+you\s+in|follow\s*up|appointment\s+next\s+week|review\s+after|see\s+you\s+again|return\s+to\s+clinic)\b"
            ]
        }

    def detect_section(self, session_id: str, text: str, speaker_id: str) -> str:
        """
        Statefully detects the current section of the consultation based on speaker prompts
        and keywords in the transcript.
        """
        text_lower = text.lower()
        
        with self._lock:
            current_section = self._session_sections.setdefault(session_id, "Greeting")
            
            # Clinician questions/prompts are the primary driver of section transitions.
            for section, patterns in self._section_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, text_lower):
                        self._session_sections[session_id] = section
                        return section
                        
            return current_section

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._session_sections.pop(session_id, None)
