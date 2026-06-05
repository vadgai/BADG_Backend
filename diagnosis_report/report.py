import json
import logging
from dotenv import load_dotenv

from utils.gemini_api_manager import (
    generate_content_with_fallback,
    get_gemini_model,
    extract_json_from_text,
)

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Gemini model via centralized API manager (multi-key support)
model_available, _model = get_gemini_model()
if model_available and _model is not None:
    logger.info("✅ Gemini model available for report generation (via API manager)")
else:
    logger.warning(
        "⚠️ Gemini model not available for report generation; fallback reports will be used."
    )

def _fallback_report(age, gender, symptoms, chat_history, mapped_diseases):
    """
    Generate a basic report when AI is unavailable.
    """
    symptom_list = symptoms if isinstance(symptoms, list) else [str(symptoms)]
    
    report = {
        "PatientInfo": {
            "Age": f"{age} Years",
            "Gender": str(gender).title()
        },
        "ClinicalSummary": "AI system temporarily unavailable. Basic symptomatic report generated.",
        "RecommendedSpecialist": "General Practitioner / Primary Care Physician",
        "RecommendedTests": ["Clinical Evaluation", "Basic Vitals Check"],
        "Recommendation": "Please consult a healthcare professional for proper diagnosis and treatment.",
        "Urgency": "Routine",
        "ReasonForConsultation": f"Patient reports symptoms: {', '.join(symptom_list)}",
        "MainSymptoms": symptom_list[:6],  # Top 6 symptoms
        "TopDiseaseMatches": [
            {
                "Name": "Unable to determine - AI unavailable",
                "MatchLevel": "Unknown",
                "PreHospitalCare": ["Seek medical consultation", "Monitor symptoms"],
                "SymptomsToWatch": ["Worsening symptoms", "New symptoms"],
                "SelfCare": ["Rest", "Stay hydrated", "Monitor temperature"],
                "MedicationSuggestion": ["Consult doctor before taking medication"]
            }
        ]
    }

    if isinstance(mapped_diseases, dict):
        conditions = mapped_diseases.get("conditions") or []
        if conditions:
            top_matches = []
            tests = []
            for cond in conditions[:2]:
                if not isinstance(cond, dict):
                    continue
                name = str(cond.get("name", "")).strip()
                if not name:
                    continue
                top_matches.append(
                    {
                        "Name": name,
                        "MatchLevel": cond.get("probability") or "Moderate",
                        "PreHospitalCare": ["Stay hydrated", "Monitor symptoms closely"],
                        "SymptomsToWatch": ["Worsening symptoms", "Severe pain or breathing difficulty"],
                        "SelfCare": ["Rest and avoid strenuous activity"],
                        "MedicationSuggestion": ["Consult a doctor before taking medication"],
                    }
                )
                for test in cond.get("recommended_tests") or []:
                    test_name = str(test).strip()
                    if test_name and test_name not in tests:
                        tests.append(test_name)
            if top_matches:
                report["TopDiseaseMatches"] = top_matches
            if tests:
                report["RecommendedTests"] = tests[:6]

    report["NextDiagnosticSteps"] = build_next_diagnostic_steps(report, mapped_diseases)

    # IMPORTANT: return the report object directly (not JSON string),
    # so that it matches the shape of normal AI-generated reports.
    return report

_GENERIC_DIAGNOSTIC_STEP_MARKERS = (
    "additional tests may be suggested based on your top predicted conditions",
    "your doctor may recommend a few diagnostic tests to understand your condition better",
    "a complete blood count (cbc) can help detect infection or inflammation",
)


def _extract_disease_name_from_match(entry) -> str:
    if not isinstance(entry, dict):
        return ""
    name = entry.get("Name") or entry.get("name") or entry.get("Disease") or entry.get("disease")
    if name:
        return str(name).strip()
    key = next((k for k in entry if str(k).startswith("Disease")), None)
    if not key:
        return ""
    payload = entry.get(key)
    if not isinstance(payload, dict):
        return ""
    num = "".join(ch for ch in str(key) if ch.isdigit())
    return str(
        payload.get(f"Name{num}")
        or payload.get("Name")
        or payload.get("name")
        or ""
    ).strip()


