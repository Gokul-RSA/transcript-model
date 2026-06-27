from typing import List, Optional, Dict
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

class PatientInfo(BaseModel):
    patient_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None

class VitalSigns(BaseModel):
    bp: Optional[str] = None
    pulse: Optional[str] = None
    temperature: Optional[str] = None
    spo2: Optional[str] = None
    weight: Optional[str] = None
    height: Optional[str] = None

class TreatmentPlan(BaseModel):
    medicines: List[Dict[str, Optional[str]]] = Field(default_factory=list)
    investigations: List[str] = Field(default_factory=list)
    advice: List[str] = Field(default_factory=list)

class ClinicalState(BaseModel):
    session_id: str
    patient_info: PatientInfo = Field(default_factory=PatientInfo)
    chief_complaint: List[str] = Field(default_factory=list)
    symptoms: List[Dict[str, Optional[str]]] = Field(default_factory=list)
    duration: Optional[str] = None
    severity: Optional[str] = None
    medical_history: List[str] = Field(default_factory=list)
    current_medications: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    vital_signs: VitalSigns = Field(default_factory=VitalSigns)
    diagnosis_tentative: List[str] = Field(default_factory=list)
    treatment_plan: TreatmentPlan = Field(default_factory=TreatmentPlan)
    follow_up: List[str] = Field(default_factory=list)
    version: int = 1
