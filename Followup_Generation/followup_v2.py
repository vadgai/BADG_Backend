# Backend/Followup_Generation/followup_v2.py
"""
CLINICAL FOLLOW-UP QUESTION ENGINE v2.0
Enhanced version with guaranteed question generation and clinical reasoning.
"""

import os
import json
import math
import logging
from typing import Optional, Union, Dict, List
from dotenv import load_dotenv

from utils.gemini_api_manager import (
    generate_content_with_fallback,
    get_gemini_model,
    extract_json_from_text,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Gemini model
model_available, model = get_gemini_model()
if model_available:
    logger.info("✅ Clinical Follow-up Engine initialized with Gemini API")
else:
    logger.warning("⚠️ Clinical Follow-up Engine using fallback mode (no Gemini API)")


# ==================== CLINICAL FALLBACK QUESTIONS ====================

CLINICAL_FALLBACK_PATTERNS = {
    "fever": [
        {
            "Question": "How high is your fever, and does it come and go or stay constant?",
            "clinical_purpose": "Differentiate fever patterns between infections",
            "differentiates_between": ["Viral infection", "Bacterial infection", "Malaria"],
            "A": "High fever (>102°F/39°C), constant",
            "B": "Moderate fever (100-102°F), intermittent",
            "C": "Low-grade fever (<100°F/37.8°C)",
            "D": "None of these"
        },
        {
            "Question": "Do you have chills, rigors, or night sweats with the fever?",
            "clinical_purpose": "Assess severity and type of infection",
            "differentiates_between": ["Severe bacterial infection", "Viral fever", "Tuberculosis"],
            "A": "Yes, severe shaking chills",
            "B": "Yes, night sweats only",
            "C": "No chills or sweats",
            "D": "None of these"
        }
    ],
    "cough": [
        {
            "Question": "What type of cough do you have, and is there any sputum?",
            "clinical_purpose": "Differentiate respiratory conditions",
            "differentiates_between": ["Pneumonia", "Bronchitis", "Dry cough/viral URI"],
            "A": "Dry cough, no sputum",
            "B": "Productive cough with clear/white sputum",
            "C": "Productive cough with yellow/green/bloody sputum",
            "D": "None of these"
        },
        {
            "Question": "Is the cough worse at night or when lying down?",
            "clinical_purpose": "Identify postnasal drip or cardiac causes",
            "differentiates_between": ["Post-nasal drip", "Asthma", "Heart failure"],
            "A": "Yes, much worse at night",
            "B": "Yes, worse when lying flat",
            "C": "No pattern, same all day",
            "D": "None of these"
        }
    ],
    "pain": [
        {
            "Question": "Can you describe the character of your pain?",
            "clinical_purpose": "Classify pain type for differential diagnosis",
            "differentiates_between": ["Inflammatory", "Neuropathic", "Musculoskeletal", "Visceral"],
            "A": "Sharp, stabbing, knife-like pain",
            "B": "Dull, aching, throbbing pain",
            "C": "Burning, tingling, electric-shock pain",
            "D": "None of these"
        },
        {
            "Question": "Does the pain radiate or spread to other areas?",
            "clinical_purpose": "Assess referred pain patterns",
            "differentiates_between": ["Localized injury", "Referred pain", "Radicular pain"],
            "A": "Yes, radiates to other areas",
            "B": "No, stays in one spot",
            "C": "Moves around unpredictably",
            "D": "None of these"
        }
    ],
    "headache": [
        {
            "Question": "Where exactly is the headache located?",
            "clinical_purpose": "Localize headache type",
            "differentiates_between": ["Migraine", "Tension headache", "Cluster headache", "Sinusitis"],
            "A": "One side of head (unilateral)",
            "B": "Behind eyes/forehead area",
            "C": "Band-like around entire head",
            "D": "None of these"
        },
        {
            "Question": "Are there any warning signs before the headache starts?",
            "clinical_purpose": "Identify migraine aura or red flags",
            "differentiates_between": ["Migraine with aura", "Simple headache", "Secondary headache"],
            "A": "Yes, visual disturbances or flashing lights",
            "B": "Yes, numbness or tingling",
            "C": "No warning signs",
            "D": "None of these"
        }
    ],
    "abdominal_pain": [
        {
            "Question": "Where exactly in your abdomen is the pain located?",
            "clinical_purpose": "Localize organ system involved",
            "differentiates_between": ["Appendicitis", "Gastritis", "Cholecystitis", "IBS"],
            "A": "Right lower abdomen",
            "B": "Right upper abdomen (below ribs)",
            "C": "Upper center or left abdomen",
            "D": "Cramping all over abdomen"
        },
        {
            "Question": "Does eating or bowel movements affect the pain?",
            "clinical_purpose": "Differentiate GI vs surgical causes",
            "differentiates_between": ["Gastritis/Ulcer", "IBS", "Appendicitis"],
            "A": "Pain worsens with eating",
            "B": "Pain improves with eating",
            "C": "Pain relieved after bowel movement",
            "D": "None of these"
        }
    ],
    "breathing": [
        {
            "Question": "Do you have difficulty breathing or shortness of breath?",
            "clinical_purpose": "Assess respiratory compromise (RED FLAG)",
            "differentiates_between": ["Pneumonia", "Asthma", "Heart failure", "Pulmonary embolism"],
            "A": "Yes, severe difficulty breathing at rest",
            "B": "Yes, difficulty with exertion only",
            "C": "No breathing difficulty",
            "D": "None of these"
        },
        {
            "Question": "Is there chest pain or tightness with breathing?",
            "clinical_purpose": "Identify pleuritic or cardiac causes",
            "differentiates_between": ["Pleurisy", "Pneumonia", "PE", "Cardiac ischemia"],
            "A": "Yes, sharp pain with deep breathing",
            "B": "Yes, pressure/tightness in chest",
            "C": "No chest symptoms",
            "D": "None of these"
        }
    ],
    "general": [
        {
            "Question": "When did these symptoms start, and how did they develop?",
            "clinical_purpose": "Assess temporal pattern and severity",
            "differentiates_between": ["Acute condition", "Chronic condition", "Progressive disease"],
            "A": "Sudden onset (within hours)",
            "B": "Gradual onset (over days)",
            "C": "Chronic (weeks to months)",
            "D": "None of these"
        },
        {
            "Question": "Are symptoms constant or do they come and go?",
            "clinical_purpose": "Identify pattern and triggers",
            "differentiates_between": ["Continuous disease", "Intermittent condition", "Triggered episodes"],
            "A": "Constant, always present",
            "B": "Intermittent, comes and goes",
            "C": "Triggered by specific activities",
            "D": "None of these"
        }
    ]
}


def _get_symptom_based_fallback(symptoms: Union[str, List], question_number: int = 0) -> Dict:
    """
    Generate clinically relevant fallback question based on symptom keywords.
    GUARANTEED to return a valid question.
    """
    symptoms_str = " ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    symptoms_lower = symptoms_str.lower()
    
    # Pattern matching with priority order
    patterns = [
        ("fever", CLINICAL_FALLBACK_PATTERNS["fever"]),
        ("cough", CLINICAL_FALLBACK_PATTERNS["cough"]),
        ("pain", CLINICAL_FALLBACK_PATTERNS["pain"]),
        ("ache", CLINICAL_FALLBACK_PATTERNS["pain"]),
        ("headache", CLINICAL_FALLBACK_PATTERNS["headache"]),
        ("abdominal", CLINICAL_FALLBACK_PATTERNS["abdominal_pain"]),
        ("stomach", CLINICAL_FALLBACK_PATTERNS["abdominal_pain"]),
        ("breath", CLINICAL_FALLBACK_PATTERNS["breathing"]),
        ("dyspnea", CLINICAL_FALLBACK_PATTERNS["breathing"]),
    ]
    
    # Find matching pattern
    for keyword, questions in patterns:
        if keyword in symptoms_lower:
            # Return appropriate question from the pattern list
            idx = question_number % len(questions)
            return questions[idx]
    
    # Generic fallback if no pattern matches
    generic_questions = CLINICAL_FALLBACK_PATTERNS["general"]
    idx = question_number % len(generic_questions)
    return generic_questions[idx]


def _validate_json_response(data: Dict) -> bool:
    """Validate that JSON response has required structure."""
    if not isinstance(data, dict):
        return False
    
    # Check for either old MCQ format or new structured format
    has_mcq_format = all(k in data for k in ["Question", "A", "B", "C", "D"])
    has_new_format = "follow_up_questions" in data and isinstance(data["follow_up_questions"], list)
    
    return has_mcq_format or has_new_format


def _convert_to_mcq_format(data: Dict) -> Dict:
    """Convert new structured format to legacy MCQ format for compatibility."""
    if "follow_up_questions" in data and data["follow_up_questions"]:
        # Extract first question from structured format
        first_q = data["follow_up_questions"][0]
        clinical_purpose = first_q.get("clinical_purpose") or first_q.get("clinical_focus", "")
        differentiates = first_q.get("differentiates_between")
        if not differentiates:
            differentiates = data.get("current_differential") or data.get("top_differentials") or []
        mcq = {
            "Question": first_q.get("question", ""),
            "A": first_q.get("options", {}).get("A", "Option A"),
            "B": first_q.get("options", {}).get("B", "Option B"),
            "C": first_q.get("options", {}).get("C", "Option C"),
            "D": "None of these",
            "clinical_purpose": clinical_purpose,
            "differentiates_between": differentiates,
        }
        for key in ("branch_switch_triggered", "red_flag_triggered"):
            if key in data:
                mcq[key] = data[key]
        return mcq
    return data


# ==================== IMPROVED CLINICAL PROMPT ====================

def _format_history_v2(chat_history: Union[str, List, None]) -> str:
    """Compact Q/A formatter to reduce token usage while preserving context."""
    if not chat_history:
        return "No previous questions asked"
    if isinstance(chat_history, str):
        return chat_history.strip() or "No previous questions asked"
    if isinstance(chat_history, list):
        lines = []
        q_idx = 0
        for i, msg in enumerate(chat_history):
            if not isinstance(msg, dict):
                continue
            q = msg.get("bot") or msg.get("Question")
            if q:
                q_idx += 1
                lines.append(f"Q{q_idx}: {str(q).strip()}")
                if i + 1 < len(chat_history):
                    nxt = chat_history[i + 1]
                    if isinstance(nxt, dict) and nxt.get("user"):
                        lines.append(f"A{q_idx}: {str(nxt.get('user')).strip()}")
        return "\n".join(lines) if lines else "No previous questions asked"
    return "No previous questions asked"


def _extract_last_answer_v2(chat_history: Union[str, List, None]) -> str:
    """Get latest patient answer from history for context grounding."""
    if not chat_history:
        return "None"
    if isinstance(chat_history, str):
        try:
            chat_history = json.loads(chat_history)
        except Exception:
            return "None"
    if isinstance(chat_history, list):
        for msg in reversed(chat_history):
            if isinstance(msg, dict) and msg.get("user"):
                return str(msg.get("user")).strip() or "None"
    return "None"


def _build_bmi_signal(weight: Optional[Union[int, float, str]], height: Optional[Union[int, float, str]]) -> Dict[str, Union[bool, float, str, None]]:
    """
    Safe BMI signal for prompt grounding.
    Returns structured data and never raises.
    """
    fallback = {
        "available": False,
        "value": None,
        "category": "Unknown",
        "text": "BMI not available",
    }
    try:
        if weight is None or height is None:
            return fallback
        w = float(weight)
        h = float(height)
        if not math.isfinite(w) or not math.isfinite(h) or w <= 0 or h <= 0:
            return fallback
        if 0.5 <= h <= 2.5:
            h *= 100.0
        elif 36 <= h <= 96:
            h *= 2.54
        if not (20 <= w <= 400 and 90 <= h <= 250):
            return fallback
        bmi = w / ((h / 100.0) ** 2)
        if not math.isfinite(bmi) or bmi <= 0 or bmi > 80:
            return fallback
        bmi_cat = "Underweight" if bmi < 18.5 else "Normal" if bmi < 25 else "Overweight" if bmi < 30 else "Obese"
        bmi_value = round(bmi, 1)
        return {
            "available": True,
            "value": bmi_value,
            "category": bmi_cat,
            "text": f"BMI: {bmi_value:.1f} ({bmi_cat})",
        }
    except Exception:
        return fallback

def _build_clinical_prompt(
    age: int,
    gender: str,
    symptoms: Union[str, List],
    chat_history: str,
    question_count: int,
    max_questions: int = 8,
    weight: float = None,
    height: float = None,
    occupation: str = None,
    location: dict = None,
    physical_activity: str = None,
    diet_type: str = None,
) -> str:
    """
    Build comprehensive clinical reasoning prompt that GUARANTEES question generation.
    """
    
    symptoms_str = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    patient_context = f"{age}-year-old {gender.lower()}"

    bmi_signal = _build_bmi_signal(weight, height)
    bmi_value = f"{bmi_signal['value']:.1f}" if bmi_signal.get("available") and bmi_signal.get("value") is not None else "Not available"
    bmi_category = bmi_signal.get("category", "Unknown") if bmi_signal.get("available") else "Unknown"

    history_text = _format_history_v2(chat_history)
    latest_answer = _extract_last_answer_v2(chat_history)
    next_question_id = question_count + 1

    prompt = f"""You are VADG-Clinical, a safe and efficient diagnostic reasoning engine.
Language: English only.

GOAL: Identify the top 2 likely diseases with maximum Information Gain.
Limit: Max 8 questions.

=== PATIENT CONTEXT ===
Patient: {patient_context}
BMI: {bmi_value} ({bmi_category})
Presenting Symptoms: {symptoms_str}
Current History:
{history_text}
Last Answer: "{latest_answer}"
Question Count: {question_count}/{max_questions}

=== REASONING LOGIC ===
1. **Analyze State**:
   - If `Last Answer` was "None of these" (or negative), DISCARD the previous top hypothesis. Switch to the next most likely organ system/cause.
   - If `Last Answer` was Positive, drill deeper into that specific condition.

2. **BMI Integration**:
   - If BMI ≥ 30 (Obese): Prioritize metabolic, cardiovascular, and respiratory (OSA) conditions.
   - If BMI < 18.5 (Underweight): Prioritize malabsorption, chronic infection, or metabolic disorders.

3. **Termination**:
   - If you have > 80% confidence in Top 1 disease OR Question Count >= 8:
     Return "ready_for_diagnosis": true.

4. **Question Generation**:
   - Generate ONE high-value Multiple Choice Question (MCQ).
   - The question must differentiate between your Top #1 and Top #2 suspects.
   - Options must be mutually exclusive.
   - Set "branch_switch_triggered" to true if you pivoted because the last answer was "None of these".

=== OUTPUT FORMAT (JSON ONLY) ===
{{
  "follow_up_questions": [
    {{
      "id": {next_question_id},
      "question": "Clear, patient-friendly question text?",
      "clinical_focus": "Differentiating [Disease A] vs [Disease B]",
      "options": {{
        "A": "Specific Symptom A",
        "B": "Specific Symptom B",
        "C": "Specific Symptom C",
        "D": "None of these"
      }}
    }}
  ],
  "current_differential": ["Disease A", "Disease B"],
  "branch_switch_triggered": false,
  "red_flag_triggered": false,
  "ready_for_diagnosis": false
}}
"""
    
    return prompt


# ==================== MAIN GENERATION FUNCTION ====================

def get_followup_for_diagnosis_v2(
    age: int,
    gender: str,
    symptoms: Union[str, list],
    chat_history: str,
    max_retries: int = 1,
    weight: float = None,
    height: float = None,
    occupation: str = None,
    location: dict = None,
    physical_activity: str = None,
    diet_type: str = None,
) -> Union[Dict, str]:
    """
    Enhanced follow-up question generator with GUARANTEED output.
    
    Returns:
        - Dict with MCQ format question
        - "Ready for diagnosis" string
        NEVER returns None
    """
    
    # Count existing bot questions from either list or string history
    question_count = 0
    if isinstance(chat_history, list):
        for msg in chat_history:
            if isinstance(msg, dict) and (msg.get("bot") or msg.get("Question")):
                question_count += 1
    elif isinstance(chat_history, str) and chat_history:
        question_count = chat_history.count("Question:") + chat_history.count("Q:")
    
    max_questions = 8
    
    # Hard limit: if max questions reached, return ready
    if question_count >= max_questions:
        logger.info(f"Maximum questions ({max_questions}) reached. Proceeding to diagnosis.")
        return "Ready for diagnosis"
    
    # Check if Gemini is available
    model_ok, _ = get_gemini_model()
    
    if not model_ok:
        logger.warning("Gemini API not available. Using clinical fallback.")
        return _get_symptom_based_fallback(symptoms, question_count)
    
    # Build clinical prompt
    prompt = _build_clinical_prompt(
        age, gender, symptoms, chat_history, question_count, max_questions,
        weight, height, occupation, location, physical_activity, diet_type
    )
    
    # Try Gemini API with all fallback keys
    try:
        success, raw_text, error = generate_content_with_fallback(
            prompt=prompt,
            max_retries=None,  # Try all keys
            temperature=0.3,
            max_output_tokens=1100,
        )
        
        if not success or not raw_text:
            logger.error(f"Gemini API failed: {error}. Using clinical fallback.")
            return _get_symptom_based_fallback(symptoms, question_count)
        
        # Check for ready signal
        if "ready_for_diagnosis" in raw_text.lower() and "true" in raw_text.lower():
            logger.info("AI indicates ready for diagnosis")
            return "Ready for diagnosis"
        
        # Parse JSON response
        parsed = extract_json_from_text(raw_text)
        
        if parsed is None:
            logger.error("Failed to parse JSON from Gemini response. Using fallback.")
            logger.debug(f"Raw response: {raw_text[:500]}")
            return _get_symptom_based_fallback(symptoms, question_count)
        
        # Validate structure
        if not _validate_json_response(parsed):
            logger.error("Invalid JSON structure. Using fallback.")
            return _get_symptom_based_fallback(symptoms, question_count)
        
        # Check if ready for diagnosis
        if isinstance(parsed, dict) and parsed.get("ready_for_diagnosis"):
            logger.info("AI determined ready for diagnosis")
            return "Ready for diagnosis"
        
        # Convert to MCQ format for compatibility
        mcq = _convert_to_mcq_format(parsed)
        
        # Ensure option D is correct
        if "D" in mcq:
            mcq["D"] = "None of these"
        
        # Validate final MCQ structure
        required_keys = ["Question", "A", "B", "C", "D"]
        if not all(k in mcq for k in required_keys):
            logger.error("MCQ missing required keys after conversion. Using fallback.")
            return _get_symptom_based_fallback(symptoms, question_count)
        
        logger.info(f"✅ Generated question {question_count + 1}: {mcq.get('Question', '')[:100]}...")
        return mcq
        
    except Exception as e:
        logger.exception(f"Unhandled exception in follow-up generation: {e}")
        return _get_symptom_based_fallback(symptoms, question_count)


# ==================== BACKWARD COMPATIBILITY ====================

# Alias for drop-in replacement
get_followup_for_diagnosis = get_followup_for_diagnosis_v2