def _is_generic_diagnostic_steps(steps) -> bool:
    if not isinstance(steps, list) or not steps:
        return True
    text = " ".join(str(s).strip().lower() for s in steps if str(s).strip())
    return any(marker in text for marker in _GENERIC_DIAGNOSTIC_STEP_MARKERS)


def build_next_diagnostic_steps(report_obj, mapping_data=None) -> list:
    """
    Build disease-specific next diagnostic steps from top matches and recommended tests.
    Replaces generic placeholder bullets when the LLM omits NextDiagnosticSteps.
    """
    if not isinstance(report_obj, dict):
        report_obj = {}

    existing = report_obj.get("NextDiagnosticSteps")
    if isinstance(existing, list) and existing and not _is_generic_diagnostic_steps(existing):
        return [str(s).strip() for s in existing if str(s).strip()][:6]

    diseases = []
    matches = report_obj.get("TopDiseaseMatches")
    if isinstance(matches, list):
        for entry in matches[:2]:
            name = _extract_disease_name_from_match(entry)
            if name and name.lower() not in {d.lower() for d in diseases}:
                diseases.append(name)

    if not diseases and isinstance(mapping_data, dict):
        for cond in (mapping_data.get("conditions") or [])[:2]:
            if isinstance(cond, dict):
                name = str(cond.get("name", "")).strip()
                if name and name.lower() not in {d.lower() for d in diseases}:
                    diseases.append(name)

    tests = report_obj.get("RecommendedTests")
    if not isinstance(tests, list):
        tests = []
    tests = [str(t).strip() for t in tests if str(t).strip()]

    specialist = str(report_obj.get("RecommendedSpecialist") or "").strip()
    urgency = str(report_obj.get("Urgency") or "Routine").strip()

    steps = []
    if diseases:
        if len(diseases) > 1:
            steps.append(
                f"Evaluate for {diseases[0]} (top match) and differentiate from {diseases[1]} using targeted investigations."
            )
        else:
            steps.append(
                f"Confirm or rule out {diseases[0]} with condition-specific laboratory and clinical assessment."
            )

    if tests:
        for test in tests[:5]:
            if diseases:
                steps.append(f"{test} — indicated for suspected {diseases[0]}.")
            else:
                steps.append(f"{test} — recommended based on your symptom profile.")
    elif diseases:
        steps.append(
            f"Your clinician may order blood work, imaging, or cultures specific to {diseases[0]} and the differential diagnosis."
        )

    if specialist:
        steps.append(f"Consult with a {specialist} to interpret results and plan treatment.")

    if urgency.lower() == "emergency":
        steps.append("Seek urgent care if symptoms worsen before test results are available.")
    else:
        steps.append("Review all results with your doctor to finalize diagnosis and next treatment steps.")

    return steps[:6]


def _format_chat_history(history: list) -> str:
    """Format full Q&A pairs from chat_history for LLM context."""
    if not history:
        return "No previous questions asked."
    lines = []
    turn = 0
    i = 0
    while i < len(history):
        msg = history[i]
        if not isinstance(msg, dict):
            i += 1
            continue
        bot_q = str(msg.get("bot") or "").strip()
        user_a = str(msg.get("user") or "").strip()
        if bot_q:
            turn += 1
            lines.append(f"Q{turn}: {bot_q}")
            if user_a:
                lines.append(f"A{turn}: {user_a}")
            elif i + 1 < len(history) and isinstance(history[i + 1], dict):
                next_user = str(history[i + 1].get("user") or "").strip()
                if next_user:
                    lines.append(f"A{turn}: {next_user}")
                    i += 1
        elif user_a and lines:
            lines.append(f"(Answer): {user_a}")
        i += 1
    return "\n".join(lines) if lines else "No previous questions asked."



