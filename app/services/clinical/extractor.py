import re
from typing import List, Dict, Any, Optional
from app.services.clinical.models import (
    SymptomEntity,
    MedicationEntity,
    DiagnosisEntity,
    ProcedureEntity,
    RiskFactorEntity,
    FamilyHistoryEntity
)
from app.services.clinical.extractors import (
    SymptomExtractor,
    MedicationExtractor,
    DiagnosisExtractor,
    HistoryExtractor,
    InvestigationExtractor,
    SectionDetector,
    context_manager
)

class ClinicalEntityExtractor:
    def __init__(self):
        self.symptom_extractor = SymptomExtractor()
        self.medication_extractor = MedicationExtractor()
        self.diagnosis_extractor = DiagnosisExtractor()
        self.history_extractor = HistoryExtractor()
        self.investigation_extractor = InvestigationExtractor()
        self.section_detector = SectionDetector()

    def _is_question(self, text: str) -> bool:
        text_stripped = text.strip()
        if not text_stripped:
            return False
        if text_stripped.endswith("?"):
            return True
        
        question_starts = [
            r"^do\b", r"^does\b", r"^did\b", r"^have\b", r"^has\b", r"^had\b",
            r"^is\b", r"^are\b", r"^was\b", r"^were\b", r"^can\b", r"^could\b",
            r"^should\b", r"^would\b", r"^will\b", r"^what\b", r"^how\b", r"^why\b",
            r"^where\b", r"^when\b", r"^who\b", r"^any\b"
        ]
        clean_text = re.sub(r'^[^\w]+', '', text_stripped).lower()
        for pattern in question_starts:
            if re.match(pattern, clean_text):
                return True
                
        return False

    def extract(self, text: str, speaker_id: Optional[str] = None, session_id: Optional[str] = None, timestamp: float = 0.0) -> Dict[str, List[Any]]:
        results = {
            "symptoms": [],
            "medications": [],
            "diagnoses": [],
            "procedures": [],
            "risk_factors": [],
            "family_histories": []
        }
        
        if not text or not text.strip():
            return results

        # Clinician Question Ignoring: If speaker is doctor and it's a question, ignore entirely.
        if speaker_id == "doctor" and self._is_question(text):
            return results

        # Detect the current conversational section statefully
        session = session_id or "default-session"
        section = self.section_detector.detect_section(session, text, speaker_id or "patient")

        # 1. Run modular sub-extractors
        results["symptoms"] = self.symptom_extractor.extract_symptoms(text, speaker_id, session, section)
        results["medications"] = self.medication_extractor.extract_medications(text, speaker_id)
        results["diagnoses"] = self.diagnosis_extractor.extract_diagnoses(text, speaker_id)
        
        history_results = self.history_extractor.extract_history(text, speaker_id)
        results["risk_factors"] = history_results.get("risk_factors", [])
        results["family_histories"] = history_results.get("family_histories", [])
        
        results["procedures"] = self.investigation_extractor.extract_investigations(text, speaker_id)

        # 2. Consolidate and deduplicate findings
        consolidated = self._consolidate_entities(results)

        # 3. Context queue & pronoun resolution
        # Push positive/present findings to the context queue
        for sym in consolidated["symptoms"]:
            if sym.present:
                # Add unique identifier tracking (we will associate IDs in state engine)
                context_manager.add_entity(session, "symptom", sym.name, f"symptom_{sym.name.lower()}", timestamp, section)
        for diag in consolidated["diagnoses"]:
            if diag.present:
                context_manager.add_entity(session, "diagnosis", diag.name, f"diagnosis_{diag.name.lower()}", timestamp, section)
        for med in consolidated["medications"]:
            if med.present:
                context_manager.add_entity(session, "medication", med.name, f"medication_{med.name.lower()}", timestamp, section)

        return consolidated

    def _consolidate_entities(self, results: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        """
        Deduplicates and consolidates extracted entities.
        """
        consolidated = {
            "symptoms": [],
            "medications": [],
            "diagnoses": [],
            "procedures": [],
            "risk_factors": [],
            "family_histories": []
        }

        # Symptoms
        symptom_groups = {}
        for sym in results["symptoms"]:
            symptom_groups.setdefault(sym.name.lower(), []).append(sym)
        for name, group in symptom_groups.items():
            any_present = any(s.present for s in group)
            final_severity = next((s.severity for s in group if s.severity), None)
            final_duration = next((s.duration for s in group if s.duration), None)
            max_confidence = max(s.confidence for s in group)
            consolidated["symptoms"].append(SymptomEntity(
                name=group[0].name,
                severity=final_severity,
                duration=final_duration,
                present=any_present,
                confidence=max_confidence
            ))

        # Medications
        med_groups = {}
        for med in results["medications"]:
            med_groups.setdefault(med.name.lower(), []).append(med)
        for name, group in med_groups.items():
            any_present = any(m.present for m in group)
            max_confidence = max(m.confidence for m in group)
            # Pick first available details
            dosage = next((m.dosage for m in group if m.dosage), None)
            frequency = next((m.frequency for m in group if m.frequency), None)
            duration = next((m.duration for m in group if m.duration), None)
            route = next((m.route for m in group if m.route), None)
            instructions = next((m.instructions for m in group if m.instructions), None)
            prn = any(m.prn for m in group)
            
            consolidated["medications"].append(MedicationEntity(
                name=group[0].name,
                present=any_present,
                confidence=max_confidence,
                dosage=dosage,
                frequency=frequency,
                duration=duration,
                route=route,
                instructions=instructions,
                prn=prn
            ))

        # Diagnoses
        diag_groups = {}
        for diag in results["diagnoses"]:
            diag_groups.setdefault(diag.name.lower(), []).append(diag)
        for name, group in diag_groups.items():
            any_present = any(d.present for d in group)
            consolidated["diagnoses"].append(DiagnosisEntity(
                name=group[0].name,
                present=any_present,
                confidence=max(d.confidence for d in group)
            ))

        # Procedures
        proc_groups = {}
        for proc in results["procedures"]:
            proc_groups.setdefault(proc.name.lower(), []).append(proc)
        for name, group in proc_groups.items():
            any_present = any(p.present for p in group)
            consolidated["procedures"].append(ProcedureEntity(
                name=group[0].name,
                present=any_present,
                confidence=max(p.confidence for p in group)
            ))
            
        # Risk factors
        rf_groups = {}
        for rf in results["risk_factors"]:
            rf_groups.setdefault(rf.name.lower(), []).append(rf)
        for name, group in rf_groups.items():
            any_present = any(r.present for r in group)
            consolidated["risk_factors"].append(RiskFactorEntity(
                name=group[0].name,
                present=any_present,
                confidence=max(r.confidence for r in group)
            ))

        # Family history
        fh_groups = {}
        for fh in results["family_histories"]:
            key = f"{fh.relationship.lower()}:{fh.condition.lower()}"
            fh_groups.setdefault(key, []).append(fh)
        for key, group in fh_groups.items():
            any_present = any(f.present for f in group)
            consolidated["family_histories"].append(FamilyHistoryEntity(
                relationship=group[0].relationship,
                condition=group[0].condition,
                present=any_present,
                confidence=max(f.confidence for f in group)
            ))

        return consolidated
