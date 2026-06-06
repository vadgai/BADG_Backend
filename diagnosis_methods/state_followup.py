"""
State-Based Followup Generation for Method 2 - Pure LLM Sequential Diagnostic Reasoning

This module implements "Sequential Differential Diagnosis" using pure LLM reasoning:
- Step A: Evidence Analysis
- Step B: Differential Mapping (3-5 conditions)
- Step C: Gap Identification
- Step D: Next-Best-Question (NBQ)
"""

import json
import logging
import os
import re
from typing import Any, Optional, Union, Dict, List
from dotenv import load_dotenv
load_dotenv()

from utils.gemini_api_manager import generate_content_with_fallback, extract_json_from_text
from diagnosis_methods.patient_state import state_to_prompt_string
from diagnosis_rule_engine import analyze_case, load_diseases_from_folder, build_disease_profiles, DISEASE_PROFILES

logger = logging.getLogger(__name__)
_DIAG_V6_QUESTION_PLANNER = str(os.getenv("DIAG_V6_QUESTION_PLANNER", "true")).strip().lower() in {"1", "true", "yes", "on"}
_PROFILES_READY = False

_PLACEHOLDER_MARKERS = {
    "clinically precise question",
    "specific clinical",
    "specific clinical question",
    "specific finding",
    "specific option",
    "disease 1",
    "disease 2",
    "option a",
    "option b",
    "option c",
}

