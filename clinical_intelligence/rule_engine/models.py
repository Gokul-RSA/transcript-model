"""
Pydantic output models for the Rule-Based Clinical Reasoning Engine.

All models are fully typed and validated with Pydantic v2.
The top-level output is `ClinicalReasoningResult`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────
# Reasoning trace
# ─────────────────────────────────────────────

class ReasoningStep(BaseModel):
    """One atomic step in the reasoning trace."""

    step_id: str = Field(description="Unique identifier for this reasoning step")
    component: str = Field(description="Engine component that produced this step")
    description: str = Field(description="Human-readable description of the reasoning")
    input_facts: List[str] = Field(
        default_factory=list,
        description="Clinical facts used as input to this step",
    )
    output: str = Field(description="Conclusion reached by this step")
    confidence_delta: float = Field(
        default=0.0,
        description="How much this step changed the candidate's confidence score",
    )


class ExplainabilityMetadata(BaseModel):
    """Full reasoning audit trail for the entire engine run."""

    reasoning_steps: List[ReasoningStep] = Field(default_factory=list)
    rules_evaluated: int = Field(default=0, description="Total rule evaluations performed")
    rules_matched: int = Field(default=0, description="Rules that contributed to output")
    reasoning_duration_ms: float = Field(
        default=0.0, description="Wall-clock time for the full reasoning pass (ms)"
    )
    rule_files_loaded: List[str] = Field(
        default_factory=list, description="YAML rule files active during this run"
    )


# ─────────────────────────────────────────────
# Candidate diagnoses
# ─────────────────────────────────────────────

class CandidateDiagnosis(BaseModel):
    """A single candidate diagnosis produced by the reasoning engine."""

    disease_id: str = Field(description="Unique identifier matching diseases.yaml")
    name: str = Field(description="Human-readable disease name")
    category: str = Field(description="Clinical category, e.g. cardiovascular")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Normalised confidence score [0, 1]"
    )
    rank: int = Field(description="Rank by confidence (1 = highest)")
    supporting_symptoms: List[str] = Field(
        default_factory=list, description="Present symptoms that support this diagnosis"
    )
    missing_symptoms: List[str] = Field(
        default_factory=list,
        description="Cardinal symptoms that are absent or unasked",
    )
    negated_symptoms: List[str] = Field(
        default_factory=list, description="Explicitly negated symptoms"
    )
    matched_rules: List[str] = Field(
        default_factory=list, description="Rule IDs that fired for this diagnosis"
    )
    risk_factors: List[str] = Field(
        default_factory=list, description="Active risk factors that raised confidence"
    )
    supporting_evidence: List[str] = Field(
        default_factory=list,
        description="Free-text evidence items (vitals, history, demographics)",
    )
    reasoning_trace: List[ReasoningStep] = Field(
        default_factory=list, description="Step-by-step reasoning for this candidate"
    )


# ─────────────────────────────────────────────
# Red flags
# ─────────────────────────────────────────────

class RedFlagAlert(BaseModel):
    """A life-threatening clinical scenario detected by the engine."""

    flag_id: str
    condition: str
    severity: Literal["CRITICAL", "HIGH", "MODERATE"]
    supporting_evidence: List[str] = Field(default_factory=list)
    recommended_action: str
    triggered_by: List[str] = Field(
        default_factory=list,
        description="Symptoms / vitals / history items that triggered this flag",
    )


# ─────────────────────────────────────────────
# Risk factors
# ─────────────────────────────────────────────

class IdentifiedRiskFactor(BaseModel):
    """A clinical risk factor identified in the patient's state."""

    factor_id: str
    name: str
    category: str
    present: bool
    source: str = Field(description="Where this was found, e.g. medical_history, vitals")
    confidence_modifier: float = Field(
        description="How much this factor adjusts disease confidence scores"
    )


# ─────────────────────────────────────────────
# Investigations
# ─────────────────────────────────────────────

