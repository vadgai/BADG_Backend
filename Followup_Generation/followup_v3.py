"""
Clinical Follow-Up Question Generator v3.0
===========================================

MAJOR CHANGE: Enforces 7-10 questions per session (not 1 question at a time).

This version generates 7-10 follow-up questions in a single API call to ensure:
- Comprehensive clinical screening
- No generic/template questions
- Strict differential diagnosis approach
- Red-flag prioritization

Author: VADG Team
Date: January 26, 2026
Version: 3.0
"""

import os
import json
import logging
from typing import Dict, List, Union, Optional
from dotenv import load_dotenv

# Import centralized Gemini API manager
from utils.gemini_api_manager import (
    get_gemini_model,
    generate_content_with_fallback,
    MODEL_NAME
)

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check model availability
model_available, model = get_gemini_model()

if model_available:
    logger.info("="*80)
    logger.info(f"✅ Clinical Follow-up Engine v3.0 initialized with Gemini API")
    logger.info(f"   Model: {MODEL_NAME}")
    logger.info(f"   Mode: 7-10 questions per session")
    logger.info("="*80)
else:
    logger.warning("="*80)
    logger.warning("⚠️ Gemini model not available for follow-up engine v3.0")
    logger.warning("   Fallback mode will be used")
    logger.warning("="*80)