_GENERIC_QUESTION_MARKERS = {
    "getting worse",
    "can you share more details",
    "any other symptoms",
    "new or worsening symptoms",
    "symptom progression",
    "breathing difficulties",
    "clinically precise differentiator question",
    "clinically precise question",
    "specific clinical",
    "specific finding",
}


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _token_set(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", _normalize_text(text)) if t}


def _jaccard(a: str, b: str) -> float:
    sa = _token_set(a)
    sb = _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / float(len(sa | sb))


def _extract_asked_questions(patient_state: Dict) -> List[str]:
    """Extract all previously asked questions from both symptom_state and raw chat_history."""
    seen: set = set()
    cleaned: List[str] = []

    # Primary source: symptom_state.questions_asked
    symptom_state = patient_state.get("symptom_state") if isinstance(patient_state.get("symptom_state"), dict) else {}
    for q in (symptom_state.get("questions_asked") or []):
        q_text = str(q).strip()
        norm = _normalize_text(q_text)
        if q_text and norm not in seen:
            seen.add(norm)
            cleaned.append(q_text)

    # Secondary source: raw chat_history [{"bot": ..., "user": ...}, ...]
    for msg in (patient_state.get("chat_history") or []):
        if not isinstance(msg, dict):
            continue
        q_text = str(msg.get("bot") or "").strip()
        norm = _normalize_text(q_text)
        if q_text and norm not in seen:
            seen.add(norm)
            cleaned.append(q_text)

    return cleaned


def _format_chat_history(patient_state: Dict) -> str:
    """Format full Q&A pairs from chat_history for LLM context."""
    history: List[Dict] = patient_state.get("chat_history") or []
    if not history:
        return "No previous questions asked."

    lines: List[str] = []
    turn = 0
    i = 0
    while i < len(history):
        msg = history[i]
        if not isinstance(msg, dict):
            i += 1
            continue
        bot_q = str(msg.get("bot") or "").strip()
        user_a = str(msg.get("user") or "").strip()
        if bot_q:
            turn += 1
            lines.append(f"Q{turn}: {bot_q}")
            if user_a:
                lines.append(f"A{turn}: {user_a}")
            elif i + 1 < len(history) and isinstance(history[i + 1], dict):
                next_user = str(history[i + 1].get("user") or "").strip()
                if next_user:
                    lines.append(f"A{turn}: {next_user}")
                    i += 1
        elif user_a and lines:
            lines.append(f"(Answer): {user_a}")
        i += 1

    return "\n".join(lines) if lines else "No previous questions asked."


def _contains_placeholder_text(text: str) -> bool:
    t = _normalize_text(text)
    if not t:
        return True
    return any(marker in t for marker in _PLACEHOLDER_MARKERS)


def _is_generic_question(text: str) -> bool:
    t = _normalize_text(text)
    if not t:
        return True
    return any(marker in t for marker in _GENERIC_QUESTION_MARKERS)


def _is_repeated_question(question: str, asked_questions: List[str]) -> bool:
    from followup.validators.repetition import is_repeated_question

    return is_repeated_question(question, asked_questions)


def _extract_top_two_condition_names(patient_state: Dict) -> List[str]:
    differential = patient_state.get("differential_diagnosis")
    names: List[str] = []
    if isinstance(differential, list):
        for item in differential:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if name:
                    names.append(name)
            if len(names) >= 2:
                break
    return names


def _ensure_profiles_loaded() -> None:
    global _PROFILES_READY
    if _PROFILES_READY and DISEASE_PROFILES:
        return
    load_diseases_from_folder()
    build_disease_profiles()
    _PROFILES_READY = True


def _extract_profile_by_name(condition_name: str) -> Optional[Dict]:
    target = _normalize_text(condition_name)
    if not target:
        return None
    for profile in DISEASE_PROFILES:
        name = _normalize_text(profile.get("name", ""))
        if not name:
            continue
        if name == target or name in target or target in name:
            return profile
    return None


def _known_findings_set(patient_state: Dict) -> set:
    positives = patient_state.get("identified_symptoms") if isinstance(patient_state.get("identified_symptoms"), list) else []
    negatives = patient_state.get("negatives") if isinstance(patient_state.get("negatives"), list) else []
    known = set()
    for item in positives + negatives:
        term = _normalize_text(item)
        if term:
            known.add(term)
    return known


def _feature_terms(profile: Dict, bucket: str) -> List[Dict[str, Union[str, float]]]:
    terms: List[Dict[str, Union[str, float]]] = []
    features = profile.get("features", {}).get(bucket, []) if isinstance(profile.get("features"), dict) else []
    if isinstance(features, list) and features:
        for feature in features:
            if isinstance(feature, dict):
                term = _normalize_text(feature.get("term"))
                if not term:
                    continue
                try:
                    weight = float(feature.get("weight", 1.0))
                except (TypeError, ValueError):
                    weight = 1.0
                terms.append({"term": term, "weight": max(0.1, weight)})
        if terms:
            return terms

    # Backward compatibility if features are missing.
    if bucket == "key":
        terms_raw = profile.get("symptoms", {}).get("required", []) if isinstance(profile.get("symptoms"), dict) else []
        terms.extend({"term": _normalize_text(item), "weight": 1.0} for item in terms_raw if _normalize_text(item))
    elif bucket == "supportive":
        terms_raw = profile.get("symptoms", {}).get("common", []) if isinstance(profile.get("symptoms"), dict) else []
        terms.extend({"term": _normalize_text(item), "weight": 0.6} for item in terms_raw if _normalize_text(item))
    elif bucket == "rare":
        terms_raw = profile.get("symptoms", {}).get("rare", []) if isinstance(profile.get("symptoms"), dict) else []
        terms.extend({"term": _normalize_text(item), "weight": 0.35} for item in terms_raw if _normalize_text(item))
    return terms


def _semantic_topic_from_feature(feature: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]", " ", feature.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _build_deterministic_question_from_feature(
    feature_term: str,
    opposite_term: str,
    top_two: List[str],
    priority: str,
) -> Dict[str, str]:
    disease_1 = top_two[0] if len(top_two) > 0 else "Top diagnosis"
    disease_2 = top_two[1] if len(top_two) > 1 else "Alternate diagnosis"
    feature_label = feature_term.strip()
    opposite_label = opposite_term.strip() if opposite_term else "a different competing pattern"
    return {
        "Question": f"Which statement best matches your symptoms regarding {feature_label}?",
        "A": f"Yes, {feature_label} is clearly present",
        "B": f"No, symptoms are closer to {opposite_label}",
        "C": "Neither pattern fits clearly",
        "D": f"I'm not sure about {feature_label}",
        "E": "None of these / Not sure",
        "allow_other": True,
        "priority": priority,
        "clinical_intent": f"Differentiate {disease_1} vs {disease_2} using feature-level evidence",
        "differentiates_between": [disease_1, disease_2],
        "feature_id": feature_label,
        "question_source": "deterministic",
    }


