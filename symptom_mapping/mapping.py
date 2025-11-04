import os
import json
import hashlib
import logging
from typing import Any, Dict, Optional
from dotenv import load_dotenv
load_dotenv()
import google.generativeai as genai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dual API key checking (GOOGLE_API_KEY or GEMINI_API_KEY)
google_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.0-flash"

# Model initialization with error handling
model_available = False
model = None

# Log API key status
if not google_api_key:
    logger.error("❌ GEMINI API KEY NOT FOUND for mapping.py!")
    logger.error("   Checked: GOOGLE_API_KEY and GEMINI_API_KEY")
    logger.error("   Please set in Backend/.env file")
else:
    logger.info("✅ Gemini API key loaded successfully (mapping.py)")
    logger.info(f"   Key prefix: {google_api_key[:10]}..." if len(google_api_key) > 10 else "   Key too short!")

# Attempt to configure and instantiate model
if google_api_key:
    try:
        genai.configure(api_key=google_api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        model_available = True
        logger.info(f"✅ Successfully connected to model: {MODEL_NAME} (mapping.py)")
    except Exception as e:
        logger.error(f"❌ Failed to instantiate model in mapping.py: {e}")
        logger.error("   Disease mapping may use fallback behavior")

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
        "conditions": conditions[:3],  # Top 3
        "follow_up_questions": [
            "How long have you had these symptoms?",
            "Have you taken any medication?",
            "Any other symptoms you've noticed?"
        ]
    }
    
    return json.dumps(result)



def generate_llm_prompt(age, gender, symptoms, chat_history, weight=None, height=None, occupation=None, location=None, physical_activity=None, diet_type=None):
    formatted_symptoms = ", ".join(symptoms)
    
    # Build comprehensive patient profile
    patient_profile = f"""
        Patient Details:
        - Age: {age} years
        - Gender: {gender}"""
    
    # Add physical measurements if available
    if weight and height:
        bmi = weight / ((height/100) ** 2)
        patient_profile += f"""
        - Weight: {weight} kg
        - Height: {height} cm
        - BMI: {bmi:.1f} ({"Underweight" if bmi < 18.5 else "Normal" if bmi < 25 else "Overweight" if bmi < 30 else "Obese"})"""
    elif weight:
        patient_profile += f"""
        - Weight: {weight} kg"""
    elif height:
        patient_profile += f"""
        - Height: {height} cm"""
    
    # Add lifestyle factors
    if occupation:
        patient_profile += f"""
        - Occupation: {occupation}"""
    
    if physical_activity:
        patient_profile += f"""
        - Physical Activity Level: {physical_activity.title()}"""
    
    if diet_type:
        diet_display = {
            "veg": "Vegetarian",
            "non_veg": "Non-Vegetarian",
            "vegan": "Vegan",
            "mixed": "Mixed"
        }.get(diet_type, diet_type.title())
        patient_profile += f"""
        - Diet Type: {diet_display}"""
    
    # Add location if available
    if location:
        location_str = []
        if location.get("city"):
            location_str.append(location["city"])
        if location.get("state"):
            location_str.append(location["state"])
        if location.get("country"):
            location_str.append(location["country"])
        if location_str:
            patient_profile += f"""
        - Location: {", ".join(location_str)}"""

    # Enhanced prompt with structured JSON response
    prompt = f"""
    You are a medical AI assistant analyzing patient data for early disease prediction and clinical reasoning.

    Patient Profile:
    {patient_profile}
    
    Reported Symptoms: {formatted_symptoms}

    Conversation History:
    {chat_history}

    Based on this comprehensive context, identify the top 3 likely medical conditions.
    For each, provide:
    - Name
    - Probability level (High / Moderate / Low)
    - Brief medical reasoning
    - Urgency (Emergency / Routine / Monitor)
    Also, suggest relevant follow-up questions to clarify diagnosis.

    Consider:
    - How the patient's BMI, activity level, and diet may influence their condition
    - Occupation-related health risks (e.g., desk job → sedentary issues, physical labor → musculoskeletal issues)
    - Location-specific diseases and environmental factors
    - Age and gender-specific conditions

    Respond strictly in JSON:
    {{
      "conditions": [
        {{"name": "...", "probability": "...", "reasoning": "...", "urgency": "..."}}
      ],
      "follow_up_questions": ["...", "..."]
    }}
    """

    # Log the prompt for verification (debug only)
    _maybe_log("LLM PROMPT =>", prompt)
    
    return prompt



