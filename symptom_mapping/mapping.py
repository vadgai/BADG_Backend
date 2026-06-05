import os
import json
import math
import hashlib
import logging
from typing import Any, Dict, Optional, Union
from dotenv import load_dotenv
load_dotenv()

# Import centralized Gemini API manager
from utils.gemini_api_manager import (
    get_gemini_model,
    MODEL_NAME,
    generate_content_with_fallback,
    extract_json_from_text,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get model from centralized manager (with 15-key fallback support)
model_available, model = get_gemini_model()

if model_available:
    logger.info("="*80)
    logger.info(f"✅ Gemini model available for disease mapping (via API manager)")
    logger.info(f"   Model: {MODEL_NAME}")
    logger.info("="*80)
else:
    logger.warning("="*80)
    logger.warning("⚠️ Gemini model not available for disease mapping")
    logger.warning("   Disease mapping will use fallback behavior")
    logger.warning("="*80)

# minimal logging toggle
DEBUG = os.getenv("VADG_DEBUG", "0") == "1"

# simple in-memory cache to speed up identical requests
_prompt_cache: Dict[str, Any] = {}

def _cache_key_for_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

def _maybe_log(title: str, content: str):
    if DEBUG:
        print("=" * 80)
        print(title)
        print(content)
        print("=" * 80)


def _coerce_numeric(value: Optional[Union[int, float, str]]) -> Optional[float]:
    """Safely coerce numeric inputs; return None for invalid/unclear values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"", "na", "n/a", "none", "null", "unknown", "-"}:
            return None
        cleaned = "".join(ch for ch in raw if ch in "0123456789.+-")
        if cleaned in {"", ".", "+", "-", "+.", "-."}:
            return None
        try:
            parsed = float(cleaned)
        except Exception:
            return None
    else:
        try:
            parsed = float(value)
        except Exception:
            return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _normalize_height_cm(height_value: Optional[Union[int, float, str]]) -> Optional[float]:
    """Normalize height to centimeters from cm/meters/inches."""
    value = _coerce_numeric(height_value)
    if value is None or value <= 0:
        return None

    if 0.5 <= value <= 2.5:
        value = value * 100.0
    elif 36 <= value <= 96:
        value = value * 2.54

    if not (90 <= value <= 250):
        return None
    return value


def _build_bmi_signal(weight: Optional[Union[int, float, str]], height: Optional[Union[int, float, str]]) -> Dict[str, Optional[Union[bool, float, str]]]:
    """Compute BMI signal for disease ranking prompts without breaking on bad input."""
    weight_kg = _coerce_numeric(weight)
    height_cm = _normalize_height_cm(height)
    if weight_kg is None or height_cm is None or weight_kg <= 0 or not (20 <= weight_kg <= 400):
        return {"available": False, "value": None, "category": "Unknown", "text": "Not available"}

    bmi = weight_kg / ((height_cm / 100.0) ** 2)
    if not math.isfinite(bmi) or bmi <= 0 or bmi > 80:
        return {"available": False, "value": None, "category": "Unknown", "text": "Not available"}

    if bmi < 18.5:
        category = "Underweight"
    elif bmi < 25:
        category = "Normal"
    elif bmi < 30:
        category = "Overweight"
    else:
        category = "Obese"

    bmi_rounded = round(bmi, 1)
    return {
        "available": True,
        "value": bmi_rounded,
        "category": category,
        "text": f"{bmi_rounded:.1f} ({category})",
    }

def _fallback_disease_mapping(symptoms):
    """
    Fallback disease mapping when AI is unavailable.
    Returns basic mapping based on common symptom patterns.
    """
    symptom_str = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    symptom_lower = symptom_str.lower()

    conditions = []

    if any(s in symptom_lower for s in ["fever", "temperature", "hot"]):
        conditions.append(
            {
                "name": "Viral infection",
                "probability": "Moderate",
                "match_score": "6/10",
                "reasoning": "Fever fits a viral syndrome pattern.",
                "urgency": "Self-Care",
            }
        )

    if any(s in symptom_lower for s in ["cough", "phlegm", "chest"]):
        conditions.append(
            {
                "name": "Respiratory infection",
                "probability": "Moderate",
                "match_score": "6/10",
                "reasoning": "Respiratory symptoms are reported.",
                "urgency": "Self-Care",
            }
        )

    if any(s in symptom_lower for s in ["headache", "head pain"]):
        conditions.append(
            {
                "name": "Tension headache",
                "probability": "Low",
                "match_score": "4/10",
                "reasoning": "Headache reported without clear red flags.",
                "urgency": "Self-Care",
            }
        )

    if not conditions:
        conditions.append(
            {
                "name": "General malaise",
                "probability": "Low",
                "match_score": "3/10",
                "reasoning": "Non-specific symptoms reported.",
                "urgency": "Self-Care",
            }
        )

    diagnosis_summary = "Symptoms suggest a non-specific acute illness based on limited information."
    return {
        "diagnosis_summary": diagnosis_summary,
        "conditions": conditions[:3],
        "suggested_specialist": "General Physician",
    }


def _normalize_mapping_result(data: Dict, symptoms) -> Dict:
    """Ensure disease mapping output has a stable 1-3 condition shape."""
    if not isinstance(data, dict):
        return _fallback_disease_mapping(symptoms)

    raw_conditions = data.get("conditions")
    if not isinstance(raw_conditions, list):
        return _fallback_disease_mapping(symptoms)

    normalized = []
    for cond in raw_conditions:
        if not isinstance(cond, dict):
            continue
        name = str(cond.get("name", "")).strip()
        probability = str(cond.get("probability", "Low")).strip()
        match_score = str(cond.get("match_score", "")).strip()
        reasoning = str(cond.get("reasoning", "")).strip()
        urgency = str(cond.get("urgency", "Routine")).strip()
        if not name:
            continue
        if not probability:
            probability = "Low"
        allowed_urgency = {"Emergency", "Urgent", "Routine", "Self-Care", "Monitor", "High", "Moderate", "Low"}
        if urgency not in allowed_urgency:
            urgency = "Routine"
        if not reasoning:
            reasoning = "Based on reported symptoms and follow-up responses."
        entry = {
            "name": name,
            "probability": probability,
            "reasoning": reasoning,
            "urgency": urgency,
        }
        if match_score:
            entry["match_score"] = match_score
        normalized.append(entry)
        if len(normalized) >= 3:
            break

    if not normalized:
        return _fallback_disease_mapping(symptoms)

    result = {"conditions": normalized}
    if "diagnosis_summary" in data:
        result["diagnosis_summary"] = str(data.get("diagnosis_summary", "")).strip()
    if "accuracy_warning" in data:
        result["accuracy_warning"] = str(data.get("accuracy_warning", "")).strip()
    if "suggested_specialist" in data:
        result["suggested_specialist"] = str(data.get("suggested_specialist", "")).strip()
    return result



def generate_llm_prompt(
    age,
    gender,
    symptoms,
    symptom_state=None,
    negatives=None,
    weight=None,
    height=None,
    occupation=None,
    location=None,
    physical_activity=None,
    diet_type=None,
):
    state = symptom_state if isinstance(symptom_state, dict) else {}
    positives = state.get("current_symptoms") if isinstance(state.get("current_symptoms"), list) else symptoms
    positives = positives if isinstance(positives, list) else [str(positives)] if positives else []
    positives = [str(s).strip() for s in positives if str(s).strip()]
    formatted_symptoms = ", ".join(positives) if positives else "None reported"

    modifiers = state.get("modifiers") if isinstance(state.get("modifiers"), list) else []
    red_flags = state.get("red_flags") if isinstance(state.get("red_flags"), list) else []
    questions_asked = state.get("questions_asked") if isinstance(state.get("questions_asked"), list) else []

    negatives_list = negatives if isinstance(negatives, list) else []
    negatives_list = [str(n).strip() for n in negatives_list if str(n).strip()]
    symptoms_negatives = ", ".join(negatives_list) if negatives_list else "None reported"

    bmi_signal = _build_bmi_signal(weight, height)
    bmi_value = f"{bmi_signal['value']:.1f}" if bmi_signal.get("available") and bmi_signal.get("value") is not None else "Not available"
    bmi_category = bmi_signal.get("category", "Unknown") if bmi_signal.get("available") else "Unknown"
    modifiers_text = ", ".join(str(m).strip() for m in modifiers if str(m).strip()) or "None reported"
    red_flags_text = ", ".join(str(r).strip() for r in red_flags if str(r).strip()) or "None reported"
    asked_count = len(questions_asked)

    prompt = f"""ACT: Medical Reporter (Mapping Mode).
GOAL: Produce TOP 3 disease matches from structured clinical evidence only.

=== EVIDENCE BOARD ===
Profile: {age}/{gender}, BMI: {bmi_value} ({bmi_category})
Positive Findings (+): {formatted_symptoms}
Negative Findings (-): {symptoms_negatives}
Modifiers: {modifiers_text}
Red Flags: {red_flags_text}
Questions Asked: {asked_count}

=== DIAGNOSTIC ALGORITHM ===
1. Use ONLY structured findings above (no raw chat history inference).
2. Rank top 3 conditions by best fit to (+), (-), modifiers, and demographics.
3. If "Weight Loss" is positive, prioritize chronic/systemic causes over acute self-limiting infections.
4. If red flags are present, elevate urgency accordingly.
5. Keep reasoning concise and explicitly evidence-grounded to (+)/(-)/modifiers/red flags.
6. Never output placeholders like "Condition 1" in final values.

=== OUTPUT JSON ONLY ===
{{
  "diagnosis_summary": "Short evidence-based summary.",
  "conditions": [
    {{
      "name": "Appendicitis",
      "probability": "High|Moderate|Low",
      "match_score": "0-10",
      "reasoning": "Why this fits (+) and (-).",
      "urgency": "Emergency|Routine|Monitor|Self-Care"
    }},
    {{
      "name": "Gastroenteritis",
      "probability": "High|Moderate|Low",
      "match_score": "0-10",
      "reasoning": "Why this is second.",
      "urgency": "Emergency|Routine|Monitor|Self-Care"
    }},
    {{
      "name": "Acid Peptic Disease",
      "probability": "High|Moderate|Low",
      "match_score": "0-10",
      "reasoning": "Why this remains possible.",
      "urgency": "Emergency|Routine|Monitor|Self-Care"
    }}
  ],
  "accuracy_warning": "Optional confidence note.",
  "suggested_specialist": "Optional specialist"
}}
"""

    # Log the prompt for verification (debug only)
    _maybe_log("LLM PROMPT =>", prompt)
    
    return prompt



def get_disease_symptom_mapping(
    age,
    gender,
    symptoms,
    chat_history,
    weight=None,
    height=None,
    occupation=None,
    location=None,
    physical_activity=None,
    diet_type=None,
    symptom_state=None,
    patient_state=None,
    negatives=None,
):
    state_obj = symptom_state if isinstance(symptom_state, dict) else {}
    patient_state_obj = patient_state if isinstance(patient_state, dict) else {}
    negatives_list = negatives if isinstance(negatives, list) else patient_state_obj.get("negatives", [])
    if not isinstance(negatives_list, list):
        negatives_list = []

    # Build prompt using stable v1 formatter
    prompt = generate_llm_prompt(
        age,
        gender,
        symptoms,
        symptom_state=state_obj,
        negatives=negatives_list,
        weight=weight,
        height=height,
        occupation=occupation,
        location=location,
        physical_activity=physical_activity,
        diet_type=diet_type,
    )

    # Check if model is available
    if not model_available or model is None:
        logger.warning("Model not available for disease mapping, using fallback")
        return _fallback_disease_mapping(symptoms)
    
    # Cache for speed
    key = _cache_key_for_prompt(prompt)
    cached = _prompt_cache.get(key)
    if cached is not None:
        _maybe_log("LLM RESPONSE (cache) =>", json.dumps(cached) if isinstance(cached, (dict, list)) else str(cached))
        return cached

    # Use centralized multi-key manager with robust JSON extraction
    try:
        success, text, error = generate_content_with_fallback(
            prompt=prompt,
            max_retries=None,  # try all available keys
            temperature=0.3,
            max_output_tokens=900,
        )
        if not success or not text:
            logger.error("Disease mapping generation failed: %s", error)
            return _fallback_disease_mapping(symptoms)
    except Exception as e:
        logger.error(f"Error generating disease mapping: {e}")
        return _fallback_disease_mapping(symptoms)

    _maybe_log("LLM RESPONSE =>", text)

    # Try to parse JSON response; fallback to deterministic mapping
    parsed = extract_json_from_text(text)
    if isinstance(parsed, dict):
        normalized = _normalize_mapping_result(parsed, symptoms)
        _prompt_cache[key] = normalized
        return normalized

    # Secondary parse attempt
    try:
        parsed = json.loads(text)
        normalized = _normalize_mapping_result(parsed, symptoms)
        _prompt_cache[key] = normalized
        return normalized
    except Exception:
        _prompt_cache[key] = _fallback_disease_mapping(symptoms)
        return _prompt_cache[key]
