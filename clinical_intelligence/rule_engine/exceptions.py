"""
Custom exception hierarchy for the Clinical Reasoning Engine.

All engine exceptions inherit from ClinicalReasoningError, making it
trivial to catch at the application boundary without masking unrelated
runtime errors.
"""

from __future__ import annotations


class ClinicalReasoningError(Exception):
    """Base exception for all clinical reasoning errors."""


class RuleLoadError(ClinicalReasoningError):
    """Raised when a YAML rule file cannot be parsed or is structurally invalid."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to load rule file '{path}': {reason}")


class RuleValidationError(ClinicalReasoningError):
    """Raised when a loaded rule fails schema validation."""

    def __init__(self, rule_id: str, field: str, reason: str) -> None:
        self.rule_id = rule_id
        self.field = field
        self.reason = reason
        super().__init__(
            f"Rule '{rule_id}' is invalid — field '{field}': {reason}"
        )


class InvalidClinicalStateError(ClinicalReasoningError):
    """Raised when the supplied ClinicalState cannot be reasoned over."""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"Invalid clinical state — '{field}': {reason}")


class ScoringError(ClinicalReasoningError):
    """Raised when a scoring computation encounters an irrecoverable error."""


class EngineNotInitializedError(ClinicalReasoningError):
    """Raised when the engine is used before its rules have been loaded."""
