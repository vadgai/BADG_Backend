"""
Prompt templates for symptom signal extraction and next-question generation.
"""

from typing import Any, Dict, List


def build_signal_extraction_prompt(
    current_state: Dict[str, Any],
    patient_response: str
) -> str:
    return f"""You are a medical NLP expert. Extract ONLY clinically relevant information from this patient response.

Current known symptoms: {current_state.get('current_symptoms', [])}
Current modifiers: {current_state.get('modifiers', [])}
Current red flags: {current_state.get('red_flags', [])}

Patient's latest response: "{patient_response}"

Extract and return ONLY:
1. New symptoms (medical terms only)
2. Modifiers (severity, duration, triggers, location, character)
3. Red flags (alarming symptoms requiring immediate attention)

Return STRICT JSON format:
{{
  "new_symptoms": ["symptom1", "symptom2"],
  "new_modifiers": ["modifier1"],
  "red_flags": ["flag1"],
  "clinical_value": true/false
}}

If response contains NO new clinical information, return {{"clinical_value": false}}.
NO explanations. ONLY JSON."""


def build_next_question_prompt(
    age: int,
    gender: str,
    symptom_state: Dict[str, Any],
    questions_asked: List[str]
) -> str:
    questions_text = "\n".join(questions_asked) if questions_asked else "None"
    return f"""You are a medical diagnosis expert. Generate ONE highly specific follow-up question.

Patient: {age}-year-old {gender}

Current Clinical State:
- Symptoms: {symptom_state.get('current_symptoms', [])}
- Modifiers: {symptom_state.get('modifiers', [])}
- Red Flags: {symptom_state.get('red_flags', [])}
- Questions Already Asked: {len(questions_asked)}

Questions previously covered:
{questions_text}

Task:
1. Infer TOP 2 most likely diseases based on current state
2. Generate ONE question that differentiates between them
3. Prioritize red flags if present
4. DO NOT repeat previous questions
5. DO NOT ask generic questions

If you have enough information (minimum 7 questions asked and clear diagnosis), return:
{{"ready_for_diagnosis": true}}

Otherwise, return STRICT JSON format:
{{
  "Question": "Specific, targeted question based on symptoms",
  "A": "Option A",
  "B": "Option B", 
  "C": "Option C",
  "D": "None of these",
  "priority": "red-flag | high | medium",
  "clinical_intent": "What this question distinguishes",
  "differentiates_between": ["Disease A", "Disease B"]
}}

NO explanations. ONLY JSON."""
