import json
import re
from app.services.clinical.pipeline import ClinicalProcessingPipeline

def main():
    pipeline = ClinicalProcessingPipeline()
    
    # Pre-defined test cases covering standard and advanced features
    test_cases = [
        "I have a severe headache and a mild cough.",
        "The patient absolutely does not currently have fever, but has a slight dizziness.",
        "Doctor asked: Do you have chest pain?",
        "Doctor said: You have diabetes.",
        "I have a head ache since yesterday and took paracetamol.",
        "Fever was not ruled out today."
    ]
    
    # The real-world dialogue pasted by the user
    dialogue = [
        ("doctor", "Good morning. What brings you in today?"),
        ("patient", "Good morning, doctor. I've been having a severe headache for about two weeks."),
        ("doctor", "Can you describe the headache for me?"),
        ("patient", "It's mostly on the right side of my head, and it feels like a throbbing pain."),
        ("doctor", "How severe would you rate it on a scale of one to ten?"),
        ("patient", "Around eight out of ten, especially in the evenings."),
        ("doctor", "Have you noticed any other symptoms?"),
        ("patient", "Yes, I've also been feeling dizzy occasionally."),
        ("doctor", "Do you have a fever?"),
        ("patient", "No, I don't have a fever."),
        ("doctor", "Any nausea or vomiting?"),
        ("patient", "I feel slightly nauseous sometimes, but I haven't vomited."),
        ("doctor", "Have you taken any medication for the headache?"),
        ("patient", "I've taken over-the-counter paracetamol a few times, but it hasn't helped much."),
        ("doctor", "Do you have a history of high blood pressure?"),
        ("patient", "Yes, I was diagnosed with high blood pressure three years ago."),
        ("doctor", "Are you currently taking medication for it?"),
        ("patient", "Yes, I'm taking amlodipine daily."),
        ("doctor", "Have you missed any doses recently?"),
        ("patient", "No, I've been taking it regularly."),
        ("doctor", "Alright. I'd like to check your blood pressure and order some blood tests."),
        ("patient", "Okay, doctor."),
        ("doctor", "Based on your symptoms, we need to rule out migraine and other neurological causes."),
        ("patient", "I understand."),
        ("doctor", "For now, continue your blood pressure medication and stay well hydrated."),
        ("patient", "Thank you, doctor."),
        ("doctor", "You're welcome. We'll review the test results at your follow-up appointment.")
    ]
    
    print("=== CLINICAL EXTRACTION LAYER (STEP 4) VERIFICATION ===\n")
    
    print("=" * 80)
    print("PART 1: RUNNING USER-SUBMITTED DOCTOR-PATIENT CONSULTATION DIALOGUE")
    print("=" * 80 + "\n")
    
    all_extracted_facts = {
        "symptoms": [],
        "medications": [],
        "diagnoses": [],
        "procedures": [],
        "risk_factors": [],
        "family_histories": []
    }
    
    for i, (speaker, text) in enumerate(dialogue, 1):
        # Process the dialogue turn through the clinical processing pipeline
        data = {
            "session_id": "consultation-session-001",
            "speaker_id": speaker,
            "transcript": text,
            "timestamp": 10.0 + i
        }
        
        result = pipeline.process(data)
        result_json = result.model_dump()
        
        # Structure the turn results
        turn_findings = {
            "symptoms": result_json["symptoms"],
            "medications": result_json["medications"],
            "diagnoses": result_json["diagnoses"],
            "procedures": result_json["procedures"],
            "risk_factors": result_json["risk_factors"],
            "family_histories": result_json["family_histories"]
        }
        
        # Filter to keep only active findings
        active_turn_findings = {k: v for k, v in turn_findings.items() if v}
        
        # Display the turn and the extracted entities (only if entities were found)
        speaker_label = f"[{speaker.upper()}]"
        print(f"{speaker_label:<10} {text}")
        if active_turn_findings:
            print("           >>> EXTRACTED CLINICAL FINDING(S):")
            print(json.dumps(active_turn_findings, indent=14).replace("{\n", "").replace("}", ""))
            
            # Aggregate for the final summary
            for key in all_extracted_facts:
                all_extracted_facts[key].extend(active_turn_findings.get(key, []))
        
    print("\n" + "=" * 80)
    print("FINAL SUMMARY OF CLINICAL FINDINGS AGGREGATED FROM THE CONSULTATION")
    print("=" * 80)
    
    # Deduplicate aggregated findings across the entire session
    def clean_agg(entities):
        seen = {}
        for ent in entities:
            key = ent["name"].lower() if "name" in ent else f"{ent['relationship'].lower()}:{ent['condition'].lower()}"
            if key not in seen:
                seen[key] = ent
            else:
                # Merge fields if one has more detail
                if ent.get("severity") and not seen[key].get("severity"):
                    seen[key]["severity"] = ent["severity"]
                if ent.get("duration") and not seen[key].get("duration"):
                    seen[key]["duration"] = ent["duration"]
                seen[key]["present"] = seen[key]["present"] or ent["present"]
        return list(seen.values())
        
    summary_findings = {
        "symptoms": clean_agg(all_extracted_facts["symptoms"]),
        "medications": clean_agg(all_extracted_facts["medications"]),
        "diagnoses": clean_agg(all_extracted_facts["diagnoses"]),
        "procedures": clean_agg(all_extracted_facts["procedures"]),
        "risk_factors": clean_agg(all_extracted_facts["risk_factors"]),
        "family_histories": clean_agg(all_extracted_facts["family_histories"])
    }
    
    print(json.dumps({k: v for k, v in summary_findings.items() if v}, indent=2))
    print("\n" + "=" * 80 + "\n")

    # Pre-defined test cases
    print("=" * 80)
    print("PART 2: RUNNING CORE RULE-BASED AND NEGATION BATCH TEST CASES")
    print("=" * 80 + "\n")
    
    for i, text in enumerate(test_cases, 1):
        print(f"Test Case {i}: \"{text}\"")
        speaker = "patient"
        clean_text = text
        if text.startswith("Doctor asked:"):
            speaker = "doctor"
            clean_text = text[13:].strip()
        elif text.startswith("Doctor said:"):
            speaker = "doctor"
            clean_text = text[12:].strip()
            
        data = {
            "session_id": "test-session",
            "speaker_id": speaker,
            "transcript": clean_text,
            "timestamp": 100.0 + i
        }
        
        result = pipeline.process(data)
        result_json = result.model_dump()
        
        clean_result = {
            "speaker_id": result_json["speaker_id"],
            "symptoms": result_json["symptoms"],
            "medications": result_json["medications"],
            "diagnoses": result_json["diagnoses"],
            "procedures": result_json["procedures"],
            "risk_factors": result_json["risk_factors"],
            "family_histories": result_json["family_histories"]
        }
        
        active_findings = {k: v for k, v in clean_result.items() if v or k == "speaker_id"}
        print(json.dumps(active_findings, indent=2))
        print("-" * 60 + "\n")

    # Interactive Tester
    print("=" * 80)
    print("PART 3: INTERACTIVE CLINICAL TEXT TESTER")
    print("=" * 80 + "\n")
    print("Type any sentence and press Enter to see extracted clinical entities.")
    print("You can prefix lines with '[DOCTOR]', '[PATIENT]', 'doctor:', or 'patient:' to change speaker context.")
    print("Or type '[DOCTOR]' or '[PATIENT]' on a line by itself to switch the default speaker context.")
    print("Type 'exit' or 'quit' to end the session.\n")
    
    default_speaker = "patient"
    
    while True:
        try:
            user_input = input(f"Enter clinical text ({default_speaker.upper()}): ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("\nVerification complete.")
                break
            
            # 1. Check if the user entered a speaker context switch tag on a line by itself
            tag_only_match = re.match(r'^(?:\[(doctor|patient)\]|\b(doctor|patient)\b)$', user_input, re.IGNORECASE)
            if tag_only_match:
                matched_role = (tag_only_match.group(1) or tag_only_match.group(2)).lower()
                default_speaker = matched_role
                print(f"--> Default speaker context switched to: {default_speaker.upper()}\n")
                continue
                
            # 2. Parse inline speaker tags (e.g., "[DOCTOR] Do you have a fever?" or "doctor: fever")
            inline_match = re.match(r'^(?:\[(doctor|patient)\]|(doctor|patient)\s*:)\s*(.*)$', user_input, re.IGNORECASE)
            
            speaker = default_speaker
            clean_input = user_input
            
            if inline_match:
                matched_role = (inline_match.group(1) or inline_match.group(2)).lower()
                speaker = matched_role
                clean_input = inline_match.group(3).strip()
                
            data = {
                "session_id": "interactive-session",
                "speaker_id": speaker,
                "transcript": clean_input,
                "timestamp": 0.0
            }
            
            result = pipeline.process(data)
            result_json = result.model_dump()
            
            clean_result = {
                "speaker_id": result_json["speaker_id"],
                "symptoms": result_json["symptoms"],
                "medications": result_json["medications"],
                "diagnoses": result_json["diagnoses"],
                "procedures": result_json["procedures"],
                "risk_factors": result_json["risk_factors"],
                "family_histories": result_json["family_histories"]
            }
            
            print("\n[Extracted Findings]")
            active_keys = {k: v for k, v in clean_result.items() if v or k == "speaker_id"}
            print(json.dumps(active_keys, indent=2))
            print("-" * 40 + "\n")
            
        except KeyboardInterrupt:
            print("\nVerification complete.")
            break
        except Exception as e:
            print(f"Error during extraction: {e}\n")

if __name__ == "__main__":
    main()
