"""
Clinical Intelligence Engine — Module 1: Rule-Based Clinical Reasoning Engine.

This package provides deterministic, explainable clinical reasoning from a
Structured Clinical State (Milestone 1 output) without using any LLM.
"""

from clinical_intelligence.rule_engine.engine import ClinicalReasoningEngine
from clinical_intelligence.rule_engine.models import ClinicalReasoningResult

__all__ = ["ClinicalReasoningEngine", "ClinicalReasoningResult"]
__version__ = "1.0.0"