def _deterministic_top2_and_feature(patient_state: Dict) -> Optional[Dict[str, Any]]:
    _ensure_profiles_loaded()
    demographics = patient_state.get("demographics") if isinstance(patient_state.get("demographics"), dict) else {}
    age = demographics.get("age")
    gender = demographics.get("gender")
    positives = patient_state.get("identified_symptoms") if isinstance(patient_state.get("identified_symptoms"), list) else []
    negatives = patient_state.get("negatives") if isinstance(patient_state.get("negatives"), list) else []
    symptom_state = patient_state.get("symptom_state") if isinstance(patient_state.get("symptom_state"), dict) else {}
    red_flags = symptom_state.get("red_flags") if isinstance(symptom_state.get("red_flags"), list) else patient_state.get("red_flags", [])
    modifier_map = symptom_state.get("modifier_map") if isinstance(symptom_state.get("modifier_map"), dict) else symptom_state.get("modifiers")

    if not positives:
        return None

    ranking = analyze_case(
        age=age,
        gender=gender,
        symptoms=positives,
        chat_history="Structured state only",
        negatives=negatives,
        modifiers=modifier_map,
        red_flags=red_flags if isinstance(red_flags, list) else [],
    )
    conditions = ranking.get("conditions") if isinstance(ranking, dict) else []
    if not isinstance(conditions, list) or len(conditions) < 1:
        return None
    top_condition = conditions[0] if isinstance(conditions[0], dict) else None
    second_condition = conditions[1] if len(conditions) > 1 and isinstance(conditions[1], dict) else None
    if not top_condition:
        return None
    top_name = str(top_condition.get("name", "")).strip()
    second_name = str(second_condition.get("name", "")).strip() if second_condition else ""
    top_two = [name for name in [top_name, second_name] if name]
    if len(top_two) < 2:
        # Fall back to current state differential names when rule engine returns one candidate.
        top_two = _extract_top_two_condition_names(patient_state) or top_two
    if len(top_two) < 2:
        return None

    profile_1 = _extract_profile_by_name(top_two[0])
    profile_2 = _extract_profile_by_name(top_two[1])
    if not profile_1 or not profile_2:
        return None

    from followup.constants import JACCARD_REPEAT_THRESHOLD

    asked_questions = _extract_asked_questions(patient_state)
    known = _known_findings_set(patient_state)
    red_flag_terms = set(_normalize_text(item) for item in (red_flags if isinstance(red_flags, list) else []) if _normalize_text(item))

    top1_terms = _feature_terms(profile_1, "key") + _feature_terms(profile_1, "supportive") + _feature_terms(profile_1, "rare")
    top2_terms = _feature_terms(profile_2, "key") + _feature_terms(profile_2, "supportive") + _feature_terms(profile_2, "rare")
    top2_term_set = {str(item.get("term")) for item in top2_terms if str(item.get("term"))}
    top1_term_set = {str(item.get("term")) for item in top1_terms if str(item.get("term"))}

    candidates: List[Dict[str, Any]] = []
    for feature in top1_terms:
        term = str(feature.get("term", "")).strip()
        if not term or term in known:
            continue
        if term in top2_term_set:
            continue
        if any(_jaccard(term, asked) >= JACCARD_REPEAT_THRESHOLD for asked in asked_questions):
            continue
        opposite = next((str(item.get("term")) for item in top2_terms if str(item.get("term")) not in known), "")
        weight = float(feature.get("weight", 1.0) or 1.0)
        red_priority = any(flag in term or term in flag for flag in red_flag_terms) if red_flag_terms else False
        separation = 1.0
        if opposite:
            separation = max(0.1, 1.0 - _jaccard(term, opposite))
        novelty = 1.0 if term not in known else 0.0
        utility = (1.45 * weight) + (1.15 * separation) + (0.7 * novelty) + (1.0 if red_priority else 0.0)
        candidates.append(
            {
                "term": term,
                "opposite": opposite,
                "utility": utility,
                "priority": "red-flag" if red_priority else "high",
            }
        )

    for feature in top2_terms:
        term = str(feature.get("term", "")).strip()
        if not term or term in known:
            continue
        if term in top1_term_set:
            continue
        if any(_jaccard(term, asked) >= JACCARD_REPEAT_THRESHOLD for asked in asked_questions):
            continue
        opposite = next((str(item.get("term")) for item in top1_terms if str(item.get("term")) not in known), "")
        weight = float(feature.get("weight", 1.0) or 1.0)
        red_priority = any(flag in term or term in flag for flag in red_flag_terms) if red_flag_terms else False
        separation = 1.0
        if opposite:
            separation = max(0.1, 1.0 - _jaccard(term, opposite))
        novelty = 1.0 if term not in known else 0.0
        utility = (1.35 * weight) + (1.1 * separation) + (0.7 * novelty) + (1.0 if red_priority else 0.0)
        candidates.append(
            {
                "term": term,
                "opposite": opposite,
                "utility": utility,
                "priority": "red-flag" if red_priority else "high",
            }
        )

    if not candidates:
        return {
            "top_two": top_two,
            "ranking": ranking,
            "feature": None,
            "question": None,
        }

    candidates.sort(key=lambda item: float(item.get("utility", 0.0)), reverse=True)
    selected = candidates[0]
    question = _build_deterministic_question_from_feature(
        feature_term=str(selected.get("term", "")),
        opposite_term=str(selected.get("opposite", "")),
        top_two=top_two,
        priority=str(selected.get("priority", "high")),
    )
    return {
        "top_two": top_two,
        "ranking": ranking,
        "feature": selected,
        "question": question,
    }