def generate_report_prompt(
    age,
    gender,
    symptoms,
    chat_history,
    mapped_diseases,
    negatives=None,
    symptom_state=None,
    running_summary=None,  # Fix G: pre-built clinical summary from diagnosis loop
):
    state = symptom_state if isinstance(symptom_state, dict) else {}
    state_symptoms = state.get("current_symptoms") if isinstance(state.get("current_symptoms"), list) else []
    modifier_map = state.get("modifier_map") if isinstance(state.get("modifier_map"), dict) else {}
    confirmed_symptoms = state_symptoms or (symptoms if isinstance(symptoms, list) else [str(symptoms)])
    confirmed_symptoms = [str(s).strip() for s in confirmed_symptoms if str(s).strip()]
    ruled_out = negatives if isinstance(negatives, list) else []
    ruled_out = [str(n).strip() for n in ruled_out if str(n).strip()]
    red_flags = state.get("red_flags") if isinstance(state.get("red_flags"), list) else []
    red_flags = [str(r).strip() for r in red_flags if str(r).strip()]
    deterministic_trace = []
    if isinstance(mapped_diseases, dict):
        conditions = mapped_diseases.get("conditions") if isinstance(mapped_diseases.get("conditions"), list) else []
        for cond in conditions[:3]:
            if not isinstance(cond, dict):
                continue
            score_details = cond.get("score_details") if isinstance(cond.get("score_details"), dict) else {}
            deterministic_trace.append(
                {
                    "name": cond.get("name"),
                    "probability": cond.get("probability"),
                    "score": cond.get("score"),
                    "matched_positive_features": score_details.get("matched_positive_features", []),
                    "contradicted_features": score_details.get("contradicted_features", []),
                    "exclude_hits": score_details.get("exclude_hits", []),
                }
            )

    symptoms_json = json.dumps(confirmed_symptoms, ensure_ascii=False)
    negatives_json = json.dumps(ruled_out, ensure_ascii=False)
    red_flags_json = json.dumps(red_flags, ensure_ascii=False)
    modifier_map_json = json.dumps(modifier_map, ensure_ascii=False)
    deterministic_trace_json = json.dumps(deterministic_trace, ensure_ascii=False, default=str)
    mapped_json = json.dumps(mapped_diseases, ensure_ascii=False, default=str)
    
    history_list = chat_history if isinstance(chat_history, list) else []
    chat_history_text = _format_chat_history(history_list)

    # Fix G: include running_summary as a ground-truth anchor when available
    running_summary_text = ""
    if running_summary and str(running_summary).strip():
        running_summary_text = f"\n- Pre-validated Clinical Summary (HIGH PRIORITY — use this as narrative foundation): {str(running_summary).strip()}"

    return f"""Medical reporter. Summarize findings into a clinical JSON report. JSON only.

INPUT:
- Age/Gender: {age}/{gender}
- Confirmed symptoms: {symptoms_json}
- Ruled out: {negatives_json}
- Red flags: {red_flags_json}
- Modifier map: {modifier_map_json}
- Deterministic score trace: {deterministic_trace_json}
- Mapped diseases: {mapped_json}{running_summary_text}

Q&A HISTORY:
{chat_history_text}

CONSTRAINTS:
1. NO HALLUCINATION: list only symptoms in "Confirmed symptoms" or stated positively in the Q&A.
2. CHRONICITY: judge from modifiers and Q&A.
3. URGENCY: set "Emergency" if any red flag is present.
4. TopDiseaseMatches MUST be a flat array of objects (no "Disease1"-style keys); keep it consistent with the deterministic trace/mapped diseases.
5. DEPTH: professional ClinicalSummary, RecommendedSpecialist, and RecommendedTests from the full presentation; no placeholders.
6. If a Pre-validated Clinical Summary is given, use it as the ClinicalSummary foundation and do not contradict it.
7. NextDiagnosticSteps: 3-5 bullets tied to the TOP predicted disease(s) in TopDiseaseMatches; name each test from RecommendedTests and explain why it helps confirm/rule out those specific conditions. No generic filler.

OUTPUT JSON ONLY:
{{
  "PatientInfo": {{"Age": "{age}", "Gender": "{gender}"}},
  "Urgency": "Emergency|Routine|Urgent",
  "ClinicalSummary": "A concise 2-3 sentence clinical narrative summarizing the patient's presentation and key findings from the chat history.",
  "RecommendedSpecialist": "e.g., Gastroenterologist, Neurologist, General Practitioner",
  "RecommendedTests": ["e.g., CBC", "e.g., Ultrasound"],
  "NextDiagnosticSteps": ["Specific step for top disease + named test", "Second step for differential"],
  "MainSymptoms": {symptoms_json},
  "TopDiseaseMatches": [
    {{
      "Name": "Appendicitis",
      "MatchLevel": "High|Moderate",
      "PreHospitalCare": ["Avoid heavy meals", "Seek urgent clinical review if pain worsens"],
      "SymptomsToWatch": ["Persistent vomiting", "Increasing right-lower abdominal pain"],
      "SelfCare": ["Hydrate with oral fluids", "Rest and monitor symptom progression"],
      "MedicationSuggestion": ["Use only clinician-approved pain relievers"]
    }}
  ]
}}
"""





