"""
Symptom Extractor v5
Extracts positive (+) and negative (-) findings from patient answers.
Provides lightweight state update helpers for the v5 reasoning loop.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.gemini_api_manager import (
    generate_content_with_fallback,
    extract_json_from_text,
    get_gemini_model,
)
from symptom_extractor import build_signal_extraction_prompt
from symptom_processing.symptom import hybrid_symptom_extraction

logger = logging.getLogger(__name__)


_NORMALIZATION_MAP = {
    "weight lost": "weight loss",
    "lost weight": "weight loss",
    "stomach hurts": "abdominal pain",
    "stomach hurt": "abdominal pain",
    "stomach pain": "abdominal pain",
    "tummy pain": "abdominal pain",
    "belly pain": "abdominal pain",
}

_NEGATIVE_SHORT_ANSWERS = {
    "no",
    "nope",
    "nah",
    "none",
    "negative",
    "not at all",
}

_RED_FLAG_HINTS = [
    ("chest pain", "chest pain"),
    ("severe chest pain", "severe chest pain"),
    ("difficulty breathing", "difficulty breathing"),
    ("shortness of breath", "shortness of breath"),
    ("trouble breathing", "difficulty breathing"),
    ("cannot breathe", "difficulty breathing"),
    ("faint", "fainting"),
    ("passed out", "loss of consciousness"),
    ("unconscious", "loss of consciousness"),
    ("seizure", "seizure"),
    ("confusion", "confusion"),
    ("severe headache", "severe headache"),
    ("worst headache", "severe headache"),
    ("blood in stool", "blood in stool"),
    ("bloody stool", "blood in stool"),
    ("vomiting blood", "vomiting blood"),
    ("coughing blood", "coughing blood"),
    ("black stool", "black stool"),
]

_MODIFIER_KEYS = (
    "duration",
    "onset",
    "location",
    "quality",
    "severity",
    "aggravating_factors",
    "relieving_factors",
    "associated_symptoms",
)

# Matches a bare internal identifier (e.g. a follow-up feature_id like
# "gradual_onset"/"caffeine_intake" or an MCQ option key) that occasionally
# leaks through as if it were the patient's answer text, instead of the
# option's human-readable display text. Natural clinical language never
# contains underscores, so this pattern is safe to treat as "not a real
# finding" and humanize rather than store verbatim.
_SNAKE_CASE_TOKEN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")


def humanize_internal_token(value: Any) -> str:
    """
    Convert a leaked internal identifier ("duration_less_than_one_month") into
    plain readable text ("duration less than one month"). Ordinary
    natural-language findings are returned unchanged.
    """
    text = str(value or "").strip()
    if not text:
        return text
    if _SNAKE_CASE_TOKEN.match(text.lower()):
        return re.sub(r"_+", " ", text).strip()
    return text


def extract_initial_symptoms(
    symptoms_text: str,
    fallback_list: Optional[List[str]] = None,
) -> List[str]:
    """
    Extract initial symptom list from raw user input.
    Uses hybrid_symptom_extraction with a safe fallback.
    """
    try:
        extracted = hybrid_symptom_extraction(symptoms_text or "")
        if extracted:
            return [str(s).strip() for s in extracted if str(s).strip()]
    except Exception as exc:
        logger.warning("extract_initial_symptoms: hybrid_symptom_extraction failed: %s", exc)

    if isinstance(fallback_list, list) and fallback_list:
        return [str(s).strip() for s in fallback_list if str(s).strip()]

    if symptoms_text:
        # Split by newline/comma for a minimal fallback.
        parts: List[str] = []
        for raw in str(symptoms_text).replace(",", "\n").splitlines():
            item = raw.strip()
            if item:
                parts.append(item)
        return parts

    return []


def _coerce_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _dedupe_preserve(items: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for item in items:
        key = str(item).strip().lower()
        if not key or key in seen:
            continue
        deduped.append(str(item).strip())
        seen.add(key)
    return deduped


def _normalize_term(value: Any) -> str:
    term = str(value).strip().lower()
    if not term:
        return ""
    term = humanize_internal_token(term)
    term = re.sub(r"\s+", " ", term)
    if term in _NORMALIZATION_MAP:
        return _NORMALIZATION_MAP[term]
    for source, target in _NORMALIZATION_MAP.items():
        if source in term:
            return target
    return term


def _is_negative_short_answer(patient_response: str) -> bool:
    if not patient_response:
        return False
    text = re.sub(r"[^a-z\s]", "", patient_response.lower()).strip()
    if not text:
        return False
    if text in _NEGATIVE_SHORT_ANSWERS:
        return True
    if text.startswith("no ") and len(text.split()) <= 3:
        return True
    if text.startswith("none ") and len(text.split()) <= 3:
        return True
    return False


def _extract_question_topic(last_question_text: Optional[str]) -> str:
    if not last_question_text:
        return ""
    question = str(last_question_text).strip()
    if not question:
        return ""

    question = question.split("(A:")[0].strip()
    q = re.sub(r"\s+", " ", question).strip().lower()

    patterns = [
        r"do you have (.+)",
        r"are you (?:having|experiencing|feeling) (.+)",
        r"have you had (.+)",
        r"is there (.+)",
        r"any (.+)",
    ]

    topic = ""
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            topic = match.group(1).strip()
            break

    if not topic:
        topic = re.sub(
            r"^(what|when|where|why|how|do|does|did|is|are|was|were|can|could|would|will|have|has|had)\b",
            "",
            q,
        ).strip()

    topic = topic.rstrip("?.!,;: ")
    topic = re.sub(r"\b(the|a|an|any)\b", " ", topic)
    topic = re.sub(r"\s+", " ", topic).strip()
    if len(topic) < 2:
        return ""
    return _normalize_term(topic)


def _detect_red_flags(patient_response: str) -> List[str]:
    text = str(patient_response or "").lower()
    detected: List[str] = []
    for hint, label in _RED_FLAG_HINTS:
        if hint in text:
            detected.append(label)
    return _dedupe_preserve(detected)


def _normalize_modifier_map(raw_map: Any) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {
        "duration": "",
        "onset": "",
        "location": "",
        "quality": "",
        "severity": "",
        "aggravating_factors": [],
        "relieving_factors": [],
        "associated_symptoms": [],
    }
    if not isinstance(raw_map, dict):
        return normalized

    for key in _MODIFIER_KEYS:
        value = raw_map.get(key)
        if key in {"aggravating_factors", "relieving_factors", "associated_symptoms"}:
            values = _coerce_list(value)
            normalized[key] = _dedupe_preserve([_normalize_term(item) for item in values if _normalize_term(item)])
        else:
            if value is None:
                continue
            term = str(value).strip()
            if term:
                normalized[key] = term
    return normalized


def _merge_modifier_map(existing: Any, incoming: Any) -> Dict[str, Any]:
    base = _normalize_modifier_map(existing)
    fresh = _normalize_modifier_map(incoming)
    for key in ("duration", "onset", "location", "quality", "severity"):
        if str(fresh.get(key, "")).strip():
            base[key] = str(fresh.get(key)).strip()
    for key in ("aggravating_factors", "relieving_factors", "associated_symptoms"):
        merged = _dedupe_preserve(
            [*_coerce_list(base.get(key)), *_coerce_list(fresh.get(key))]
        )
        base[key] = [str(item).strip() for item in merged if str(item).strip()]
    return base


def _heuristic_modifier_map(patient_response: str) -> Dict[str, Any]:
    text = str(patient_response or "").strip()
    lower = text.lower()
    modifier_map = _normalize_modifier_map({})

    duration_match = re.search(
        r"\b(for|since|from)\s+(\d+\s*(hour|hours|day|days|week|weeks|month|months|year|years))\b",
        lower,
    )
    if duration_match:
        modifier_map["duration"] = duration_match.group(2)

    onset_match = re.search(r"\b(sudden|gradual|started suddenly|started gradually)\b", lower)
    if onset_match:
        modifier_map["onset"] = onset_match.group(1)

    location_patterns = [
        "right lower abdomen",
        "left lower abdomen",
        "upper abdomen",
        "lower abdomen",
        "chest",
        "head",
        "throat",
        "back",
    ]
    for loc in location_patterns:
        if loc in lower:
            modifier_map["location"] = loc
            break

    quality_patterns = [
        "burning",
        "sharp",
        "dull",
        "throbbing",
        "cramping",
        "stabbing",
        "pressure",
    ]
    for quality in quality_patterns:
        if quality in lower:
            modifier_map["quality"] = quality
            break

    severity_match = re.search(r"\b([0-9]|10)\s*/\s*10\b", lower)
    if severity_match:
        modifier_map["severity"] = f"{severity_match.group(1)}/10"
    elif "severe" in lower:
        modifier_map["severity"] = "severe"
    elif "moderate" in lower:
        modifier_map["severity"] = "moderate"
    elif "mild" in lower:
        modifier_map["severity"] = "mild"

    aggravating_terms = []
    if any(token in lower for token in ["worse with", "aggravated by", "worsens when"]):
        aggravating_terms.append("activity-related worsening")
    if "after meals" in lower or "after eating" in lower:
        aggravating_terms.append("after meals")
    if "walking" in lower or "movement" in lower:
        aggravating_terms.append("movement")
    modifier_map["aggravating_factors"] = _dedupe_preserve(aggravating_terms)

    relieving_terms = []
    if "better with rest" in lower or "improves with rest" in lower:
        relieving_terms.append("rest")
    if "after medicine" in lower or "after medication" in lower:
        relieving_terms.append("medication")
    if "relieved by" in lower:
        relieving_terms.append("relieved by intervention")
    modifier_map["relieving_factors"] = _dedupe_preserve(relieving_terms)

    assoc_terms = []
    for candidate in ["nausea", "vomiting", "diarrhea", "fever", "cough", "weight loss", "fatigue", "chills"]:
        if candidate in lower:
            assoc_terms.append(candidate)
    modifier_map["associated_symptoms"] = _dedupe_preserve(assoc_terms)
    return modifier_map


def _modifier_map_to_legacy_list(modifier_map: Dict[str, Any]) -> List[str]:
    legacy: List[str] = []
    for key in ("duration", "onset", "location", "quality", "severity"):
        value = str(modifier_map.get(key, "")).strip()
        if value:
            legacy.append(f"{key}: {value}")
    for key in ("aggravating_factors", "relieving_factors", "associated_symptoms"):
        values = modifier_map.get(key, [])
        if isinstance(values, list) and values:
            legacy.append(f"{key}: {', '.join(str(v).strip() for v in values if str(v).strip())}")
    return legacy


def _heuristic_signals(
    patient_response: str,
    last_question_text: Optional[str],
) -> Dict[str, Any]:
    # Positive findings are extracted by the LLM (combined call, or the recovery
    # extractor when it fails), which normalizes to clean clinical terms. The
    # deterministic heuristic deliberately does NOT guess positives from question
    # topics — doing so previously polluted the symptom list with question-stem
    # fragments (e.g. "you wake up at night due to symptoms"). It handles only
    # negatives, red flags, and modifiers.
    positives: List[str] = []
    negatives: List[str] = []
    red_flags = _detect_red_flags(patient_response)

    if _is_negative_short_answer(patient_response):
        topic = _extract_question_topic(last_question_text)
        if topic:
            negatives.append(topic)
    modifier_map = _heuristic_modifier_map(patient_response)

    return {
        "new_positive_findings": positives,
        "new_negative_findings": _dedupe_preserve(negatives),
        "red_flags_detected": red_flags,
        "modifier_map": modifier_map,
        "modifiers": _modifier_map_to_legacy_list(modifier_map),
        "clinical_utility": bool(positives or negatives or red_flags),
    }


def _normalize_findings(items: List[Any]) -> List[str]:
    normalized: List[str] = []
    for item in items:
        if isinstance(item, dict):
            symptom = item.get("symptom") or item.get("name") or item.get("finding")
            if symptom:
                term = _normalize_term(symptom)
                if term:
                    normalized.append(term)
        elif isinstance(item, str):
            term = _normalize_term(item)
            if term:
                normalized.append(term)
        else:
            text = _normalize_term(item)
            if text:
                normalized.append(text)
    return _dedupe_preserve(normalized)


def extract_signals(
    current_state: Dict[str, Any],
    patient_response: str,
    last_question_text: Optional[str] = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """
    Extract positive and negative findings from the latest answer.

    When ``use_llm`` is False (or no model is available), a deterministic
    heuristic extractor is used. This avoids spending a Gemini call here when
    the differential-reasoning step already performs LLM-based symptom/negative
    extraction, keeping per-turn API usage low so the LLM stays within quota.
    Returns a normalized dictionary even on failure.
    """
    # Default structure
    fallback = {
        "new_positive_findings": [],
        "new_negative_findings": [],
        "red_flags_detected": [],
        "modifier_map": _normalize_modifier_map({}),
        "modifiers": [],
        "clinical_utility": False,
    }

    if not use_llm:
        return _heuristic_signals(patient_response, last_question_text) or fallback

    model_available, _ = get_gemini_model()
    if not model_available:
        return _heuristic_signals(patient_response, last_question_text) or fallback

    prompt_state = dict(current_state) if isinstance(current_state, dict) else {}
    if "current_symptoms" not in prompt_state and prompt_state.get("identified_symptoms"):
        prompt_state["current_symptoms"] = prompt_state.get("identified_symptoms", [])

    prompt = build_signal_extraction_prompt(
        current_state=prompt_state,
        patient_response=patient_response,
        last_question_text=last_question_text,
    )

    try:
        success, raw_text, error = generate_content_with_fallback(
            prompt=prompt,
            max_retries=None,
            temperature=0.2,
            max_output_tokens=600,
        )
        if not success or not raw_text:
            logger.warning("extract_signals: generation failed: %s", error)
            return _heuristic_signals(patient_response, last_question_text) or fallback

        parsed = extract_json_from_text(raw_text)
        if not isinstance(parsed, dict):
            return _heuristic_signals(patient_response, last_question_text) or fallback

        positives = _normalize_findings(_coerce_list(parsed.get("new_positive_findings")))
        negatives = _normalize_findings(_coerce_list(parsed.get("new_negative_findings")))
        red_flags = _normalize_findings(_coerce_list(parsed.get("red_flags_detected")))
        modifier_map = _merge_modifier_map(
            _heuristic_modifier_map(patient_response),
            parsed.get("modifier_map"),
        )

        if _is_negative_short_answer(patient_response):
            topic = _extract_question_topic(last_question_text)
            if topic:
                negatives = _dedupe_preserve(negatives + [topic])

        red_flags = _dedupe_preserve(red_flags + _detect_red_flags(patient_response))

        clinical_utility = parsed.get("clinical_utility")
        if not isinstance(clinical_utility, bool):
            clinical_utility = bool(positives or negatives or red_flags)

        return {
            "new_positive_findings": positives,
            "new_negative_findings": negatives,
            "red_flags_detected": red_flags,
            "modifier_map": modifier_map,
            "modifiers": _modifier_map_to_legacy_list(modifier_map),
            "clinical_utility": clinical_utility,
        }
    except Exception as exc:
        logger.warning("extract_signals: unexpected error: %s", exc)
        return _heuristic_signals(patient_response, last_question_text) or fallback


def _merge_unique(target: List[str], incoming: List[str]) -> List[str]:
    existing = {str(t).strip().lower() for t in target if str(t).strip()}
    for item in incoming:
        key = str(item).strip().lower()
        if not key or key in existing:
            continue
        target.append(str(item).strip())
        existing.add(key)
    return target


def apply_signals_to_state(
    patient_state: Dict[str, Any],
    signals: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge extracted signals into patient_state (identified_symptoms, negatives, red_flags).
    """
    if not isinstance(patient_state, dict):
        return patient_state

    positives = [humanize_internal_token(item) for item in (signals.get("new_positive_findings") or [])]
    negatives = [humanize_internal_token(item) for item in (signals.get("new_negative_findings") or [])]
    red_flags = [humanize_internal_token(item) for item in (signals.get("red_flags_detected") or [])]
    incoming_modifier_map = signals.get("modifier_map") if isinstance(signals.get("modifier_map"), dict) else {}
    incoming_modifiers = signals.get("modifiers") if isinstance(signals.get("modifiers"), list) else []

    patient_state.setdefault("identified_symptoms", [])
    patient_state.setdefault("negatives", [])
    patient_state.setdefault("red_flags", [])
    symptom_state = patient_state.get("symptom_state") if isinstance(patient_state.get("symptom_state"), dict) else {}

    _merge_unique(patient_state["identified_symptoms"], positives)
    _merge_unique(patient_state["negatives"], negatives)
    _merge_unique(patient_state["red_flags"], red_flags)

    existing_map = symptom_state.get("modifier_map") if isinstance(symptom_state.get("modifier_map"), dict) else {}
    merged_map = _merge_modifier_map(existing_map, incoming_modifier_map)
    symptom_state["modifier_map"] = merged_map
    symptom_state["modifiers"] = _dedupe_preserve(
        [*(_coerce_list(symptom_state.get("modifiers"))), *(_coerce_list(incoming_modifiers)), *(_modifier_map_to_legacy_list(merged_map))]
    )
    symptom_state["current_symptoms"] = _dedupe_preserve(patient_state.get("identified_symptoms", []))
    symptom_state["red_flags"] = _dedupe_preserve(patient_state.get("red_flags", []))
    symptom_state.setdefault("questions_asked", [])
    patient_state["symptom_state"] = symptom_state

    patient_state["last_updated"] = datetime.utcnow().isoformat()
    return patient_state