def _build_chief_symptom_mcq(patient_state: Dict) -> Dict[str, str]:
    symptoms = patient_state.get("identified_symptoms") if isinstance(patient_state.get("identified_symptoms"), list) else []
    chief = ""
    for item in symptoms:
        term = _normalize_text(item)
        if term:
            chief = term
            break
    if not chief:
        chief = _normalize_text(patient_state.get("chief_complaint", "")) or "main symptom"

    lower = chief.lower()
    if any(token in lower for token in {"abdominal", "stomach", "vomit", "diarrhea", "bowel"}):
        return {
            "Question": "Which digestive pattern best matches your current symptoms?",
            "A": "Right-lower abdominal pain worsens with movement",
            "B": "Diffuse abdominal symptoms with loose stools or vomiting",
            "C": "Upper-abdominal burning discomfort linked to meals",
            "D": "Bloating or gas mostly after eating",
            "E": "None of these / Not sure",
            "allow_other": True,
            "priority": "high",
            "clinical_intent": "Differentiate inflammatory surgical, infectious, and acid-peptic abdominal patterns",
            "differentiates_between": ["Top suspect #1", "Top suspect #2"],
            "feature_id": "digestive_pattern",
            "question_source": "deterministic",
        }

    if any(token in lower for token in {"cough", "breath", "chest", "wheeze", "phlegm"}):
        return {
            "Question": "Which respiratory feature is most prominent right now?",
            "A": "Breathlessness or wheeze episodes with chest tightness",
            "B": "Productive cough with colored sputum and fever",
            "C": "Dry cough with throat irritation and minimal sputum",
            "D": "Chest pain that worsens with deep breathing",
            "E": "None of these / Not sure",
            "allow_other": True,
            "priority": "high",
            "clinical_intent": "Differentiate airway-reactive, bacterial, and viral respiratory patterns",
            "differentiates_between": ["Top suspect #1", "Top suspect #2"],
            "feature_id": "respiratory_pattern",
            "question_source": "deterministic",
        }

    if any(token in lower for token in {"headache", "dizziness", "weakness", "numb", "balance"}):
        return {
            "Question": "Which neurological feature best describes your current condition?",
            "A": "One-sided weakness/numbness or speech disturbance",
            "B": "Severe throbbing headache with light sensitivity",
            "C": "Spinning dizziness without focal weakness",
            "D": "Gradual memory or concentration difficulties",
            "E": "None of these / Not sure",
            "allow_other": True,
            "priority": "high",
            "clinical_intent": "Differentiate focal neurological, migraine, and vestibular patterns",
            "differentiates_between": ["Top suspect #1", "Top suspect #2"],
            "feature_id": "neurological_pattern",
            "question_source": "deterministic",
        }

    return {
        "Question": f"Which associated pattern best matches your current {chief}?",
        "A": f"Localized and persistent {chief} in one area",
        "B": f"{chief} with systemic features like fever or fatigue",
        "C": f"Trigger-linked episodic {chief} that comes and goes",
        "D": f"{chief} that started suddenly and is severe",
        "E": "None of these / Not sure",
        "allow_other": True,
        "priority": "high",
        "clinical_intent": f"Differentiate competing causes of {chief} using symptom pattern context",
        "differentiates_between": ["Top suspect #1", "Top suspect #2"],
        "feature_id": chief,
        "question_source": "deterministic",
    }


