from pydantic import BaseModel
from typing import Optional

class TranscriptEvent(BaseModel):
    """
    Standardized event schema representing a real-time transcription block.
    """
    session_id: str
    role: str
    sequence_number: int
    timestamp: float
    transcript: str
    is_partial: bool
    is_final: bool
    confidence: Optional[float] = None
    provider: str = "scribe_v2"
