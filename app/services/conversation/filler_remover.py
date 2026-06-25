import re

class FillerRemover:
    def __init__(self):
        # List of filler words and phrases to remove
        # Excludes "like" to prevent clinical context damage (e.g. "pain like burning")
        # Excludes "actually" to preserve descriptive intent (e.g. "I actually have a fever")
        # Includes common clinical dialogue signals "mm-hmm" and "uh-huh"
        self.fillers = [
            "uh", "um", "hmm", "ah", "er", "you know", "sort of", "kind of", "mm-hmm", "uh-huh"
        ]
        # Sort by length descending to match multi-word phrases first
        sorted_fillers = sorted(self.fillers, key=len, reverse=True)
        escaped_fillers = [re.escape(f) for f in sorted_fillers]
        # Custom lookaround boundaries to support hyphenated and multi-word terms safely
        self.pattern = re.compile(r'(?<![\w-])(' + '|'.join(escaped_fillers) + r')(?![\w-])', re.IGNORECASE)

    def clean(self, text: str) -> str:
        if not text:
            return ""

        # Remove the filler words/phrases
        cleaned = self.pattern.sub("", text)

        # Post-processing cleanup for leftover punctuation:
        # 1. Collapse spaces before sentence-ending punctuation (., ?, !)
        cleaned = re.sub(r'\s+([.?!])', r'\1', cleaned)
        # 2. Attach commas, semicolons, colons to the preceding word if they have a space before them
        cleaned = re.sub(r'\s+([,;:])', r'\1', cleaned)
        # 3. Clean up multiple consecutive punctuation markers
        cleaned = re.sub(r',+', ',', cleaned)
        cleaned = re.sub(r';+', ';', cleaned)
        cleaned = re.sub(r'\.+', '.', cleaned)
        # 4. Standardize spacing around punctuation
        cleaned = re.sub(r'\s*,\s*', ', ', cleaned)
        cleaned = re.sub(r'\s*;\s*', '; ', cleaned)
        # 5. Clean up leading/trailing spaces and invalid leading/trailing punctuation
        cleaned = re.sub(r'^[,\s;]+', '', cleaned)
        cleaned = re.sub(r'[,\s;]+$', '', cleaned)
        # 6. Collapse multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)

        return cleaned.strip()