def _build_alternate_contextual_mcq(patient_state: Dict, asked_questions: List[str]) -> Dict[str, str]:
    positives = patient_state.get("identified_symptoms") if isinstance(patient_state.get("identified_symptoms"), list) else []
    positives = [str(item).strip() for item in positives if str(item).strip()]
    red_flags = patient_state.get("red_flags") if isinstance(patient_state.get("red_flags"), list) else []
    red_flags = [str(item).strip() for item in red_flags if str(item).strip()]

    opt_a = positives[0] if len(positives) > 0 else "localized pain pattern"
    opt_b = positives[1] if len(positives) > 1 else "systemic fever/chills pattern"
    opt_c = red_flags[0] if red_flags else "intermittent trigger-linked pattern"
    opt_d = positives[2] if len(positives) > 2 else "gradual worsening over days"

    candidate = {
        "Question": "Which of these associated findings is most clearly present now?",
        "A": f"Mainly {opt_a}",
        "B": f"Mainly {opt_b}",
        "C": f"Mainly {opt_c}",
        "D": f"Mainly {opt_d}",
        "E": "None of these / Not sure",
        "allow_other": True,
        "priority": "red-flag" if red_flags else "high",
        "clinical_intent": "Capture the most discriminative associated feature from current structured findings",
        "differentiates_between": ["Top suspect #1", "Top suspect #2"],
        "feature_id": "associated_feature_focus",
        "question_source": "deterministic",
    }

    if _is_repeated_question(candidate.get("Question", ""), asked_questions):
        candidate["Question"] = "Which change best reflects your symptom pattern since the last question?"
    return candidate


def build_contextual_fallback_mcq(patient_state: Dict) -> Union[Dict, str]:
    """
    Build a symptom-based MCQ fallback when LLM is unavailable.
    Does NOT use any disease dataset — driven entirely by chief symptom patterns.
    """
    turn_count = int(patient_state.get("turn_count", 0) or 0)
    asked_questions = _extract_asked_questions(patient_state)

    if turn_count >= 12:
        return "Ready for diagnosis"

    fallback = _build_chief_symptom_mcq(patient_state)
    if not _is_repeated_question(fallback.get("Question", ""), asked_questions):
        return fallback

    alternate = _build_alternate_contextual_mcq(patient_state, asked_questions)
    if not _is_repeated_question(alternate.get("Question", ""), asked_questions):
        return alternate

    return _build_alternate_contextual_mcq(patient_state, asked_questions)


