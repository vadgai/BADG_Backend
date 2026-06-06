"""Tier-3 turn-indexed clinical dimension templates."""

from typing import Dict, List, Optional

from followup.agents.critic import QuestionCritic
from followup.fallbacks.contextual import _top2_from_state


def _turn_templates(chief: str) -> List[Dict]:
    return [
        {
            "Question": f"How long have you had {chief}?",
            "A": "Less than 24 hours", "B": "1 to 3 days", "C": "4 to 7 days",
            "D": "More than 1 week", "E": "None of these / Not sure", "feature_id": "duration",
        },
        {
            "Question": f"How did your {chief} start?",
            "A": "Suddenly over minutes to hours", "B": "Gradually over several days",
            "C": "Intermittent episodes that come and go", "D": "Constant since it began",
            "E": "None of these / Not sure", "feature_id": "onset",
        },
        {
            "Question": f"How severe is your {chief} right now?",
            "A": "Mild — noticeable but not limiting daily activity",
            "B": "Moderate — interferes with normal activity",
            "C": "Severe — hard to function normally",
            "D": "Worst at specific times of day only",
            "E": "None of these / Not sure", "feature_id": "severity",
        },
        {
            "Question": "Which factor most clearly worsens your symptoms?",
            "A": "Physical activity or exertion", "B": "Eating, fasting, or specific foods",
            "C": "Stress, poor sleep, or fatigue", "D": "No clear trigger — symptoms are constant",
            "E": "None of these / Not sure", "feature_id": "aggravating_factor",
        },
        {
            "Question": "Have you noticed any of these associated features?",
            "A": "Fever, chills, or night sweats", "B": "Nausea, vomiting, or appetite loss",
            "C": "Breathlessness or chest discomfort", "D": "No associated features beyond main symptoms",
            "E": "None of these / Not sure", "feature_id": "associated_features",
        },
        {
            "Question": "Have you tried any treatment since symptoms began?",
            "A": "Over-the-counter medicines with some relief", "B": "Over-the-counter medicines with no relief",
            "C": "Prescription medicines from a doctor", "D": "No treatment tried yet",
            "E": "None of these / Not sure", "feature_id": "treatment_trial",
        },
        {
            "Question": "Have you had similar episodes before?",
            "A": "Yes, similar episodes in the past", "B": "No, this is the first time",
            "C": "Unsure — possibly mild episodes before", "D": "Yes, but this episode feels clearly worse",
            "E": "None of these / Not sure", "feature_id": "prior_episodes",
        },
        {
            "Question": "Which red-flag pattern is most relevant for you now?",
            "A": "Sudden severe worsening or confusion", "B": "Difficulty breathing or chest pain",
            "C": "Persistent high fever or rigors", "D": "None of these red flags",
            "E": "None of these / Not sure", "feature_id": "red_flag_screen",
        },
        {
            "Question": "How are your symptoms affecting daily function?",
            "A": "Can work/perform daily tasks with mild discomfort",
            "B": "Need rest but can manage basic tasks",
            "C": "Mostly bed-bound or unable to work",
            "D": "Symptoms fluctuate through the day",
            "E": "None of these / Not sure", "feature_id": "functional_impact",
        },
        {
            "Question": "Any recent exposure that could explain your illness?",
            "A": "Contact with someone who was sick recently", "B": "Recent travel or crowded exposure",
            "C": "New medication, supplement, or food trigger", "D": "No known recent exposure",
            "E": "None of these / Not sure", "feature_id": "exposure_history",
        },
        {
            "Question": "Which pattern best describes symptom progression?",
            "A": "Getting progressively worse each day", "B": "Improving slightly but not resolved",
            "C": "Stable without major change", "D": "Waxing and waning repeatedly",
            "E": "None of these / Not sure", "feature_id": "progression",
        },
        {
            "Question": "Which relieving factor applies most to your symptoms?",
            "A": "Rest or sleep helps noticeably", "B": "Fluids, food, or warmth helps",
            "C": "Pain/symptom medicine helps", "D": "Nothing clearly relieves symptoms",
            "E": "None of these / Not sure", "feature_id": "relieving_factor",
        },
    ]


def build_turn_indexed_question(
    patient_state: Dict,
    symptom_state: Dict,
    current_question_count: int,
    asked_questions: List[str],
    *,
    allow_suffix_fallback: bool = False,
) -> Optional[Dict]:
    symptoms = symptom_state.get("current_symptoms", []) if isinstance(symptom_state, dict) else []
    chief = next((str(s).strip() for s in symptoms if str(s).strip()), "your symptoms")
    top_two = _top2_from_state(patient_state)
    templates = _turn_templates(chief)
    critic = QuestionCritic(symptom_state)

    start_idx = max(int(current_question_count or 0), 0)
    for offset in range(len(templates)):
        candidate = dict(templates[(start_idx + offset) % len(templates)])
        candidate.setdefault("priority", "high")
        candidate.setdefault(
            "clinical_intent",
            f"Collect structured discriminator #{start_idx + offset + 1} for {top_two[0]} vs {top_two[1]}",
        )
        candidate.setdefault("differentiates_between", top_two[:2])
        candidate.setdefault("allow_other", True)
        candidate.setdefault("question_source", "turn_indexed")
        if critic.validate(candidate, asked_questions):
            return candidate

    if allow_suffix_fallback:
        fallback = dict(templates[start_idx % len(templates)])
        fallback["Question"] = f"{fallback['Question']} (follow-up {start_idx + 1})"
        fallback.setdefault("D", "None of these")
        fallback.setdefault("E", "None of these / Not sure")
        fallback.setdefault("allow_other", True)
        fallback.setdefault("question_source", "turn_indexed")
        fallback.setdefault("differentiates_between", top_two[:2])
        return fallback

    return None
