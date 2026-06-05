"""
Clinical Follow-Up Question Generator v3.0
===========================================

MAJOR CHANGE: Enforces 6-8 questions per session (not 1 question at a time).

This version generates 6-8 follow-up questions in a single API call to ensure:
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
import math
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
    logger.info(f"   Mode: 6-8 questions per session")
    logger.info("="*80)
else:
    logger.warning("="*80)
    logger.warning("⚠️ Gemini model not available for follow-up engine v3.0")
    logger.warning("   Fallback mode will be used")
    logger.warning("="*80)

def _extract_last_answer_v3(chat_history: Union[str, List, None]) -> str:
    """Extract latest user answer from chat history for better prompt grounding."""
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


def _format_history_v3(chat_history: Union[str, List, None]) -> str:
    """Compact Q/A formatter to keep prompts concise and useful."""
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


def _build_bmi_signal(weight: Optional[Union[int, float, str]], height: Optional[Union[int, float, str]]) -> str:
    """Safe BMI signal text for v3 prompts."""
    try:
        if weight is None or height is None:
            return "BMI not available"
        w = float(weight)
        h = float(height)
        if not math.isfinite(w) or not math.isfinite(h) or w <= 0 or h <= 0:
            return "BMI not available"
        if 0.5 <= h <= 2.5:
            h *= 100.0
        elif 36 <= h <= 96:
            h *= 2.54
        if not (20 <= w <= 400 and 90 <= h <= 250):
            return "BMI not available"
        bmi = w / ((h / 100.0) ** 2)
        if not math.isfinite(bmi) or bmi <= 0 or bmi > 80:
            return "BMI not available"
        bmi_cat = "Underweight" if bmi < 18.5 else "Normal" if bmi < 25 else "Overweight" if bmi < 30 else "Obese"
        return f"BMI: {bmi:.1f} ({bmi_cat})"
    except Exception:
        return "BMI not available"


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
    Build v3 prompt that ENFORCES 6-8 questions with strict clinical reasoning.
    """
    
    symptoms_str = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    latest_answer = _extract_last_answer_v3(chat_history)
    history_text = _format_history_v3(chat_history)
    
    # Build patient context
    patient_context = f"{age}-year-old {gender.lower()}"
    
    # Build patient profile
    profile_details = []
    
    profile_details.append(_build_bmi_signal(weight, height))
    
    profile_section = "\n".join([f"- {d}" for d in profile_details]) if profile_details else "- BMI not available"
    
    prompt = f"""You are a clinical reasoning engine. Language: English only.
Generate 6-8 high-value follow-up questions.
Goal: identify the top 2 most likely diseases with minimal questions.

Patient: {patient_context}
{profile_section}
Symptoms: {symptoms_str}
Latest patient answer: {latest_answer}
History:
{history_text}

Rules:
- 6-8 questions only.
- Use symptoms from patient form + latest patient answer + full chat history.
- Use BMI category as a supporting signal when available.
- If BMI is unavailable, continue with symptom/history evidence only.
- Each question must reduce uncertainty between the top 2 likely diseases.
- Do NOT repeat or paraphrase any question already asked in history.
- Red-flag questions first if relevant.
- Patient-friendly, short, one concept per question.

Return JSON only:
{{
  "follow_up_questions": [
    {{
      "id": 1,
      "question": "Short, targeted question",
      "priority": "red-flag | high | medium",
      "clinical_focus": "What this clarifies",
      "differentiates_between": ["Disease A", "Disease B"]
    }}
  ],
  "question_count": <number>,
  "top_differentials": ["Disease 1", "Disease 2"],
  "confidence_level": "low | medium | high",
  "reasoning_summary": "One short sentence"
}}
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
    Validate that response meets v3 requirements (6-8 questions).
    """
    if not isinstance(data, dict):
        return False
    
    # Must have follow_up_questions array
    if "follow_up_questions" not in data:
        return False
    
    questions = data["follow_up_questions"]
    
    # Must have 6-8 questions
    if not isinstance(questions, list) or not (6 <= len(questions) <= 8):
        logger.warning(f"Invalid question count: {len(questions) if isinstance(questions, list) else 0} (need 6-8)")
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
    Generate 6-8 fallback questions when API fails.
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
    
    # Ensure 6-8 questions
    questions = questions[:8]  # Cap at 8
    if len(questions) < 6:
        # Add simple, high-value screening questions if needed
        padding = [
            {
                "id": len(questions) + 1,
                "question": "Are you feeling unusually tired or weak?",
                "priority": "medium",
                "clinical_focus": "Assess systemic impact",
                "differentiates_between": ["Systemic illness", "Localized condition"]
            },
            {
                "id": len(questions) + 1,
                "question": "Have your symptoms stayed the same, worsened, or improved?",
                "priority": "medium",
                "clinical_focus": "Assess progression",
                "differentiates_between": ["Progressive condition", "Stable condition"]
            }
        ]
        for item in padding:
            if len(questions) >= 6:
                break
            questions.append(item)
    
    # Renumber to ensure sequential IDs
    for idx, q in enumerate(questions, 1):
        q["id"] = idx
    
    return {
        "follow_up_questions": questions,
        "question_count": len(questions),
        "top_differentials": ["Infectious disease", "Inflammatory condition"],
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
    Generate 6-8 follow-up questions using v3 clinical reasoning engine.
    
    Returns:
        Dict with follow_up_questions array (6-8 questions)
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
            max_output_tokens=1600  # Reduced tokens for 6-8 questions
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
    print(f"Expected: 6-8")
    print(f"Status: {'✅ PASS' if 6 <= len(test_result['follow_up_questions']) <= 8 else '❌ FAIL'}")
