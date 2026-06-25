from typing import Optional, List
from app.services.conversation.filler_remover import FillerRemover
from app.services.conversation.utterance_merger import UtteranceMerger
from app.services.conversation.terminology_normalizer import ClinicalTerminologyNormalizer

class ConversationProcessor:
    def __init__(self, max_completed_utterances: int = 1000):
        self.filler_remover = FillerRemover()
        self.merger = UtteranceMerger(max_completed_utterances=max_completed_utterances)
        self.normalizer = ClinicalTerminologyNormalizer()

    def _finalize(self, block: dict) -> dict:
        """
        Processes a completed block to apply clinical terminology normalization.
        Extracts raw_text, cleaned_text, and normalized_text explicitly, while preserving
        original keys for backward compatibility.
        Does not mutate the input dictionary.
        """
        raw = block.get("raw_text", "")
        cleaned = block.get("transcript", "")
        normalized = self.normalizer.normalize(cleaned)

        return {
            **block,
            "raw_text": raw,
            "cleaned_text": cleaned,
            "normalized_text": normalized,
            # Keep transcript field normalized for backward compatibility
            "transcript": normalized,
        }

    def process(
        self,
        session_id: str,
        speaker_id: str,
        transcript: str,
        is_final: bool,
        timestamp: float
    ) -> Optional[dict]:
        """
        Processes a transcript event through the pipeline:
        1. Clean fillers using FillerRemover.
        2. Attempt merging via UtteranceMerger.
        3. If a block is completed, normalize its clinical terminology and return it.
        """
        # 1. Clean fillers
        clean_text = self.filler_remover.clean(transcript)

        # 2. Add/merge utterance
        merged_block = self.merger.add(
            session_id=session_id,
            speaker_id=speaker_id,
            transcript=clean_text,
            is_final=is_final,
            timestamp=timestamp,
            raw_transcript=transcript
        )

        # 3. If a merged block was popped/completed, normalize its clinical terms
        if merged_block:
            return self._finalize(merged_block)

        return None

    def flush(self, session_id: str) -> Optional[dict]:
        """
        Force-finalizes and normalizes the last active utterance of the session.
        """
        flushed_block = self.merger.flush(session_id)
        if flushed_block:
            return self._finalize(flushed_block)
        return None

    def pop_completed(self, session_id: Optional[str] = None) -> List[dict]:
        """
        Retrieves and clears all completed utterances.
        """
        return self.merger.pop_completed(session_id)

    def clear_session(self, session_id: str) -> None:
        """
        Wipes all in-memory buffers associated with session_id to prevent memory growth.
        """
        self.merger.clear_session(session_id)