def final_report(
    age,
    gender,
    symptoms,
    chat_history,
    mapped_diseases,
    weight=None,
    height=None,
    occupation=None,
    location=None,
    physical_activity=None,
    diet_type=None,
    negatives=None,
    symptom_state=None,
    running_summary=None,  # Fix G: pre-built clinical summary
):
    """
    Generate final diagnosis report using Gemini AI.
    Falls back to basic report if AI is unavailable or fails.
    """
    # If Gemini model is not available at all, return fallback report immediately
    model_ok, _ = get_gemini_model()
    if not model_ok:
        logger.error("Gemini model not available for report generation, using fallback")
        return _fallback_report(age, gender, symptoms, chat_history, mapped_diseases)

    try:
        prompt = generate_report_prompt(
            age,
            gender,
            symptoms,
            chat_history,
            mapped_diseases,
            negatives=negatives,
            symptom_state=symptom_state,
            running_summary=running_summary,  # Fix G: pass through
        )

        # Use centralized multi-key manager with full fallback across all configured keys
        success, raw_response, error = generate_content_with_fallback(
            prompt=prompt,
            max_retries=None,  # try all available keys (up to 15)
            temperature=0.3,
            max_output_tokens=2800,
        )

        if not success or not raw_response:
            logger.error("Gemini report generation failed: %s", error)
            return _fallback_report(age, gender, symptoms, chat_history, mapped_diseases)

        raw_response = raw_response.strip()

        # First, try robust JSON extraction provided by the API manager
        parsed_json = extract_json_from_text(raw_response)

        # If that fails, fall back to simple fence-stripping logic
        if not parsed_json:
            cleaned_res = raw_response
            if cleaned_res.startswith("```json"):
                cleaned_res = cleaned_res[len("```json") :].strip()
            if cleaned_res.endswith("```"):
                cleaned_res = cleaned_res[: -3].strip()

            if cleaned_res.startswith("{") and cleaned_res.endswith("}"):
                try:
                    parsed_json = json.loads(cleaned_res)
                except json.JSONDecodeError as exc:
                    logger.error(
                        "JSONDecodeError in report generation: %s", exc, exc_info=True
                    )
                    logger.warning(
                        "Falling back to basic report format due to JSON parse error"
                    )
                    return _fallback_report(
                        age, gender, symptoms, chat_history, mapped_diseases
                    )

        if not parsed_json or not isinstance(parsed_json, dict):
            # One reformat retry before fallback
            reformat_prompt = (
                "The previous response could not be parsed. PLEASE RETURN ONLY a single JSON object "
                "in the exact structure requested earlier (start with \"{\" and end with \"}\"). "
                "Do not include any explanatory text or markdown."
            )
            try:
                success_retry, retry_text, _ = generate_content_with_fallback(
                    prompt=f"{reformat_prompt}\n\n{raw_response}",
                    max_retries=None,
                    temperature=0.2,
                    max_output_tokens=2800,
                )
                if success_retry and retry_text:
                    retry_text = retry_text.strip()
                    parsed_json = extract_json_from_text(retry_text)
                    if not parsed_json:
                        try:
                            parsed_json = json.loads(retry_text)
                        except Exception:
                            parsed_json = None
            except Exception:
                parsed_json = None

        if not parsed_json or not isinstance(parsed_json, dict):
            logger.error(
                "Model returned unexpected or non-dict format; using fallback report. Raw preview: %s",
                raw_response[:500],
            )
            return _fallback_report(
                age, gender, symptoms, chat_history, mapped_diseases
            )

        # Enforce hard constraints from report prompt to avoid hallucinations.
        state = symptom_state if isinstance(symptom_state, dict) else {}
        state_symptoms = state.get("current_symptoms") if isinstance(state.get("current_symptoms"), list) else []
        confirmed_symptoms = state_symptoms or (symptoms if isinstance(symptoms, list) else [str(symptoms)])
        confirmed_symptoms = [str(s).strip() for s in confirmed_symptoms if str(s).strip()]
        symptom_tokens = [s.lower() for s in confirmed_symptoms]

        state_red_flags = state.get("red_flags") if isinstance(state.get("red_flags"), list) else []
        state_red_flags = [str(r).strip().lower() for r in state_red_flags if str(r).strip()]

        red_flag_keywords = [
            "chest pain",
            "severe chest pain",
            "difficulty breathing",
            "shortness of breath",
            "loss of consciousness",
            "fainting",
            "stroke",
            "seizure",
            "confusion",
            "severe headache",
            "severe abdominal pain",
            "bleeding",
        ]
        has_red_flag = bool(state_red_flags) or any(
            any(flag in token for flag in red_flag_keywords)
            for token in symptom_tokens
        )

        def _extract_match_name(match_entry):
            if not isinstance(match_entry, dict) or not match_entry:
                return ""
            
            # New clean JSON array format (e.g. {"Name": "Appendicitis", ...})
            if "Name" in match_entry or "name" in match_entry:
                return str(match_entry.get("Name") or match_entry.get("name") or "").strip()
            
            # Backwards compatibility with old {"Disease1": {"Name1": "Appendicitis"}} format
            key = next(iter(match_entry.keys()), None)
            if not key:
                return ""
            payload = match_entry.get(key)
            if not isinstance(payload, dict):
                return ""
            idx = "".join(ch for ch in str(key) if ch.isdigit())
            return str(
                payload.get(f"Name{idx}") or payload.get("Name") or payload.get("name") or ""
            ).strip()

        def _is_chronic_condition(name: str) -> bool:
            n = (name or "").lower()
            chronic_terms = [
                "ibd",
                "inflammatory bowel",
                "malignancy",
                "cancer",
                "tuberculosis",
                "tb",
            ]
            return any(term in n for term in chronic_terms)

        weight_loss_present = any(
            "weight loss" in token or "unintentional weight loss" in token
            for token in symptom_tokens
        )

        if weight_loss_present and isinstance(parsed_json.get("TopDiseaseMatches"), list):
            matches = parsed_json.get("TopDiseaseMatches", [])
            parsed_json["TopDiseaseMatches"] = sorted(
                matches,
                key=lambda entry: 0 if _is_chronic_condition(_extract_match_name(entry)) else 1,
            )

        # Constraint #1: Main symptoms must come ONLY from confirmed symptoms.
        parsed_json["MainSymptoms"] = confirmed_symptoms
        # Constraint #3: Urgency escalation on red flags.
        parsed_json["Urgency"] = "Emergency" if has_red_flag else "Routine"

        # Ensure TopDiseaseMatches use rule-engine names when LLM omits or mislabels them.
        if isinstance(mapped_diseases, dict):
            mapped_conditions = mapped_diseases.get("conditions")
            if isinstance(mapped_conditions, list) and mapped_conditions:
                matches = parsed_json.get("TopDiseaseMatches")
                if not isinstance(matches, list):
                    matches = []
                normalized_matches = []
                used_names = set()
                for idx, entry in enumerate(matches):
                    if not isinstance(entry, dict):
                        continue
                    name = _extract_match_name(entry)
                    if not name and idx < len(mapped_conditions):
                        cond = mapped_conditions[idx]
                        if isinstance(cond, dict):
                            name = str(cond.get("name", "")).strip()
                    if not name:
                        continue
                    key = str(name).strip().lower()
                    if key in used_names:
                        continue
                    used_names.add(key)
                    match_level = (
                        entry.get("MatchLevel")
                        or entry.get("matchLevel")
                        or (mapped_conditions[idx].get("probability") if idx < len(mapped_conditions) and isinstance(mapped_conditions[idx], dict) else None)
                        or "Moderate"
                    )
                    normalized_matches.append(
                        {
                            "Name": name,
                            "MatchLevel": match_level,
                            "PreHospitalCare": entry.get("PreHospitalCare") or entry.get("preHospitalCare") or [],
                            "SymptomsToWatch": entry.get("SymptomsToWatch") or entry.get("symptomsToWatch") or [],
                            "SelfCare": entry.get("SelfCare") or entry.get("selfCare") or [],
                            "MedicationSuggestion": entry.get("MedicationSuggestion") or entry.get("medicationSuggestion") or [],
                        }
                    )
                    if len(normalized_matches) >= 2:
                        break
                for cond in mapped_conditions:
                    if len(normalized_matches) >= 2:
                        break
                    if not isinstance(cond, dict):
                        continue
                    name = str(cond.get("name", "")).strip()
                    if not name:
                        continue
                    key = name.lower()
                    if key in used_names:
                        continue
                    used_names.add(key)
                    normalized_matches.append(
                        {
                            "Name": name,
                            "MatchLevel": cond.get("probability") or "Moderate",
                            "PreHospitalCare": ["Stay hydrated", "Monitor symptoms closely"],
                            "SymptomsToWatch": ["Worsening symptoms", "Severe pain or breathing difficulty"],
                            "SelfCare": ["Rest and avoid strenuous activity"],
                            "MedicationSuggestion": ["Consult a doctor before taking medication"],
                        }
                    )
                if normalized_matches:
                    parsed_json["TopDiseaseMatches"] = normalized_matches[:2]

        parsed_json["NextDiagnosticSteps"] = build_next_diagnostic_steps(
            parsed_json, mapped_diseases
        )

        # Add context metadata to the report
        from datetime import datetime

        meta = {
            "context_used": [],
            "timestamp": str(datetime.now()),
            "analysis_type": "personalized",
        }

        # Only consider BMI when BOTH weight and height are present and valid.
        # Do not infer or assume BMI if either is missing.
        try:
            w = float(weight) if weight is not None else None
            h = float(height) if height is not None else None
            if w is not None and h is not None and w > 0 and h > 0:
                if 0.5 <= h <= 2.5:
                    h = h * 100.0
                elif 36 <= h <= 96:
                    h = h * 2.54
                if 20 <= w <= 400 and 90 <= h <= 250:
                    meta["context_used"].append("weight")
                    meta["context_used"].append("height")
                    bmi = w / ((h / 100) ** 2)
                    if 0 < bmi <= 80:
                        meta["bmi"] = round(bmi, 1)
        except Exception:
            # Keep report flow stable even when inputs are malformed.
            pass
        if physical_activity:
            meta["context_used"].append("activity")
        if diet_type:
            meta["context_used"].append("diet")

        # Add personalized analysis note
        if meta["context_used"]:
            meta["note"] = "Analysis personalized using your physical and lifestyle profile."
        else:
            meta["note"] = "Basic analysis using symptoms and demographics only."

        parsed_json["meta"] = meta
        return parsed_json

    except Exception as exc:
        logger.exception(
            "An API error occurred during report content generation: %s", exc
        )
        return _fallback_report(age, gender, symptoms, chat_history, mapped_diseases)
