import re
import json
from typing import Dict, Optional, Any, List
from threading import RLock
from app.services.clinical.pipeline import ClinicalProcessingPipeline
from app.services.clinical.models import ClinicalState, PatientInfo, VitalSigns, TreatmentPlan
from app.services.providers.models import TranscriptEvent
from app.services.transcript_bus import transcript_bus
from app.utils.logging import logger
from app.services.clinical.extractors import NameExtractor, VitalsExtractor, context_manager

class ClinicalStateEngine:
    def __init__(self):
        self._states: Dict[str, ClinicalState] = {}
        self._provenance: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()
        self.pipeline = ClinicalProcessingPipeline()
        self.name_extractor = NameExtractor()
        self.vitals_extractor = VitalsExtractor()
        
        # Subscribe to transcript bus events
        transcript_bus.subscribe(self.on_transcript_event)
        logger.info("ClinicalStateEngine: Subscribed to TranscriptEventBus.")

    def get_state(self, session_id: str) -> ClinicalState:
        """Thread-safely gets the current clinical state for a session, creating a new one if it doesn't exist."""
        with self._lock:
            if session_id not in self._states:
                self._states[session_id] = ClinicalState(session_id=session_id)
            return self._states[session_id]

    def clear_state(self, session_id: str) -> None:
        """Thread-safely clears the clinical state cache for a completed session."""
        with self._lock:
            self._states.pop(session_id, None)
            self._provenance.pop(session_id, None)
            self._metadata.pop(session_id, None)
            context_manager.clear_session(session_id)
            logger.info("ClinicalStateEngine: Cleared state", extra={"session_id": session_id})

    def get_provenance(self, session_id: str) -> Dict[str, Any]:
        """Gets internal provenance cache for a session."""
        with self._lock:
            return self._provenance.get(session_id, {})

    async def on_transcript_event(self, event: TranscriptEvent) -> None:
        """
        Subscribed callback invoked when a new TranscriptEvent is published.
        Only processes final (committed) events to update the session state incrementally.
        """
        if not event.is_final:
            return

        try:
            self.update_state_from_event(event)
        except Exception as e:
            logger.error(
                "ClinicalStateEngine: Error updating state from event",
                exc_info=True,
                extra={"session_id": event.session_id, "error": str(e)}
            )

    def _record_provenance(self, session_id: str, fact_key: str, event: TranscriptEvent, version: int) -> None:
        if session_id not in self._provenance:
            self._provenance[session_id] = {}
        self._provenance[session_id][fact_key] = {
            "event_id": event.event_id,
            "session_id": session_id,
            "sequence_number": event.sequence_number,
            "timestamp": event.timestamp,
            "speaker_id": event.speaker_id or "UNKNOWN",
            "transcript": event.transcript or "",
            "version": version
        }

    def _assess_significant_changes(self, session_id: str, old_state: Dict[str, Any], new_state: Dict[str, Any], transcript: str) -> None:
        if session_id not in self._metadata:
            self._metadata[session_id] = {
                "pending_updates": 0,
                "last_version": 0,
                "significant_change_reasons": [],
                "complete": False
            }
        
        meta = self._metadata[session_id]
        meta["pending_updates"] += 1
        
        reasons = set(meta["significant_change_reasons"])
        
        # 1. New Diagnosis
        old_diags = set(old_state.get("diagnosis_tentative", [])).union(set(old_state.get("medical_history", [])))
        new_diags = set(new_state.get("diagnosis_tentative", [])).union(set(new_state.get("medical_history", [])))
        if new_diags - old_diags:
            reasons.add("New Diagnosis")
            
        # 2. New Medication
        old_meds = {m.get("name").lower() for m in old_state.get("treatment_plan", {}).get("medicines", [])}.union(
            {m.lower() for m in old_state.get("current_medications", [])}
        )
        new_meds = {m.get("name").lower() for m in new_state.get("treatment_plan", {}).get("medicines", [])}.union(
            {m.lower() for m in new_state.get("current_medications", [])}
        )
        if new_meds - old_meds:
            reasons.add("New Medication")
            
        # 3. Emergency Finding
        emergency_terms = {"chest pain", "shortness of breath", "breathing issue", "difficulty breathing"}
        active_symptoms = {s.get("name").lower() for s in new_state.get("symptoms", []) if s.get("status") == "Active"}
        if emergency_terms.intersection(active_symptoms):
            reasons.add("Emergency Finding")
            
        # 4. Significant Clinical Update
        old_sym_status = {s.get("name").lower(): s.get("status") for s in old_state.get("symptoms", [])}
        new_sym_status = {s.get("name").lower(): s.get("status") for s in new_state.get("symptoms", [])}
        for name, status in new_sym_status.items():
            if name in old_sym_status and old_sym_status[name] != status:
                reasons.add("Significant Clinical Update")
                
        # 5. Consultation Completed
        if len(new_state.get("follow_up", [])) > len(old_state.get("follow_up", [])):
            reasons.add("Consultation Completed")
            
        meta["significant_change_reasons"] = list(reasons)
        
        # Assess state completeness
        has_patient = new_state.get("patient_info", {}).get("age") is not None or new_state.get("patient_info", {}).get("gender") is not None
        has_cc = len(new_state.get("chief_complaint", [])) > 0
        has_findings = (
            len(new_state.get("symptoms", [])) > 0 or 
            len(new_state.get("diagnosis_tentative", [])) > 0 or 
            new_state.get("vital_signs", {}).get("bp") is not None
        )
        meta["complete"] = bool(has_patient and has_cc and has_findings)

    # Expose helper methods for LLM Triggering
    def has_significant_state_change(self, session_id: str) -> bool:
        with self._lock:
            meta = self._metadata.get(session_id)
            return bool(meta and len(meta.get("significant_change_reasons", [])) > 0)

    def clinical_state_complete(self, session_id: str) -> bool:
        with self._lock:
            meta = self._metadata.get(session_id)
            return bool(meta and meta.get("complete", False))

    def ready_for_llm(self, session_id: str) -> bool:
        with self._lock:
            meta = self._metadata.get(session_id)
            if not meta:
                return False
            return bool(
                len(meta.get("significant_change_reasons", [])) > 0 or 
                meta.get("complete", False) or 
                meta.get("pending_updates", 0) >= 3
            )

    def pending_updates_count(self, session_id: str) -> int:
        with self._lock:
            meta = self._metadata.get(session_id)
            return meta.get("pending_updates", 0) if meta else 0

    def significant_change_reason(self, session_id: str) -> Optional[str]:
        with self._lock:
            meta = self._metadata.get(session_id)
            if meta and meta.get("significant_change_reasons"):
                return ", ".join(meta["significant_change_reasons"])
            return None

    def update_state_from_event(self, event: TranscriptEvent) -> ClinicalState:
        """
        Thread-safely updates the incremental clinical state using rules/heuristics and the pipeline extractor.
        """
        with self._lock:
            state = self.get_state(event.session_id)
            speaker_id = event.speaker_id or "UNKNOWN"
            text = event.transcript or ""
            text_lower = text.lower()

            # Snapshot the old state representation to check for version changes later
            old_state_dump = state.model_dump()

            # Process the turn through the standard clinical pipeline
            pipeline_data = {
                "session_id": event.session_id,
                "speaker_id": speaker_id,
                "transcript": text,
                "timestamp": event.timestamp
            }
            result = self.pipeline.process(pipeline_data)

            # 1. Patient Info (Age, Gender, Name)
            age_match = re.search(r'\b(?:i am|i\'m|age|aged|she is|he is|is|he\'s|she\'s)\s*(\d{1,3})\b', text_lower)
            if not age_match:
                age_match = re.search(r'\b(\d{1,3})\s*(?:years?\s*old|yo)\b', text_lower)
            if age_match:
                state.patient_info.age = int(age_match.group(1))
                self._record_provenance(event.session_id, "patient_info.age", event, state.version)

            if re.search(r'\b(?:male|males|gentleman|man|boy)\b', text_lower):
                state.patient_info.gender = "Male"
                self._record_provenance(event.session_id, "patient_info.gender", event, state.version)
            elif re.search(r'\b(?:female|females|lady|woman|girl)\b', text_lower):
                state.patient_info.gender = "Female"
                self._record_provenance(event.session_id, "patient_info.gender", event, state.version)

            # Use NameExtractor
            extracted_name = self.name_extractor.extract_name(text, speaker_id=speaker_id)
            if extracted_name:
                state.patient_info.patient_name = extracted_name
                self._record_provenance(event.session_id, "patient_info.patient_name", event, state.version)

            # 2. Chief Complaint
            if re.search(r'\b(?:came in for|complaining of|brings you in|brought you in|reason for visit|chief complaint)\b', text_lower):
                for sym in result.symptoms:
                    if sym.present and sym.name not in state.chief_complaint:
                        state.chief_complaint.append(sym.name)
                        self._record_provenance(event.session_id, f"chief_complaint.{sym.name.lower()}", event, state.version)
            if not state.chief_complaint:
                for sym in result.symptoms:
                    if sym.present and sym.name not in state.chief_complaint:
                        state.chief_complaint.append(sym.name)
                        self._record_provenance(event.session_id, f"chief_complaint.{sym.name.lower()}", event, state.version)

            # 3. Symptoms (Unique List with status contradiction handling and confidence scores)
            for sym in result.symptoms:
                conf_str = "High"
                if sym.confidence < 0.5:
                    conf_str = "Low"
                elif sym.confidence < 0.9:
                    conf_str = "Medium"
                
                existing = None
                for s in state.symptoms:
                    if s["name"].lower() == sym.name.lower():
                        existing = s
                        break
                        
                if sym.present:
                    if existing:
                        if sym.severity:
                            existing["severity"] = sym.severity
                        if sym.duration:
                            existing["duration"] = sym.duration
                        existing["status"] = "Active"
                        existing["confidence"] = conf_str
                        existing["present"] = "True"
                        existing["updated_at"] = str(event.timestamp)
                    else:
                        existing_id = f"symptom_{len(state.symptoms) + 1}"
                        state.symptoms.append({
                            "entity_id": existing_id,
                            "name": sym.name,
                            "severity": sym.severity,
                            "duration": sym.duration,
                            "status": "Active",
                            "confidence": conf_str,
                            "present": "True",
                            "updated_at": str(event.timestamp)
                        })
                    self._record_provenance(event.session_id, f"symptoms.{sym.name.lower()}", event, state.version)
                else:
                    # Contradiction Handling: Negated / Resolved
                    is_resolved = any(cue in text_lower for cue in ["gone", "resolved", "no longer", "disappeared", "stopped", "no " + sym.name.lower() + " now", "cleared up", "cured"])
                    status_val = "Resolved" if is_resolved else "Negated"
                    
                    if existing:
                        existing["status"] = status_val
                        existing["present"] = "False"
                        existing["confidence"] = conf_str
                        existing["updated_at"] = str(event.timestamp)
                    else:
                        existing_id = f"symptom_{len(state.symptoms) + 1}"
                        state.symptoms.append({
                            "entity_id": existing_id,
                            "name": sym.name,
                            "severity": sym.severity,
                            "duration": sym.duration,
                            "status": status_val,
                            "confidence": conf_str,
                            "present": "False",
                            "updated_at": str(event.timestamp)
                        })
                    self._record_provenance(event.session_id, f"symptoms.{sym.name.lower()}", event, state.version)

            # Conversational Context Modifier Association
            if not result.symptoms and state.symptoms:
                # Find if there is duration / severity
                detected_durs = self.pipeline.extractor.symptom_extractor._detect_durations(text)
                detected_sevs = []
                for term in self.pipeline.extractor.symptom_extractor.severity_terms:
                    if re.search(r'\b' + re.escape(term) + r'\b', text_lower):
                        detected_sevs.append(term)
                        
                # Check pronoun resolution ("it", "they", "this", "that") in text
                pronoun_match = re.search(r'\b(it|they|this|that)\b', text_lower)
                
                # Query context manager for active target
                target = None
                if pronoun_match:
                    pronoun_resolved = context_manager.resolve_pronoun(event.session_id, pronoun_match.group(1), event.timestamp)
                    if pronoun_resolved and pronoun_resolved["entity_type"] == "symptom":
                        target = next((s for s in state.symptoms if s["name"].lower() == pronoun_resolved["name"].lower()), None)
                
                # Run ambiguity detection if target not resolved
                if not target and (detected_durs or detected_sevs):
                    target_candidate = context_manager.get_modifier_target(event.session_id, "symptom", event.timestamp)
                    if target_candidate == "Needs clarification":
                        # Ambiguity detected: update all active symptoms in state
                        active_syms = [s for s in state.symptoms if s["status"] == "Active"]
                        for s in active_syms:
                            if detected_durs:
                                s["duration"] = "Needs clarification"
                            if detected_sevs:
                                s["severity"] = "Needs clarification"
                    elif isinstance(target_candidate, dict):
                        target = next((s for s in state.symptoms if s["name"].lower() == target_candidate["name"].lower()), None)
                
                if target:
                    if detected_durs:
                        target["duration"] = detected_durs[0]["value"]
                    if detected_sevs:
                        target["severity"] = detected_sevs[0]
                    target["updated_at"] = str(event.timestamp)
                    self._record_provenance(event.session_id, f"symptoms.{target['name'].lower()}", event, state.version)

            # 4. Duration (Overall/Chief complaint duration)
            for sym in result.symptoms:
                if sym.present and sym.duration:
                    state.duration = sym.duration
                    self._record_provenance(event.session_id, "duration", event, state.version)
            if not state.duration:
                dur_match = re.search(r'\b(?:for|since)\s+((?:about\s+|around\s+|almost\s+)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an|several|a\s+few)\s+(?:day|week|month|year)s?)\b', text_lower)
                if not dur_match:
                    dur_match = re.search(r'\bsince\s+((?:last\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|yesterday|week|month|year|college|childhood))\b', text_lower)
                if dur_match:
                    clean_dur = dur_match.group(1).strip()
                    clean_dur = re.sub(r'^(?:about|around|almost)\s+', '', clean_dur, flags=re.IGNORECASE).strip()
                    state.duration = clean_dur
                    self._record_provenance(event.session_id, "duration", event, state.version)

            # 5. Severity (Overall/Chief complaint severity)
            for sym in result.symptoms:
                if sym.present and sym.severity:
                    state.severity = sym.severity.capitalize()
                    self._record_provenance(event.session_id, "severity", event, state.version)
            if not state.severity:
                for term in ["severe", "moderate", "mild"]:
                    if re.search(r'\b' + term + r'\b', text_lower):
                        state.severity = term.capitalize()
                        self._record_provenance(event.session_id, "severity", event, state.version)
                        break

            # Associate general duration/severity back to first symptom
            if state.symptoms:
                if state.duration and not state.symptoms[0].get("duration"):
                    state.symptoms[0]["duration"] = state.duration
                if state.severity and not state.symptoms[0].get("severity"):
                    state.symptoms[0]["severity"] = state.severity.lower()

            # 6. Medical History
            for diag in result.diagnoses:
                diag_name = diag.name.capitalize()
                if diag.present:
                    if diag_name not in state.medical_history:
                        state.medical_history.append(diag_name)
                        self._record_provenance(event.session_id, f"medical_history.{diag.name.lower()}", event, state.version)
                else:
                    if diag_name in state.medical_history:
                        state.medical_history.remove(diag_name)
                        self._record_provenance(event.session_id, f"medical_history.{diag.name.lower()}", event, state.version)

            # 7. Current Medications (reported by patient/attender)
            if speaker_id in ["patient", "attender"]:
                for med in result.medications:
                    med_name = med.name.capitalize()
                    if med.present:
                        if med_name not in state.current_medications:
                            state.current_medications.append(med_name)
                            self._record_provenance(event.session_id, f"current_medications.{med.name.lower()}", event, state.version)
                    else:
                        if med_name in state.current_medications:
                            state.current_medications.remove(med_name)
                            self._record_provenance(event.session_id, f"current_medications.{med.name.lower()}", event, state.version)

            # 8. Allergies
            allergy_match = re.search(r'\b(?:allergic to|allergy to|allergies to)\s+([a-z]+)\b', text_lower)
            if allergy_match:
                allergy = allergy_match.group(1).capitalize()
                if allergy not in ["none", "no", "nah"] and allergy not in state.allergies:
                    state.allergies.append(allergy)
                    self._record_provenance(event.session_id, f"allergies.{allergy.lower()}", event, state.version)
            
            # NKDA checking
            if "nkda" in text_lower or "no known allergies" in text_lower:
                if "NKDA" not in state.allergies:
                    state.allergies.append("NKDA")
                    self._record_provenance(event.session_id, "allergies.nkda", event, state.version)

            # 9. Vital Signs
            vitals = self.vitals_extractor.extract_vitals(text)
            for k, v in vitals.items():
                if v:
                    setattr(state.vital_signs, k, v)
                    self._record_provenance(event.session_id, f"vital_signs.{k}", event, state.version)

            # 10. Diagnosis (Tentative)
            tentative_match = re.findall(r'\b(?:rule out|r/o|could be|diagnose|neurological causes|migraine)\s+([a-zA-Z\s]+?)(?:\b|and|or|\.)', text_lower)
            for item in tentative_match:
                item_clean = item.strip().capitalize()
                if item_clean and item_clean not in state.diagnosis_tentative:
                    state.diagnosis_tentative.append(item_clean)
                    self._record_provenance(event.session_id, f"diagnosis_tentative.{item_clean.lower()}", event, state.version)
            
            if "migraine" in text_lower and "Migraine" not in state.diagnosis_tentative:
                state.diagnosis_tentative.append("Migraine")
                self._record_provenance(event.session_id, "diagnosis_tentative.migraine", event, state.version)
            if "neurological causes" in text_lower and "Neurological causes" not in state.diagnosis_tentative:
                state.diagnosis_tentative.append("Neurological causes")
                self._record_provenance(event.session_id, "diagnosis_tentative.neurological causes", event, state.version)

            # Contradiction for tentative diagnosis
            for diag in result.diagnoses:
                if not diag.present:
                    diag_name = diag.name.capitalize()
                    if diag_name in state.diagnosis_tentative:
                        state.diagnosis_tentative.remove(diag_name)
                        self._record_provenance(event.session_id, f"diagnosis_tentative.{diag.name.lower()}", event, state.version)

            # 11. Treatment Plan (Medicines, Investigations, Advice)
            if speaker_id == "doctor":
                for med in result.medications:
                    med_name = med.name.capitalize()
                    
                    if med.present:
                        existing = None
                        for m in state.treatment_plan.medicines:
                            if m["name"].lower() == med_name.lower():
                                existing = m
                                break
                        
                        prn_str = "True" if med.prn else "False"
                        
                        if existing:
                            if med.dosage: existing["dosage"] = med.dosage
                            if med.frequency: existing["frequency"] = med.frequency
                            if med.duration: existing["duration"] = med.duration
                            if med.route: existing["route"] = med.route
                            if med.instructions: existing["instructions"] = med.instructions
                            existing["prn"] = prn_str
                        else:
                            state.treatment_plan.medicines.append({
                                "name": med_name,
                                "dosage": med.dosage,
                                "frequency": med.frequency,
                                "duration": med.duration,
                                "route": med.route,
                                "instructions": med.instructions,
                                "prn": prn_str
                            })
                        self._record_provenance(event.session_id, f"treatment_plan.medicines.{med.name.lower()}", event, state.version)
                    else:
                        existing = None
                        for m in state.treatment_plan.medicines:
                            if m["name"].lower() == med_name.lower():
                                existing = m
                                break
                        if existing:
                            state.treatment_plan.medicines.remove(existing)
                            self._record_provenance(event.session_id, f"treatment_plan.medicines.{med.name.lower()}", event, state.version)

            # Investigations
            for p in result.procedures:
                if p.present:
                    proc_name = p.name.capitalize()
                    if proc_name not in state.treatment_plan.investigations:
                        state.treatment_plan.investigations.append(proc_name)
                        self._record_provenance(event.session_id, f"treatment_plan.investigations.{p.name.lower()}", event, state.version)
                else:
                    proc_name = p.name.capitalize()
                    if proc_name in state.treatment_plan.investigations:
                        state.treatment_plan.investigations.remove(proc_name)
                        self._record_provenance(event.session_id, f"treatment_plan.investigations.{p.name.lower()}", event, state.version)

            # Advice
            if "stay well hydrated" in text_lower or "stay hydrated" in text_lower:
                advice_str = "Stay well hydrated"
                if advice_str not in state.treatment_plan.advice:
                    state.treatment_plan.advice.append(advice_str)
                    self._record_provenance(event.session_id, "treatment_plan.advice.stay hydrated", event, state.version)
            if "continue your" in text_lower:
                match = re.search(r'\b(continue your [a-zA-Z\s]+?)(?:\b|and|or|\.)', text_lower)
                if match:
                    advice_str = match.group(1).capitalize()
                    if advice_str not in state.treatment_plan.advice:
                        state.treatment_plan.advice.append(advice_str)
                        self._record_provenance(event.session_id, "treatment_plan.advice.continue your", event, state.version)

            # 12. Follow-up
            followup_match = re.search(r'\b(?:come\s+back|review\s+after|visit\s+again|follow\s*up|appointment|see\s+you\s+again|return\s+to\s+clinic)\b', text_lower)
            if followup_match or "follow-up" in text_lower or "appointment" in text_lower:
                for sentence in re.split(r'(?<=[.!?])\s+', text):
                    sent_lower = sentence.lower()
                    if any(term in sent_lower for term in ["come back", "review after", "visit again", "follow up", "follow-up", "appointment", "see you again", "return to clinic"]):
                        clean_sentence = sentence.strip()
                        if clean_sentence and clean_sentence not in state.follow_up:
                            state.follow_up.append(clean_sentence)
                            self._record_provenance(event.session_id, f"follow_up.{len(state.follow_up)-1}", event, state.version)

            # Update context manager turns
            current_section = self.pipeline.extractor.section_detector.detect_section(event.session_id, text, speaker_id)
            context_manager.update_turns(event.session_id, current_section)

            # Versioning and Significant Change triggers check
            new_state_dump = state.model_dump()
            old_compare = {k: v for k, v in old_state_dump.items() if k != "version"}
            new_compare = {k: v for k, v in new_state_dump.items() if k != "version"}
            if old_compare != new_compare:
                state.version += 1
                self._assess_significant_changes(event.session_id, old_compare, new_compare, text)

            # Push WS updates if active
            try:
                from app.services.session import session_manager
                session = session_manager.get_session(event.session_id)
                if session:
                    for stream in list(session.streams.values()):
                        try:
                            import asyncio
                            asyncio.create_task(stream.websocket.send_json({
                                "type": "clinical_state",
                                "data": state.model_dump()
                            }))
                        except Exception:
                            pass
            except Exception:
                pass

            return state

clinical_state_engine = ClinicalStateEngine()
