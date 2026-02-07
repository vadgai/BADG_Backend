# Backend/Followup_Generation/followup_v2.py
"""
CLINICAL FOLLOW-UP QUESTION ENGINE v2.0
Enhanced version with guaranteed question generation and clinical reasoning.
"""

import os
import json
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
        return {
            "Question": first_q.get("question", ""),
            "A": first_q.get("options", {}).get("A", "Option A"),
            "B": first_q.get("options", {}).get("B", "Option B"),
            "C": first_q.get("options", {}).get("C", "Option C"),
            "D": "None of these",
            "clinical_purpose": first_q.get("clinical_purpose", ""),
            "differentiates_between": first_q.get("differentiates_between", [])
        }
    return data


# ==================== IMPROVED CLINICAL PROMPT ====================

def _build_clinical_prompt(
    age: int,
    gender: str,
    symptoms: Union[str, List],
    chat_history: str,
    question_count: int,
    max_questions: int = 10,
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
    
    # Build patient profile with available data
    profile_details = []
    
    # BMI calculation (only if both weight and height available)
    if weight and height:
        try:
            bmi = float(weight) / ((float(height) / 100) ** 2)
            if bmi > 0:
                bmi_cat = "Underweight" if bmi < 18.5 else "Normal" if bmi < 25 else "Overweight" if bmi < 30 else "Obese"
                profile_details.append(f"BMI: {bmi:.1f} ({bmi_cat})")
        except:
            pass
    
    if occupation:
        profile_details.append(f"Occupation: {occupation}")
    if physical_activity:
        profile_details.append(f"Physical Activity: {physical_activity}")
    if diet_type:
        profile_details.append(f"Diet: {diet_type}")
    if location and isinstance(location, dict):
        loc_parts = [location.get("city"), location.get("state"), location.get("country")]
        loc_str = ", ".join([p for p in loc_parts if p])
        if loc_str:
            profile_details.append(f"Location: {loc_str}")
    
    profile_section = "\n".join([f"  - {d}" for d in profile_details]) if profile_details else "  - Limited demographic data"
    
    # Calculate confidence indicator
    questions_answered = question_count
    confidence_indicator = "LOW" if questions_answered < 3 else "MEDIUM" if questions_answered < 7 else "HIGH"
    
    prompt = f"""You are a CLINICAL AI DIAGNOSTIC ASSISTANT conducting a systematic medical interview.

═══════════════════════════════════════════════════════════════════════════════
PATIENT PROFILE
═══════════════════════════════════════════════════════════════════════════════
• Demographics: {patient_context}
{profile_section}

PRESENTING SYMPTOMS: {symptoms_str}

CONVERSATION HISTORY:
{chat_history if chat_history else "No previous questions asked"}

PROGRESS: Question {question_count + 1} of {max_questions} | Confidence: {confidence_indicator}

═══════════════════════════════════════════════════════════════════════════════
CLINICAL REASONING PROTOCOL
═══════════════════════════════════════════════════════════════════════════════

STEP 1: DIFFERENTIAL DIAGNOSIS ANALYSIS
▸ Analyze ALL symptoms and answers as a constellation
▸ Identify TOP 3 most probable diseases based on:
  - Symptom pattern matching
  - Demographics (age, gender, location)
  - Risk factors (BMI, occupation, lifestyle)
  - Temporal patterns from history

STEP 2: DISCRIMINATING FEATURE IDENTIFICATION
▸ What SINGLE clinical feature would best differentiate between your top 3 diagnoses?
▸ Priority order for questions:
  1. RED FLAGS (life-threatening signs) - ALWAYS ask if not ruled out
  2. PATHOGNOMONIC features (disease-specific symptoms)
  3. Temporal patterns (onset, duration, progression)
  4. Severity indicators (functional impact)
  5. Associated symptoms (constellation patterns)
  6. Risk factors and exposures

STEP 3: DECISION POINT
▸ IF confidence is HIGH (≥7 questions) AND you can differentiate top diagnoses → Return: {{"ready_for_diagnosis": true}}
▸ IF confidence is LOW/MEDIUM OR critical differentiating info missing → Generate targeted question
▸ IF reached question limit ({max_questions}) → Return: {{"ready_for_diagnosis": true}}

═══════════════════════════════════════════════════════════════════════════════
QUESTION QUALITY STANDARDS
═══════════════════════════════════════════════════════════════════════════════

✓ GOOD QUESTIONS (specific, discriminating):
  • "Does the headache worsen when bending forward or lying flat?"
    → Differentiates: Sinusitis vs Migraine vs Intracranial pressure
  • "Is there blood or coffee-ground material in vomit?"
    → Differentiates: GI bleeding vs Gastritis vs Food poisoning
  • "Does the pain radiate to the left arm or jaw?"
    → Differentiates: Cardiac ischemia vs Musculoskeletal pain

✗ BAD QUESTIONS (vague, already answered):
  • "Any other symptoms?" - TOO VAGUE
  • "How are you feeling?" - NON-DISCRIMINATING
  • Questions already answered in chat history - REDUNDANT

═══════════════════════════════════════════════════════════════════════════════
MANDATORY OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

IF CONTINUING INTERVIEW (default for questions {question_count + 1} < {max_questions}):
{{
  "follow_up_questions": [
    {{
      "id": {question_count + 1},
      "question": "Clear, patient-friendly question in simple language",
      "clinical_purpose": "Brief explanation of what this determines",
      "differentiates_between": ["Disease A", "Disease B", "Disease C"],
      "red_flag_assessment": true/false,
      "options": {{
        "A": "Option pointing toward Disease A presentation",
        "B": "Option pointing toward Disease B presentation",
        "C": "Option pointing toward Disease C or other presentation",
        "D": "None of these"
      }}
    }}
  ],
  "confidence_level": "low|medium|high",
  "top_differentials": ["Disease 1", "Disease 2", "Disease 3"],
  "ready_for_diagnosis": false
}}

IF READY FOR DIAGNOSIS (only if confidence HIGH and sufficient data):
{{
  "ready_for_diagnosis": true,
  "confidence_level": "high",
  "questions_answered": {question_count},
  "top_differentials": ["Most likely disease", "Second likely", "Third likely"]
}}

═══════════════════════════════════════════════════════════════════════════════
CRITICAL REQUIREMENTS
═══════════════════════════════════════════════════════════════════════════════
1. MUST return valid JSON (no markdown, no explanations outside JSON)
2. MUST NOT return empty arrays - always generate at least 1 question OR ready_for_diagnosis
3. MUST NOT ask questions already answered in chat history
4. MUST ensure Option D is always "None of these"
5. MUST base questions on clinical reasoning, not random inquiry
6. MUST consider patient demographics and context in question selection

═══════════════════════════════════════════════════════════════════════════════
NOW: Apply clinical reasoning and generate your response as JSON only.
═══════════════════════════════════════════════════════════════════════════════
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
    
    # Count existing questions
    question_count = 0
    if chat_history:
        question_count = chat_history.count("Question:") + chat_history.count("Q:")
    
    max_questions = 10
    
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
            max_output_tokens=1500,
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
