from typing import Dict, Any
from app.services.clinical.normalizer import ClinicalNormalizer
from app.services.clinical.extractor import ClinicalEntityExtractor
from app.services.clinical.models import ClinicalExtractionResult

class ClinicalProcessingPipeline:
    def __init__(self):
        self.normalizer = ClinicalNormalizer()
        self.extractor = ClinicalEntityExtractor()

    def process(self, data: Dict[str, Any]) -> ClinicalExtractionResult:
        """
        Orchestrates the clinical processing pipeline:
        1. Normalizes the colloquial layman terms in the transcript.
        2. Extracts clinical entities (symptoms, medications, diagnoses, procedures,
           risk factors, and family histories).
           Passes the speaker_id to the extractor to ignore clinician questions.
        3. Constructs and returns a structured ClinicalExtractionResult Pydantic model.
        """
        session_id = data.get("session_id", "")
        speaker_id = data.get("speaker_id", "")
        transcript = data.get("transcript", "")
        timestamp = data.get("timestamp", 0.0)

        # 1. Normalize
        normalized_transcript = self.normalizer.normalize(transcript)

        # 2. Extract (passing speaker_id, session_id, and timestamp)
        extraction_results = self.extractor.extract(
            normalized_transcript, 
            speaker_id=speaker_id,
            session_id=session_id,
            timestamp=timestamp
        )

        # 3. Construct and return result model
        return ClinicalExtractionResult(
            session_id=session_id,
            speaker_id=speaker_id,
            timestamp=timestamp,
            symptoms=extraction_results.get("symptoms", []),
            medications=extraction_results.get("medications", []),
            diagnoses=extraction_results.get("diagnoses", []),
            procedures=extraction_results.get("procedures", []),
            risk_factors=extraction_results.get("risk_factors", []),
            family_histories=extraction_results.get("family_histories", [])
        )