def _build_clinical_prompt_v3(
    age: int,
    gender: str,
    symptoms: Union[str, List],
    chat_history: str,
    weight: float = None,
    height: float = None,
    occupation: str = None,
    location: dict = None,
    physical_activity: str = None,
    diet_type: str = None,
) -> str:
    """
    Build v3 prompt that ENFORCES 7-10 questions with strict clinical reasoning.
    
    This prompt is designed to prevent generic questions and enforce
    differential diagnosis-driven questioning.
    """
    
    symptoms_str = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    
    # Build patient context
    patient_context = f"{age}-year-old {gender.lower()}"
    
    # Build patient profile
    profile_details = []
    
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
    
    profile_section = "\n".join([f"- {d}" for d in profile_details]) if profile_details else "- Limited demographic data"
    
    prompt = f"""You are a clinical reasoning engine for medical professionals, NOT a chatbot.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════
Generate 7–10 highly relevant follow-up questions based ONLY on the given patient symptoms.

═══════════════════════════════════════════════════════════════════════════════
PATIENT INFORMATION
═══════════════════════════════════════════════════════════════════════════════
Demographics: {patient_context}
{profile_section}

Presenting Symptoms: {symptoms_str}

Conversation History:
{chat_history if chat_history else "No previous questions asked - this is the initial assessment"}

═══════════════════════════════════════════════════════════════════════════════
ABSOLUTE RULES (NON-NEGOTIABLE)
═══════════════════════════════════════════════════════════════════════════════

1. You MUST generate BETWEEN 7 AND 10 questions in EVERY case.
   - Not 1 question. Not 5 questions. Between 7 and 10.
   - This is NON-NEGOTIABLE.

2. You are STRICTLY FORBIDDEN from using default or generic questions such as:
   - "Do you have any other symptoms?"
   - "How long have you been feeling this?"
   - "Any past medical history?"
   - "How are you feeling?"
   - "Is there anything else bothering you?"
   
3. Each question MUST be clinically meaningful and reduce diagnostic uncertainty.
   - Every question should help differentiate between specific conditions.
   - Questions should target missing clinical information.

4. Questions must be DIFFERENTIAL-DRIVEN, not symptom-collection driven.
   - Start by identifying 2-3 most likely diagnoses.
   - Ask questions that differentiate between them.

5. If red-flag symptoms are suspected, PRIORITIZE those questions first.
   - Life-threatening conditions take priority.
   - Urgent indicators come before routine questions.

6. You MUST NOT output diagnosis, explanations, or advice.
   - Output ONLY the JSON structure.
   - No commentary outside the JSON.

7. You MUST NOT return an empty list under ANY condition.
   - Even if symptoms are vague, generate questions.
   - Even if diagnosis seems obvious, generate questions.

═══════════════════════════════════════════════════════════════════════════════
REASONING STRATEGY (INTERNAL – DO NOT OUTPUT THIS)
═══════════════════════════════════════════════════════════════════════════════

Step 1: DIFFERENTIAL DIAGNOSIS
- Analyze all symptoms as a constellation
- Consider patient demographics (age, gender, location)
- Identify the top 2–3 most likely conditions

Step 2: GAP ANALYSIS
- What clinical information is MISSING?
- What features would differentiate between your top diagnoses?
- Prioritize:
  1. RED FLAGS (life-threatening signs)
  2. PATHOGNOMONIC features (disease-specific symptoms)
  3. TEMPORAL patterns (onset, duration, progression)
  4. SEVERITY indicators (functional impact)
  5. ASSOCIATED symptoms
  6. RISK FACTORS and exposures

Step 3: QUESTION GENERATION
- Generate 7-10 questions that address the gaps identified above
- Order by priority (red flags first)
- Ensure each question reduces diagnostic uncertainty

═══════════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT (STRICT JSON ONLY)
═══════════════════════════════════════════════════════════════════════════════

{{
  "follow_up_questions": [
    {{
      "id": 1,
      "question": "Specific, targeted clinical question in patient-friendly language",
      "priority": "red-flag | high | medium",
      "clinical_focus": "What this question is trying to confirm or rule out",
      "differentiates_between": ["Disease A", "Disease B"]
    }},
    {{
      "id": 2,
      "question": "Second question...",
      "priority": "high | medium",
      "clinical_focus": "...",
      "differentiates_between": ["...", "..."]
    }}
    // ... continue for 7-10 questions total
  ],
  "question_count": 7-10,
  "top_differentials": ["Disease 1", "Disease 2", "Disease 3"],
  "confidence_level": "low | medium | high",
  "reasoning_summary": "One sentence explaining your differential diagnosis approach"
}}

CRITICAL REQUIREMENTS:
- The "follow_up_questions" array MUST contain 7-10 items
- Each question MUST have all required fields (id, question, priority, clinical_focus, differentiates_between)
- Questions MUST be ordered by priority (red-flag first, then high, then medium)
- The "question_count" field MUST match the actual number of questions
- The "top_differentials" array MUST list 2-3 specific disease names

═══════════════════════════════════════════════════════════════════════════════
FAILSAFE ENFORCEMENT
═══════════════════════════════════════════════════════════════════════════════

- If you are unsure, STILL generate 7–10 questions.
- If symptoms are minimal (e.g., just "fever"), generate broad screening questions:
  * Respiratory symptoms (cough, sputum, dyspnea)
  * GI symptoms (nausea, vomiting, diarrhea)
  * Neurological symptoms (headache, confusion, stiff neck)
  * Urinary symptoms (dysuria, frequency, hematuria)
  * Severity and functional impact
  * Temporal patterns
  * Red flag screening

- If symptoms are clear (e.g., "crushing chest pain"), generate targeted questions:
  * All relevant red flags for suspected condition
  * Differentiating features from similar conditions
  * Severity assessment
  * Contraindications to treatment
  * Risk factors
  * Associated symptoms

- NEVER reuse default or template questions.
- NEVER ask questions already answered in chat history.

═══════════════════════════════════════════════════════════════════════════════
EXAMPLES OF GOOD QUESTIONS (for reference only)
═══════════════════════════════════════════════════════════════════════════════

For "headache":
✓ "Do you have a stiff neck, fever, or sensitivity to light?" (RED FLAG - meningitis)
✓ "Is the pain throbbing and on one side of your head?" (PATHOGNOMONIC - migraine)
✓ "Does the pain worsen with physical activity or movement?" (DISCRIMINATING)
✓ "Do you see flashing lights or zigzag lines before the pain?" (AURA - migraine)

For "chest pain":
✓ "Does the pain radiate to your left arm, jaw, or back?" (RED FLAG - MI)
✓ "Is the pain crushing or squeezing in nature?" (CHARACTERISTIC - MI)
✓ "Does the pain worsen with deep breathing or movement?" (DISCRIMINATING - pleuritic vs cardiac)
✓ "Are you sweating or feeling nauseous?" (ASSOCIATED - MI)

═══════════════════════════════════════════════════════════════════════════════
BEGIN
═══════════════════════════════════════════════════════════════════════════════

Output ONLY valid JSON. No markdown, no explanations, no commentary.
Start your response with {{ and end with }}.
"""
    
    return prompt


