from typing import List, Optional
from pydantic import BaseModel, Field

class SymptomEntity(BaseModel):
    name: str
    severity: Optional[str] = None
    duration: Optional[str] = None
    present: bool = True
    confidence: float = 1.0

class MedicationEntity(BaseModel):
    name: str
    present: bool = True
    confidence: float = 1.0

class DiagnosisEntity(BaseModel):
    name: str
    present: bool = True
    confidence: float = 1.0

class ProcedureEntity(BaseModel):
    name: str
    present: bool = True
    confidence: float = 1.0

class RiskFactorEntity(BaseModel):
    name: str
    present: bool = True
    confidence: float = 1.0

class FamilyHistoryEntity(BaseModel):
    relationship: str
    condition: str
    present: bool = True
    confidence: float = 1.0

class ClinicalFact(BaseModel):
    entity_type: str
    value: str
    confidence: float = 1.0

class ClinicalExtractionResult(BaseModel):
    session_id: str
    speaker_id: str
    timestamp: float
    symptoms: List[SymptomEntity] = Field(default_factory=list)
    medications: List[MedicationEntity] = Field(default_factory=list)
    diagnoses: List[DiagnosisEntity] = Field(default_factory=list)
    procedures: List[ProcedureEntity] = Field(default_factory=list)
    risk_factors: List[RiskFactorEntity] = Field(default_factory=list)
    family_histories: List[FamilyHistoryEntity] = Field(default_factory=list)
