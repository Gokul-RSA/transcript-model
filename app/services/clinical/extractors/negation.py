import re
from app.services.clinical.dictionary.loader import dictionary_manager

class NegationDetector:
    def __init__(self):
        negations = dictionary_manager.get_negations()
        self.pre_negation_triggers = set(negations.get("pre_negation", []))
        self.post_negation_triggers = set(negations.get("post_negation", []))

    def expand_contractions(self, text: str) -> str:
        """
        Expands common English contractions in the text to assist in accurate word-level negation parsing.
        """
        if not text:
            return ""
        
        contractions = {
            r"\bdon't\b": "do not",
            r"\bdoesn't\b": "does not",
            r"\bdidn't\b": "did not",
            r"\bhaven't\b": "have not",
            r"\bhadn't\b": "had not",
            r"\bwasn't\b": "was not",
            r"\bweren't\b": "were not",
            r"\bisn't\b": "is not",
            r"\baren't\b": "are not",
            r"\bwon't\b": "will not",
            r"\bwouldn't\b": "would not",
            r"\bshouldn't\b": "should not",
            r"\bcouldn't\b": "could not",
            r"\bcan't\b": "cannot"
        }
        
        expanded = text
        for pattern, replacement in contractions.items():
            expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
        return expanded

    def is_negated(self, clause: str, entity_name: str, start_char: int, end_char: int) -> bool:
        """
        Determines if an entity mention in a clause is negated.
        Uses a sliding-window negation logic and handles double-negation edge cases.
        """
        clause_lower = clause.lower()
        
        # Check for double negations first (e.g., "not ruled out")
        # Double negation means the symptom IS present (negation is canceled)
        double_negations = ["not ruled out", "never ruled out", "cannot be ruled out", "not negative", "no history of no"]
        for dn in double_negations:
            if dn in clause_lower:
                return False

        # Get the prefix text in the clause before the entity
        prefix = clause[:start_char].strip()
        # Get the suffix text in the clause after the entity
        suffix = clause[end_char:].strip()
        
        # Tokenize prefix and suffix into words (ignoring punctuation)
        prefix_words = [w.lower() for w in re.findall(r'\b\w+\b', prefix)]
        suffix_words = [w.lower() for w in re.findall(r'\b\w+\b', suffix)]
        
        # Check the ENTIRE prefix for pre-negation triggers
        for w in prefix_words:
            if w in self.pre_negation_triggers:
                return True
                
        # Check suffix for post-negation triggers (within a tight 3-word window)
        suffix_window = suffix_words[:3]
        for w in suffix_window:
            if w in self.post_negation_triggers:
                return True
                
        return False