def _validate_mcq_quality(mcq: Dict, patient_state: Dict) -> (bool, str):
    from followup.validators.mcq_quality import validate_mcq_quality

    return validate_mcq_quality(mcq, patient_state)


def get_followup_from_state(
    patient_state: Dict,
    top_diseases: Optional[List[Dict]] = None,
    disease_engine=None,
    entropy_tracker=None,
    max_retries: int = 1,
) -> Union[Dict, str, None]:
    """Backward-compatible entry — delegates to followup.orchestrator."""
    del top_diseases, disease_engine, entropy_tracker
    from followup.orchestrator import get_next_followup_question

    return get_next_followup_question(patient_state, max_retries=max_retries)


def analyze_answer_for_state(
    question: str,
    answer: str,
    current_state: Dict
) -> Optional[Dict]:
    """
    Analyze a patient's answer and extract structured information to update state.
    Now includes differential diagnosis generation using pure LLM reasoning.
    
    Args:
        question: The question that was asked
        answer: The patient's answer
        current_state: Current patient state
        
    Returns:
        Dictionary with extracted information (symptoms, negatives, conditions, confidence, differential_diagnosis)
        or None if analysis fails
    """
    from utils.gemini_api_manager import get_gemini_model
    model_available, model = get_gemini_model()
    
    if not model_available or model is None:
        return None
    
    state_str = state_to_prompt_string(current_state)
    
    # Get patient demographics for context
    age = current_state.get("demographics", {}).get("age", "Unknown")
    gender = current_state.get("demographics", {}).get("gender", "Unknown")
    symptom_state = current_state.get("symptom_state") if isinstance(current_state.get("symptom_state"), dict) else {}
    modifier_map = symptom_state.get("modifier_map") if isinstance(symptom_state.get("modifier_map"), dict) else {}
    red_flags = symptom_state.get("red_flags") if isinstance(symptom_state.get("red_flags"), list) else current_state.get("red_flags", [])
    
    prompt = f"""Update the diagnostic reasoning from the latest answer. Patient: {age}/{gender}. Apply India-specific context (tropical/endemic disease, lifestyle) where relevant.

STATE:
{state_str}
Modifiers: {json.dumps(modifier_map, ensure_ascii=False)}
Red flags: {json.dumps(red_flags, ensure_ascii=False)}
Q: {question}
A: {answer}

DO:
1. Add NEW symptoms from the answer to identified_symptoms; anything ruled out by the answer to negatives.
2. Set confidence_score 0.0-1.0 by strength of evidence so far.
3. Rank EXACTLY 3 differentials (most->least likely). Each: name (specific condition), confidence (High>=70% | Moderate 50-70% | Low<50%), reasoning (1-2 sentences anchored to the findings/negatives, consistent with the confidence).
4. differentiator_symptom: the single feature that most strongly separates Suspect #1 vs #2.
5. running_summary: 2-3 clinical sentences (key findings, top suspect, next differentiator) for report reuse.

Return ONLY valid JSON:
{{
  "identified_symptoms": ["..."],
  "negatives": ["..."],
  "confidence_score": 0.75,
  "differential_diagnosis": [
    {{"name": "...", "confidence": "High|Moderate|Low", "reasoning": "..."}},
    {{"name": "...", "confidence": "High|Moderate|Low", "reasoning": "..."}},
    {{"name": "...", "confidence": "High|Moderate|Low", "reasoning": "..."}}
  ],
  "differentiator_symptom": "...",
  "running_summary": "..."
}}
"""

    success, raw_text, error = generate_content_with_fallback(
        prompt=prompt,
        max_retries=None,  # Try all available API keys (up to 15) if first fails
        temperature=0.2,
        max_output_tokens=1100
    )
    
    if not success or not raw_text:
        logger.warning(f"Failed to analyze answer: {error}")
        return None
    
    # Extract JSON
    parsed_json = extract_json_from_text(raw_text)
    
    if parsed_json and isinstance(parsed_json, dict):
        return parsed_json
    
    return None
