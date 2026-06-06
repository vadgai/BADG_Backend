"""Tier-2 symptom-pattern fallback MCQs."""

from typing import Dict, List, Optional

from followup.agents.critic import QuestionCritic
from followup.fallbacks.contextual import _top2_from_state


def build_min_depth_question(
    patient_state: Dict,
    symptom_state: Dict,
    asked_questions: List[str],
) -> Optional[Dict]:
    current_symptoms = symptom_state.get("current_symptoms", []) if isinstance(symptom_state, dict) else []
    symptom_blob = " ".join(str(item).strip().lower() for item in current_symptoms if str(item).strip())
    if not symptom_blob and isinstance(patient_state, dict):
        symptom_blob = str(patient_state.get("chief_complaint", "")).strip().lower()

    top_two = _top2_from_state(patient_state)
    candidates = []

    if any(token in symptom_blob for token in ("abdominal", "stomach", "vomit", "diarrhea", "bowel")):
        candidates.append({
            "Question": "Which abdominal pattern is most prominent right now?",
            "A": "Pain is right-lower and worse with movement or coughing",
            "B": "Pain is diffuse with loose stools or repeated vomiting",
            "C": "Pain is upper-abdominal burning, often after meals",
            "D": "Cramping pain relieved after passing stool",
            "E": "None of these / Not sure",
            "feature_id": "abdominal_pattern",
        })
    if any(token in symptom_blob for token in ("cough", "breath", "chest", "wheeze", "phlegm")):
        candidates.append({
            "Question": "Which respiratory pattern best matches your current symptoms?",
            "A": "Breathlessness with chest tightness or wheeze episodes",
            "B": "Productive cough with yellow/green sputum and fever",
            "C": "Dry cough with throat irritation and minimal sputum",
            "D": "Sudden onset breathlessness without cough or sputum",
            "E": "None of these / Not sure",
            "feature_id": "respiratory_pattern",
        })
    if any(token in symptom_blob for token in ("headache", "dizziness", "weakness", "numb", "balance")):
        candidates.append({
            "Question": "Which neurological pattern is most noticeable now?",
            "A": "One-sided weakness/numbness or speech disturbance",
            "B": "Severe throbbing headache with light sensitivity",
            "C": "Spinning dizziness without focal weakness",
            "D": "Gradual memory or concentration difficulties",
            "E": "None of these / Not sure",
            "feature_id": "neurological_pattern",
        })

    candidates.append({
        "Question": "Which associated feature is most clearly present with your current symptoms?",
        "A": "Localized focal symptoms in one body area",
        "B": "Systemic features like fever, fatigue, or chills",
        "C": "Trigger-linked intermittent episodes",
        "D": "Symptoms worse at specific times (morning, night, after meals)",
        "E": "None of these / Not sure",
        "feature_id": "associated_pattern",
    })

    critic = QuestionCritic(symptom_state)
    for candidate in candidates:
        candidate.setdefault("priority", "high")
        candidate.setdefault(
            "clinical_intent",
            f"Differentiate {top_two[0]} vs {top_two[1]} with a non-repetitive clinical discriminator",
        )
        candidate.setdefault("differentiates_between", top_two[:2])
        candidate.setdefault("allow_other", True)
        candidate.setdefault("question_source", "deterministic")
        if critic.validate(candidate, asked_questions):
            return candidate
    return None
