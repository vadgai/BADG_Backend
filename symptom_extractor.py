"""
Prompt templates for symptom signal extraction and next-question generation.
"""

from typing import Any, Dict, List


def build_signal_extraction_prompt(
    current_state: Dict[str, Any],
    patient_response: str,
    last_question_text: str = None
) -> str:
    last_q = last_question_text or current_state.get("last_question_text") or current_state.get("last_question") or "None"
    modifier_map = current_state.get("modifier_map") if isinstance(current_state.get("modifier_map"), dict) else {}

    # Fix K: add differential and red flags for context-aware extraction
    differential = current_state.get("differential_diagnosis") if isinstance(current_state.get("differential_diagnosis"), list) else []
    diff_text = ""
    if differential:
        diff_names = [str(d.get("name", "")).strip() for d in differential[:3] if isinstance(d, dict) and d.get("name")]
        if diff_names:
            diff_text = f"\n- Current Top Suspects (differential): {', '.join(diff_names)}"

    red_flags = current_state.get("red_flags") if isinstance(current_state.get("red_flags"), list) else []
    red_flags_text = ""
    if red_flags:
        red_flags_text = f"\n- Known Red Flags: {', '.join(str(r).strip() for r in red_flags if str(r).strip())}"

    return f"""Medical scribe. Extract clinical signals from the patient answer. JSON only.

CONTEXT:
- Current symptoms: {current_state.get('current_symptoms', [])}
- Modifier map: {modifier_map}{diff_text}{red_flags_text}
- Last question: "{last_q}"
- Patient answer: "{patient_response}"

RULES:
1. NORMALIZE to short clinical terms only ("weight lost"->"weight loss", "stomach hurts"->"abdominal pain"). Never store the question text or a full sentence as a finding.
2. NEGATIVES: if the patient denies the last question, add its topic to new_negative_findings.
3. RED FLAGS: capture life-threatening mentions (chest pain, loss of consciousness, severe breathing difficulty, etc.).
4. MODIFIERS: fill any present among duration, onset, location, quality, severity, aggravating_factors, relieving_factors, associated_symptoms.
5. NO HALLUCINATION: only findings explicitly stated in the answer.
6. Use the Top Suspects to judge which positives are diagnostically meaningful.

OUTPUT JSON ONLY:
{{
  "new_positive_findings": ["term1", "term2"],
  "new_negative_findings": ["term1"],
  "red_flags_detected": [],
  "modifier_map": {{
    "duration": "",
    "onset": "",
    "location": "",
    "quality": "",
    "severity": "",
    "aggravating_factors": [],
    "relieving_factors": [],
    "associated_symptoms": []
  }},
  "clinical_utility": true
}}"""


def build_next_question_prompt(
    age: int,
    gender: str,
    symptom_state: Dict[str, Any],
    questions_asked: List[str]
) -> str:
    questions_text = "\n".join(questions_asked) if questions_asked else "None"
    question_count = len(questions_asked)
    return f"""ACT: Senior Clinical Consultant (Symptom-Driven Mode).
GOAL: Generate ONE differentiating MCQ using structured symptom state only.

CONTEXT:
- Patient: {age}yo {gender}
- Confirmed Symptoms (+): {symptom_state.get('current_symptoms', [])}
- Modifiers: {symptom_state.get('modifiers', [])}
- Modifier Map: {symptom_state.get('modifier_map', {})}
- Red Flags: {symptom_state.get('red_flags', [])}
- Questions Already Asked: {question_count}
- Previously Asked Questions:
{questions_text}

STRICT RULES:
1. Use ONLY structured state above; do not use raw chat history or free-form assumptions.
2. Infer TOP 2 competing diseases from (+), modifiers, red flags, and demographics.
3. Ask ONE targeted differentiator question only (non-repetitive).
4. Prioritize red-flag differentiation whenever red flags are present.
5. Never use placeholder/template wording in the question or options.
6. Never ask generic filler/progression checks unless required by red-flag differentiation.
7. If evidence is limited, ask the single highest-value differentiator linked to known symptoms (not a generic progression question).
8. The question must test a concrete differentiator feature between top-2 conditions.
9. If question_count >= 10 OR (question_count >= 7 and diagnosis is sufficiently certain), return:
{{"ready_for_diagnosis": true}}

OUTPUT JSON ONLY:
{{
  "Question": "Is abdominal pain localized to the right lower side and worse with movement?",
  "A": "Yes, localized right-lower pain worsens while walking/coughing",
  "B": "No, pain is diffuse with loose stools or vomiting",
  "C": "No, pain is mainly upper-abdominal burning after meals",
  "D": "None of these",
  "priority": "red-flag|high|medium",
  "clinical_intent": "What this differentiates",
  "differentiates_between": ["Appendicitis", "Gastroenteritis"],
  "feature_id": "feature_key"
}}"""