class InvestigationRecommendation(BaseModel):
    """A recommended investigation with priority and rationale."""

    investigation_id: str
    name: str
    priority: Literal["URGENT", "HIGH", "ROUTINE"]
    reason: str
    for_conditions: List[str] = Field(
        default_factory=list,
        description="Disease names that this investigation targets",
    )
    escalated_by_red_flag: bool = Field(
        default=False,
        description="True if priority was elevated because a red flag is active",
    )


# ─────────────────────────────────────────────
# Missing information
# ─────────────────────────────────────────────

class MissingInfoItem(BaseModel):
    """A clinically important piece of information not yet collected."""

    field: str = Field(description="Logical field name, e.g. 'pain_radiation'")
    question: str = Field(description="Suggested follow-up question for the clinician")
    priority: int = Field(
        ge=1, le=5,
        description="Priority 1 (most urgent) to 5 (nice to have)",
    )
    relevant_conditions: List[str] = Field(
        default_factory=list,
        description="Conditions for which this info would change confidence",
    )


# ─────────────────────────────────────────────
# Contraindications
# ─────────────────────────────────────────────

class Contraindication(BaseModel):
    """A detected contraindication."""

    contraindication_id: str
    drug_or_procedure: str = Field(
        description="The treatment or investigation that is contraindicated"
    )
    reason: str = Field(description="Why it is contraindicated")
    trigger: str = Field(
        description="The allergy, history item, or medication that triggers this"
    )
    severity: Literal["ABSOLUTE", "RELATIVE"]
    recommendation: str


# ─────────────────────────────────────────────
# Drug interactions
# ─────────────────────────────────────────────

class DrugInteraction(BaseModel):
    """A clinically significant drug–drug interaction."""

    interaction_id: str
    drug_a: str
    drug_b: str
    severity: Literal["MAJOR", "MODERATE", "MINOR"]
    mechanism: str
    clinical_effect: str
    recommendation: str


# ─────────────────────────────────────────────
# Clinical alerts
# ─────────────────────────────────────────────

class ClinicalAlert(BaseModel):
    """A general-purpose clinical alert generated by the engine."""

    alert_id: str
    alert_type: str = Field(
        description="Category: red_flag | contraindication | interaction | missing_info | risk_factor"
    )
    severity: Literal["CRITICAL", "HIGH", "MODERATE", "LOW", "INFO"]
    title: str
    message: str
    supporting_evidence: List[str] = Field(default_factory=list)
    recommended_action: Optional[str] = None


# ─────────────────────────────────────────────
# Top-level result
# ─────────────────────────────────────────────

class ClinicalReasoningResult(BaseModel):
    """
    The complete output of a single clinical reasoning pass.

    This is the sole public output type of ClinicalReasoningEngine.reason().
    Every field is fully explainable and deterministically derived from
    rule evaluations — no LLM is involved.
    """

    session_id: str
    reasoning_timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Diagnoses ranked by confidence
    candidate_diagnoses: List[CandidateDiagnosis] = Field(default_factory=list)

    # Life-threatening alerts (highest priority)
    red_flags: List[RedFlagAlert] = Field(default_factory=list)

    # Risk factor analysis
    risk_factors: List[IdentifiedRiskFactor] = Field(default_factory=list)

    # Recommended investigations
    recommended_investigations: List[InvestigationRecommendation] = Field(
        default_factory=list
    )

    # Missing clinical information + follow-up questions
    missing_information: List[MissingInfoItem] = Field(default_factory=list)

    # Safety checks
    contraindications: List[Contraindication] = Field(default_factory=list)
    drug_interactions: List[DrugInteraction] = Field(default_factory=list)

    # Actionable alerts (aggregated)
    clinical_alerts: List[ClinicalAlert] = Field(default_factory=list)

    # Full reasoning audit trail
    explainability: ExplainabilityMetadata = Field(
        default_factory=ExplainabilityMetadata
    )

    # Engine metadata
    engine_version: str = Field(default="1.0.0")
    rule_set_version: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict()
