import os
import json
import hashlib
import logging
from typing import Any, Dict, Optional
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

def _fallback_disease_mapping(symptoms):
    """
    Fallback disease mapping when AI is unavailable.
    Returns basic mapping based on common symptom patterns.
    """
    symptom_str = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    symptom_lower = symptom_str.lower()
    
    # Basic symptom-to-disease mapping
    conditions = []
    
    if any(s in symptom_lower for s in ["fever", "temperature", "hot"]):
        conditions.append({"name": "Viral infection", "probability": "Moderate", "reasoning": "Fever is a common symptom", "urgency": "Monitor"})
    
    if any(s in symptom_lower for s in ["cough", "phlegm", "chest"]):
        conditions.append({"name": "Respiratory infection", "probability": "Moderate", "reasoning": "Respiratory symptoms present", "urgency": "Monitor"})
    
    if any(s in symptom_lower for s in ["headache", "head pain"]):
        conditions.append({"name": "Tension headache", "probability": "Moderate", "reasoning": "Headache reported", "urgency": "Routine"})
    
    if not conditions:
        conditions.append({"name": "General malaise", "probability": "Low", "reasoning": "Non-specific symptoms", "urgency": "Monitor"})
    
    result = {
        "conditions": conditions[:2]  # Top 2
    }

    return result


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



def generate_llm_prompt(age, gender, symptoms, chat_history, weight=None, height=None, occupation=None, location=None, physical_activity=None, diet_type=None):
    formatted_symptoms = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    chat_history_text = _format_chat_history(chat_history)

    prompt = f"""
        You are a highly experienced medical diagnosis doctor.

        Patient:
        - Age: {age}
        - Gender: {gender}

        Symptoms: {formatted_symptoms}

        Chat History:
        {chat_history_text}

        Based on all the above, list the top 3 most likely medical conditions or diseases this patient may have. For each, provide:
        - Condition name
        - One-line reasoning (based on symptoms + answers)
        - Urgency level: (Low / Moderate / High)

        Make sure your answer is formatted clearly.
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
):
    # Build prompt using stable v1 formatter
    prompt = generate_llm_prompt(
        age,
        gender,
        symptoms,
        chat_history,
        weight,
        height,
        occupation,
        location,
        physical_activity,
        diet_type,
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
            max_output_tokens=1500,
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
        _prompt_cache[key] = parsed
        return parsed

    # Secondary parse attempt
    try:
        parsed = json.loads(text)
        _prompt_cache[key] = parsed
        return parsed
    except Exception:
        _prompt_cache[key] = _fallback_disease_mapping(symptoms)
        return _prompt_cache[key]