def _parse_json_response_v3(response_text: str) -> Optional[Dict]:
    """
    Parse JSON response from Gemini, handling various formats.
    """
    if not response_text:
        return None
    
    try:
        # Try direct parse first
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code blocks
    import re
    
    # Remove markdown code fences
    cleaned = re.sub(r'```json\s*', '', response_text)
    cleaned = re.sub(r'```\s*', '', cleaned)
    cleaned = cleaned.strip()
    
    # Try to find JSON object
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    
    if start != -1 and end != -1:
        json_str = cleaned[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    return None


def _validate_v3_response(data: Dict) -> bool:
    """
    Validate that response meets v3 requirements (7-10 questions).
    """
    if not isinstance(data, dict):
        return False
    
    # Must have follow_up_questions array
    if "follow_up_questions" not in data:
        return False
    
    questions = data["follow_up_questions"]
    
    # Must have 7-10 questions
    if not isinstance(questions, list) or not (7 <= len(questions) <= 10):
        logger.warning(f"Invalid question count: {len(questions) if isinstance(questions, list) else 0} (need 7-10)")
        return False
    
    # Each question must have required fields
    for q in questions:
        if not all(k in q for k in ["id", "question", "priority", "clinical_focus"]):
            logger.warning(f"Question {q.get('id')} missing required fields")
            return False
    
    return True


def _generate_fallback_questions_v3(
    symptoms: Union[str, List],
    age: int,
    gender: str
) -> Dict:
    """
    Generate 7-10 fallback questions when API fails.
    These are high-quality clinical questions based on symptom patterns.
    """
    
    symptoms_str = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    symptoms_lower = symptoms_str.lower()
    
    questions = []
    
    # Always include red flag screening (questions 1-2)
    questions.extend([
        {
            "id": 1,
            "question": "Are you experiencing severe difficulty breathing, chest pain, or loss of consciousness?",
            "priority": "red-flag",
            "clinical_focus": "Screen for immediately life-threatening conditions",
            "differentiates_between": ["Medical emergency", "Non-urgent condition"]
        },
        {
            "id": 2,
            "question": "Have you noticed any sudden weakness, numbness, or difficulty speaking?",
            "priority": "red-flag",
            "clinical_focus": "Screen for stroke or neurological emergency",
            "differentiates_between": ["Stroke/TIA", "Benign neurological symptoms"]
        }
    ])
    
    # Pattern-based questions (questions 3-7)
    if any(word in symptoms_lower for word in ["fever", "temperature", "hot"]):
        questions.extend([
            {
                "id": 3,
                "question": "Do you have a cough, shortness of breath, or chest discomfort?",
                "priority": "high",
                "clinical_focus": "Screen for respiratory infection",
                "differentiates_between": ["Pneumonia", "Upper respiratory infection", "COVID-19"]
            },
            {
                "id": 4,
                "question": "Are you experiencing nausea, vomiting, diarrhea, or abdominal pain?",
                "priority": "high",
                "clinical_focus": "Screen for GI infection",
                "differentiates_between": ["Gastroenteritis", "Food poisoning", "Appendicitis"]
            },
            {
                "id": 5,
                "question": "Do you have painful or frequent urination, or back pain?",
                "priority": "high",
                "clinical_focus": "Screen for urinary tract infection",
                "differentiates_between": ["UTI", "Pyelonephritis", "Other causes"]
            }
        ])
    
    if any(word in symptoms_lower for word in ["pain", "ache", "hurt"]):
        questions.extend([
            {
                "id": len(questions) + 1,
                "question": "On a scale of 1-10, how severe is your pain?",
                "priority": "high",
                "clinical_focus": "Assess pain severity",
                "differentiates_between": ["Mild condition", "Moderate condition", "Severe condition"]
            },
            {
                "id": len(questions) + 2,
                "question": "Is the pain constant or does it come and go?",
                "priority": "high",
                "clinical_focus": "Characterize temporal pattern",
                "differentiates_between": ["Chronic condition", "Acute condition", "Intermittent condition"]
            }
        ])
    
    if any(word in symptoms_lower for word in ["cough", "respiratory", "breath"]):
        questions.extend([
            {
                "id": len(questions) + 1,
                "question": "Are you coughing up any phlegm or blood?",
                "priority": "high",
                "clinical_focus": "Characterize cough",
                "differentiates_between": ["Productive infection", "Dry cough", "Hemoptysis"]
            }
        ])
    
    # Add severity and functional questions (questions 6-8)
    questions.extend([
        {
            "id": len(questions) + 1,
            "question": "How long have you been experiencing these symptoms?",
            "priority": "medium",
            "clinical_focus": "Establish timeline",
            "differentiates_between": ["Acute condition", "Subacute condition", "Chronic condition"]
        },
        {
            "id": len(questions) + 2,
            "question": "Are your symptoms getting worse, staying the same, or improving?",
            "priority": "medium",
            "clinical_focus": "Assess progression",
            "differentiates_between": ["Progressive condition", "Stable condition", "Resolving condition"]
        },
        {
            "id": len(questions) + 3,
            "question": "Are your symptoms preventing you from working or doing daily activities?",
            "priority": "medium",
            "clinical_focus": "Assess functional impact",
            "differentiates_between": ["Severe functional impairment", "Mild impairment", "No impairment"]
        }
    ])
    
    # Add risk factor questions (questions 9-10)
    questions.extend([
        {
            "id": len(questions) + 1,
            "question": "Do you have any chronic medical conditions like diabetes, heart disease, or lung disease?",
            "priority": "medium",
            "clinical_focus": "Identify comorbidities",
            "differentiates_between": ["High-risk patient", "Low-risk patient"]
        },
        {
            "id": len(questions) + 2,
            "question": "Have you recently traveled, been exposed to sick individuals, or experienced similar symptoms before?",
            "priority": "medium",
            "clinical_focus": "Identify exposures and history",
            "differentiates_between": ["Travel-related illness", "Exposure-related illness", "Recurrent condition"]
        }
    ])
    
    # Ensure exactly 7-10 questions
    questions = questions[:10]  # Cap at 10
    
    # Renumber to ensure sequential IDs
    for idx, q in enumerate(questions, 1):
        q["id"] = idx
    
    return {
        "follow_up_questions": questions,
        "question_count": len(questions),
        "top_differentials": ["Infectious disease", "Inflammatory condition", "Acute illness"],
        "confidence_level": "low",
        "reasoning_summary": "Fallback questions generated due to API unavailability"
    }


def get_followup_for_diagnosis_v3(
    age: int,
    gender: str,
    symptoms: Union[str, list],
    chat_history: str = "",
    weight: float = None,
    height: float = None,
    occupation: str = None,
    location: dict = None,
    physical_activity: str = None,
    diet_type: str = None,
) -> Dict:
    """
    Generate 7-10 follow-up questions using v3 clinical reasoning engine.
    
    Returns:
        Dict with follow_up_questions array (7-10 questions)
        NEVER returns None or empty array
    """
    
    logger.info("="*80)
    logger.info("Starting Follow-Up Question Generation v3.0")
    logger.info(f"Patient: {age}yo {gender}, Symptoms: {symptoms}")
    logger.info("="*80)
    
    # Build prompt
    prompt = _build_clinical_prompt_v3(
        age=age,
        gender=gender,
        symptoms=symptoms,
        chat_history=chat_history,
        weight=weight,
        height=height,
        occupation=occupation,
        location=location,
        physical_activity=physical_activity,
        diet_type=diet_type
    )
    
    # Try Gemini API
    model_ok, _ = get_gemini_model()
    
    if model_ok:
        logger.info("Attempting generation with Gemini API...")
        
        success, response, error = generate_content_with_fallback(
            prompt=prompt,
            temperature=0.3,
            max_output_tokens=3000  # Need more tokens for 7-10 questions
        )
        
        if success and response:
            logger.info(f"Received response from Gemini ({len(response)} chars)")
            
            # Parse JSON
            data = _parse_json_response_v3(response)
            
            if data and _validate_v3_response(data):
                logger.info(f"✅ Successfully generated {len(data['follow_up_questions'])} questions")
                return data
            else:
                logger.warning("Failed to parse or validate Gemini response. Using fallback.")
        else:
            logger.warning(f"Gemini API failed: {error}. Using fallback.")
    else:
        logger.warning("Gemini API not available. Using fallback.")
    
    # Fallback: Generate high-quality clinical questions
    logger.info("Generating fallback questions...")
    fallback_response = _generate_fallback_questions_v3(symptoms, age, gender)
    logger.info(f"✅ Generated {len(fallback_response['follow_up_questions'])} fallback questions")
    
    return fallback_response


# Alias for backward compatibility
get_followup_for_diagnosis = get_followup_for_diagnosis_v3


if __name__ == "__main__":
    # Test the v3 engine
    print("="*80)
    print("Testing Clinical Follow-Up Question Generator v3.0")
    print("="*80)
    
    test_result = get_followup_for_diagnosis_v3(
        age=35,
        gender="Female",
        symptoms=["fever", "headache", "body ache"],
        chat_history=""
    )
    
    print("\nResult:")
    print(json.dumps(test_result, indent=2))
    print("\nValidation:")
    print(f"Question count: {len(test_result['follow_up_questions'])}")
    print(f"Expected: 7-10")
    print(f"Status: {'✅ PASS' if 7 <= len(test_result['follow_up_questions']) <= 10 else '❌ FAIL'}")