def generate_llm_prompt_v2(
    age,
    gender,
    weight,
    height,
    occupation,
    activity,
    diet,
    country,
    state,
    city,
    symptoms,
    chat_history,
):
    formatted_symptoms = ", ".join(symptoms)

    # compute BMI if possible
    bmi_text = ""
    if weight and height:
        try:
            bmi_val = float(weight) / ((float(height) / 100.0) ** 2)
            bmi_cat = (
                "Underweight" if bmi_val < 18.5 else
                "Normal" if bmi_val < 25 else
                "Overweight" if bmi_val < 30 else
                "Obese"
            )
            bmi_text = f"\n    - BMI: {bmi_val:.1f} ({bmi_cat})"
        except Exception:
            bmi_text = ""

    prompt = f"""
    You are an expert clinical diagnostician performing differential diagnosis analysis. Your task is to synthesize ALL available patient data into a coherent clinical picture and rank the most likely conditions.

    Patient Profile:
    - Age: {age} years (consider age-related disease susceptibility, physiological changes, and epidemiology)
    - Gender: {gender} (consider gender-specific conditions and hormonal factors)
    - Weight: {weight} kg | Height: {height} cm{bmi_text}
    - Occupation: {occupation} (assess occupational hazards, stress, sedentary vs physical work)
    - Physical Activity: {activity} (evaluate cardiovascular fitness, metabolic health)
    - Diet: {diet} (consider nutritional deficiencies, metabolic disorders)
    - Geographic Location: {city}, {state}, {country}
      → Regional disease patterns, endemic infections, climate factors, pollution levels, healthcare access

    Reported Symptoms: {formatted_symptoms}

    Detailed Clinical History (Q&A Responses):
    {chat_history}

    CLINICAL REASONING APPROACH:
    1. **Pattern Recognition**: Analyze symptom constellation - which symptoms cluster together in known disease patterns?
    2. **Temporal Analysis**: Consider onset (acute vs gradual), duration, progression, timing patterns
    3. **Severity Assessment**: Evaluate symptom intensity and functional impact
    4. **Risk Stratification**: Factor in age, gender, BMI, lifestyle, occupation, and geographic risk factors
    5. **Differential Diagnosis**: Distinguish between competing diagnoses using discriminating clinical features
    6. **Likelihood Ranking**: Assign probability based on symptom match, prevalence, and patient-specific risk factors

    PROBABILITY ASSIGNMENT RULES:
    - **High**: ≥70% symptom match + strong supporting evidence from history + consistent with patient demographics
    - **Moderate**: 50-70% symptom match + some supporting evidence + plausible for patient profile
    - **Low**: <50% symptom match OR missing key features BUT still possible differential

    URGENCY CLASSIFICATION:
    - **Emergency**: Life-threatening symptoms, severe organ dysfunction, requires immediate medical attention
    - **Routine**: Stable symptoms, schedule appointment within 24-48 hours
    - **Monitor**: Mild symptoms, self-limiting conditions, observe and seek care if worsening

    TASK: Identify the TOP 3 most likely medical conditions based on comprehensive analysis of ALL available data.

    For each condition provide:
    1. **Name**: Specific disease/condition (use medical terminology but clear)
    2. **Probability**: High / Moderate / Low (based on clinical reasoning above)
    3. **Reasoning**: 2-3 sentences explaining WHY this diagnosis fits (cite specific symptoms, risk factors, clinical features)
    4. **Urgency**: Emergency / Routine / Monitor

    Also suggest 2-3 relevant follow-up questions that would help confirm or rule out the top diagnoses.

    RESPOND STRICTLY IN JSON FORMAT (no markdown, no extra text):
    {{
      "conditions": [
        {{"name": "...", "probability": "High/Moderate/Low", "reasoning": "Clinical reasoning with specific symptom references", "urgency": "Emergency/Routine/Monitor"}},
        {{"name": "...", "probability": "...", "reasoning": "...", "urgency": "..."}},
        {{"name": "...", "probability": "...", "reasoning": "...", "urgency": "..."}}
      ],
      "follow_up_questions": ["...", "...", "..."]
    }}
    """

    _maybe_log("LLM PROMPT (v2) =>", prompt)
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
    # Derive country/state/city safely from location dict
    country = (location or {}).get("country") if isinstance(location, dict) else None
    state = (location or {}).get("state") if isinstance(location, dict) else None
    city = (location or {}).get("city") if isinstance(location, dict) else None

    # Build prompt using v2 (explicit geo + age reasoning)
    prompt = generate_llm_prompt_v2(
        age,
        gender,
        weight,
        height,
        occupation,
        (physical_activity.title() if isinstance(physical_activity, str) else physical_activity),
        diet_type,
        country,
        state,
        city,
        symptoms,
        chat_history,
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

    # Synchronous model call (callers already use thread executors)
    try:
        response = model.generate_content(prompt)
        text = getattr(response, "text", "") or ""
    except Exception as e:
        logger.error(f"Error generating disease mapping: {e}")
        return _fallback_disease_mapping(symptoms)

    _maybe_log("LLM RESPONSE =>", text)

    # Try to parse JSON response; fallback to raw text
    try:
        parsed = json.loads(text)
        _prompt_cache[key] = parsed
        return parsed
    except Exception:
        _prompt_cache[key] = text
        return text