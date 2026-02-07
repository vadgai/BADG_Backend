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
        "Recommendation": "Please consult a healthcare professional for proper diagnosis and treatment.",
        "Urgency": "Routine",
        "ReasonForConsultation": f"Patient reports symptoms: {', '.join(symptom_list)}",
        "MainSymptoms": symptom_list[:6],  # Top 6 symptoms
        "TopDiseaseMatches": [
            {
                "Disease1": {
                    "Name1": "Unable to determine - AI unavailable",
                    "MatchLevel1": "Unknown",
                    "PreHospitalCare1": ["Seek medical consultation", "Monitor symptoms"],
                    "SymptomsToWatch1": ["Worsening symptoms", "New symptoms"],
                    "SelfCare1": ["Rest", "Stay hydrated", "Monitor temperature"],
                    "MedicationSuggestion1": ["Consult doctor before taking medication"]
                }
            }
        ]
    }

    # IMPORTANT: return the report object directly (not JSON string),
    # so that it matches the shape of normal AI-generated reports.
    return report


def _format_chat_history(chat_history) -> str:
    """
    Normalize chat history into a readable Q/A transcript for LLM prompts.
    Accepts list of {bot/user} dicts, a JSON string, or plain string.
    """
    if not chat_history:
        return "No previous questions asked."

    if isinstance(chat_history, str):
        # Try to parse JSON list if present; otherwise return as-is
        try:
            parsed = json.loads(chat_history)
            chat_history = parsed
        except Exception:
            return chat_history.strip() or "No previous questions asked."

    if isinstance(chat_history, list):
        lines = []
        q_idx = 0
        for i, msg in enumerate(chat_history):
            if not isinstance(msg, dict):
                continue
            bot_text = msg.get("bot") or msg.get("Question")
            if bot_text:
                q_idx += 1
                lines.append(f"Q{q_idx}: {str(bot_text).strip()}")
                # Try to pair with next user response if available
                if i + 1 < len(chat_history):
                    next_msg = chat_history[i + 1]
                    if isinstance(next_msg, dict) and next_msg.get("user"):
                        lines.append(f"A{q_idx}: {str(next_msg.get('user')).strip()}")
        return "\n".join(lines) if lines else "No previous questions asked."

    return str(chat_history).strip() or "No previous questions asked."

def generate_report_prompt(age, gender, symptoms, chat_history, mapped_diseases):
    formatted_symptoms = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    chat_history_text = _format_chat_history(chat_history)

    sample_report = {
        "PatientInfo": {
            "Age": "42 Years",
            "Gender": "Man"
        },
        "Recommendation": "Schedule an appointment with a physician within the next 24–48 hours.",
        "Urgency": "Moderate",
        "ReasonForConsultation": "Patient reports persistent sore throat, moderate fever, headache, and fatigue.",
        "MainSymptoms": [
            "Sore throat",
            "Headache",
            "Fatigue",
            "Moderate fever",
            "Dry cough"
        ],
        "NextDiagnosticSteps": [
            "Your doctor may recommend a few diagnostic tests to understand your condition better.",
            "Complete Blood Count (CBC) test helps detect infection or inflammation.",
            "Throat culture or rapid antigen test to confirm bacterial throat infection.",
            "These tests allow your doctor to identify underlying causes."
        ],
        "TopDiseaseMatches": [
            {
                "Disease1": {
                    "Name1": "Strep throat",
                    "MatchLevel1": "High",
                    "PreHospitalCare1": [
                        "Drink warm fluids",
                        "Use throat lozenges"
                    ],
                    "SymptomsToWatch1": [
                        "Difficulty breathing",
                        "Persistent high fever"
                    ],
                    "SelfCare1": [
                        "Rest",
                        "Maintain good hygiene"
                    ],
                    "MedicationSuggestion1": [
                        "Acetaminophen for fever",
                        "Amoxicillin if prescribed"
                    ]
                }
            }
        ]
    }

    return f"""
You are a senior medical AI assistant. Produce a JSON report ONLY — do NOT include any explanation,
markdown, or extra text. The JSON must follow this structure exactly (sample shown):

{json.dumps(sample_report, indent=2)}

Now generate the report for:
Age: {age}
Gender: {gender}
Symptoms: {formatted_symptoms}

Chat History:
{chat_history_text}

Mapped diseases (and match levels):
{mapped_diseases}

Requirements:
- Output must be valid JSON ONLY (start with '{{' and end with '}}').
- Keep lines short and crisp (this will be converted to PDF).
- Use easy-to-understand Indian English where appropriate.
- For each disease include pre-hospital care, symptoms to watch, self-care, and medication suggestions.
- End the JSON with 'Urgency' and a clear 'Recommendation'.

Return only the JSON object, nothing else.
"""




def final_report(age, gender, symptoms, chat_history, mapped_diseases, weight=None, height=None, occupation=None, location=None, physical_activity=None, diet_type=None):
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
            age, gender, symptoms, chat_history, mapped_diseases
        )

        # Use centralized multi-key manager with full fallback across all configured keys
        success, raw_response, error = generate_content_with_fallback(
            prompt=prompt,
            max_retries=None,  # try all available keys (up to 15)
            temperature=0.3,
            max_output_tokens=4000,
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
                    max_output_tokens=4000,
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

        # Add context metadata to the report
        from datetime import datetime

        meta = {
            "context_used": [],
            "timestamp": str(datetime.now()),
            "analysis_type": "personalized",
        }

        # Only consider BMI when BOTH weight and height are present and valid.
        # Do not infer or assume BMI if either is missing.
        if weight is not None and height is not None and weight > 0 and height > 0:
            meta["context_used"].append("weight")
            meta["context_used"].append("height")
            bmi = weight / ((height / 100) ** 2)
            meta["bmi"] = round(bmi, 1)
        if occupation:
            meta["context_used"].append("occupation")
        if physical_activity:
            meta["context_used"].append("activity")
        if diet_type:
            meta["context_used"].append("diet")
        if location:
            meta["context_used"].append("location")

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
