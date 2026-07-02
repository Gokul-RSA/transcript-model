import re
from typing import Dict, Optional

class VitalsExtractor:
    def extract_vitals(self, text: str) -> Dict[str, Optional[str]]:
        results = {
            "bp": None,
            "pulse": None,
            "temperature": None,
            "spo2": None,
            "weight": None,
            "height": None
        }
        
        if not text:
            return results

        text_lower = text.lower()

        # BP
        bp_match = re.search(r'\b(?:bp|blood\s+pressure)\s*(?:is|of|was|be|at)?\s*(\d{2,3}\s*/\s*\d{2,3})\b', text_lower)
        if bp_match:
            results["bp"] = bp_match.group(1).replace(" ", "")

        # Pulse
        pulse_match = re.search(r'\b(?:pulse|heart\s+rate|hr)\s*(?:is|of|was|be|at)?\s*(\d{2,3})\b', text_lower)
        if pulse_match:
            results["pulse"] = pulse_match.group(1)

        # Temperature
        temp_match = re.search(r'\b(?:temp|temperature)\s*(?:is|of|was|be|at)?\s*(\d{2,3}(?:\.\d)?)\s*(?:f|c|degrees)?\b', text_lower)
        if temp_match:
            results["temperature"] = temp_match.group(1)

        # SpO2
        spo2_match = re.search(r'\b(?:spo2|oxygen|saturation|o2\s+sat)\s*(?:is|of|was|be|at)?\s*(\d{2,3})\s*%?\b', text_lower)
        if spo2_match:
            results["spo2"] = spo2_match.group(1)

        # Weight
        weight_match = re.search(r'\b(?:weight|weighs?)\s*(?:is|of|was|be|at)?\s*(\d{2,3})\s*(?:kg|lbs|pounds)?\b', text_lower)
        if weight_match:
            results["weight"] = weight_match.group(1)

        # Height
        height_match = re.search(r'\b(?:height|tall)\s*(?:is|of|was|be|at)?\s*(\d(?:\'\d{1,2}\"?)?)\b', text_lower)
        if height_match:
            results["height"] = height_match.group(1)

        return results
