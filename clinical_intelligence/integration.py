"""
Integration shim — bridges Milestone 1 ClinicalStateEngine with the
Rule-Based Clinical Reasoning Engine (Milestone 2, Module 1).

Usage::

    from clinical_intelligence.integration import get_reasoning_result

    # Inside a FastAPI route or background task:
    result = get_reasoning_result(session_id)
"""

from __future__ import annotations

import logging
from typing import Optional

from clinical_intelligence.rule_engine.engine import ClinicalReasoningEngine
from clinical_intelligence.rule_engine.models import ClinicalReasoningResult

logger = logging.getLogger(__name__)

# Module-level singleton engine (lazy initialised)
_engine: Optional[ClinicalReasoningEngine] = None


def _get_engine() -> ClinicalReasoningEngine:
    global _engine
    if _engine is None:
        _engine = ClinicalReasoningEngine()
    return _engine


def get_reasoning_result(session_id: str) -> Optional[ClinicalReasoningResult]:
    """
    Retrieve the current ClinicalState for a session from Milestone 1's
    ClinicalStateEngine and run it through the Rule-Based Reasoning Engine.

    Returns None if the session is not found or the state is empty.
    """
    try:
        from app.services.clinical.state_engine import clinical_state_engine

        state = clinical_state_engine.get_state(session_id)
        if not state:
            logger.warning("Integration: No state found for session=%s", session_id)
            return None

        engine = _get_engine()
        result = engine.reason(state)
        return result

    except ImportError:
        logger.error(
            "Integration: Could not import ClinicalStateEngine — "
            "ensure the transcript-model app package is on PYTHONPATH."
        )
        return None
    except Exception:
        logger.exception(
            "Integration: Unexpected error during reasoning for session=%s", session_id
        )
        return None


def reason_from_state(state: object) -> ClinicalReasoningResult:
    """
    Directly reason from a ClinicalState or dict without the app import.
    Useful for batch processing and API endpoints.
    """
    engine = _get_engine()
    return engine.reason(state)
