"""
Diagnosis Rule Engine v5
Final weighing: combines rule-based matching with LLM refinement.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from diagnosis_rule_engine import (
    load_diseases_from_folder,
    build_disease_profiles,
    analyze_case,
)
from utils.gemini_api_manager import (
    generate_content_with_fallback,
    extract_json_from_text,
    get_gemini_model,
)

logger = logging.getLogger(__name__)

_PROFILES_READY = False
_DIAG_V6_SCORER = str(os.getenv("DIAG_V6_SCORER", "true")).strip().lower() in {"1", "true", "yes", "on"}


def _ensure_profiles_loaded() -> None:
    global _PROFILES_READY
    if _PROFILES_READY:
        return
    load_diseases_from_folder()
    build_disease_profiles()
    _PROFILES_READY = True


def _format_chat_history(chat_history) -> str:
    if not chat_history:
        return "No previous questions asked."

    if isinstance(chat_history, str):
        try:
            parsed = json.loads(chat_history)
            chat_history = parsed
        except Exception:
            return chat_history.strip() or "No previous questions asked."

    if isinstance(chat_history, list):
        lines: List[str] = []
        q_idx = 0
        for i, msg in enumerate(chat_history):
            if not isinstance(msg, dict):
                continue
            bot_text = msg.get("bot") or msg.get("Question")
            if bot_text:
                q_idx += 1
                lines.append(f"Q{q_idx}: {str(bot_text).strip()}")
                if i + 1 < len(chat_history):
                    next_msg = chat_history[i + 1]
                    if isinstance(next_msg, dict) and next_msg.get("user"):
                        lines.append(f"A{q_idx}: {str(next_msg.get('user')).strip()}")
        return "\n".join(lines) if lines else "No previous questions asked."

    return str(chat_history).strip() or "No previous questions asked."


def _normalize_conditions(
    data: Dict[str, Any],
    fallback: Dict[str, Any],
    candidate_pool: Optional[List[Dict[str, Any]]] = None,
    positives: Optional[List[str]] = None,
    negatives: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return fallback

    raw_conditions = data.get("conditions")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        return fallback

    candidate_pool = candidate_pool or []
    candidate_by_name = {
        str(item.get("name", "")).strip().lower(): item
        for item in candidate_pool
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    }
    positives = positives or []
    negatives = negatives or []

    normalized: List[Dict[str, Any]] = []
    for cond in raw_conditions:
        if not isinstance(cond, dict):
            continue
        name = str(cond.get("name", "")).strip()
        if not name:
            continue
        probability = str(cond.get("probability", "Low")).strip() or "Low"
        reasoning = str(cond.get("reasoning", "")).strip() or "Based on reported symptoms and history."
        urgency = str(cond.get("urgency", "Routine")).strip() or "Routine"
        candidate_entry = candidate_by_name.get(name.lower())
        is_supported = _condition_supported_by_evidence(
            {"name": name, "reasoning": reasoning},
            positives=positives,
            negatives=negatives,
            candidate_by_name=candidate_by_name,
        )
        if not is_supported:
            continue
        normalized.append(
            {
                "name": name,
                "probability": probability,
                "reasoning": reasoning,
                "urgency": urgency,
                "score": candidate_entry.get("score") if isinstance(candidate_entry, dict) else None,
                "score_details": candidate_entry.get("score_details") if isinstance(candidate_entry, dict) else {},
            }
        )
        if len(normalized) >= 3:
            break

    if not normalized:
        return fallback

    result: Dict[str, Any] = {"conditions": normalized}
    if "diagnosis_summary" in data:
        result["diagnosis_summary"] = str(data.get("diagnosis_summary", "")).strip()
    if "accuracy_warning" in data:
        result["accuracy_warning"] = str(data.get("accuracy_warning", "")).strip()
    if "follow_up_questions" in data and isinstance(data.get("follow_up_questions"), list):
        result["follow_up_questions"] = data.get("follow_up_questions")
    return result


def _fallback_from_rule(rule_result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(rule_result, dict):
        return {"conditions": []}

    conditions = rule_result.get("conditions")
    if not isinstance(conditions, list):
        return {"conditions": []}

    normalized: List[Dict[str, Any]] = []
    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        name = str(cond.get("name", "")).strip()
        if not name:
            continue
        normalized.append(
            {
                "name": name,
                "probability": str(cond.get("probability", "Low")).strip() or "Low",
                "reasoning": str(cond.get("reasoning", "")).strip() or "Based on reported symptoms.",
                "urgency": str(cond.get("urgency", "Routine")).strip() or "Routine",
                "score": cond.get("score"),
                "score_details": cond.get("score_details") if isinstance(cond.get("score_details"), dict) else {},
            }
        )
        if len(normalized) >= 3:
            break

    return {"conditions": normalized}


def _normalize_term_set(items: List[str]) -> set:
    values = set()
    for item in items:
        text = re.sub(r"\s+", " ", str(item or "").strip().lower())
        if text:
            values.add(text)
    return values


def _extract_candidate_pool(rule_result: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    if not isinstance(rule_result, dict):
        return []
    candidates = rule_result.get("conditions")
    if not isinstance(candidates, list):
        return []
    out: List[Dict[str, Any]] = []
    for condition in candidates:
        if not isinstance(condition, dict):
            continue
        name = str(condition.get("name", "")).strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "probability": str(condition.get("probability", "Low")).strip() or "Low",
                "score": condition.get("score"),
                "score_details": condition.get("score_details") if isinstance(condition.get("score_details"), dict) else {},
                "reasoning": str(condition.get("reasoning", "")).strip(),
                "urgency": str(condition.get("urgency", "Routine")).strip() or "Routine",
            }
        )
        if len(out) >= limit:
            break
    return out


def _condition_supported_by_evidence(
    condition: Dict[str, Any],
    positives: List[str],
    negatives: List[str],
    candidate_by_name: Dict[str, Dict[str, Any]],
) -> bool:
    name = str(condition.get("name", "")).strip()
    if not name:
        return False
    in_pool = name.lower() in candidate_by_name
    reasoning = str(condition.get("reasoning", "")).strip().lower()
    positive_terms = _normalize_term_set(positives)
    negative_terms = _normalize_term_set(negatives)
    detail = candidate_by_name.get(name.lower(), {})
    score_details = detail.get("score_details") if isinstance(detail.get("score_details"), dict) else {}
    contrad = set(str(x).strip().lower() for x in score_details.get("contradicted_features", []))
    exclude_hits = set(str(x).strip().lower() for x in score_details.get("exclude_hits", []))

    if in_pool and not exclude_hits:
        return True
    if in_pool and exclude_hits and positive_terms.intersection(exclude_hits):
        return False

    # Out-of-pool suggestion can pass only if reasoning references concrete positives and avoids negatives.
    if not in_pool:
        if not any(term in reasoning for term in positive_terms):
            return False
        if any(term in reasoning for term in negative_terms):
            return False
        return True

    if contrad and positive_terms.intersection(contrad):
        return False
    return True


def _format_chat_history_brief(chat_history) -> str:
    """Format Q&A history into a compact string for the diagnosis weighing prompt."""
    if not isinstance(chat_history, list) or not chat_history:
        return "No Q&A history."
    lines = []
    turn = 0
    for msg in chat_history:
        if not isinstance(msg, dict):
            continue
        bot_q = str(msg.get("bot") or "").strip()
        user_a = str(msg.get("user") or "").strip()
        if bot_q and user_a:
            turn += 1
            lines.append(f"Q{turn}: {bot_q[:80]} → A: {user_a[:60]}")
    return "\n".join(lines) if lines else "No Q&A history."


def _build_prompt(
    age: Any,
    gender: Any,
    positives: List[str],
    negatives: List[str],
    chat_history,
    rule_context: Dict[str, Any],
    candidate_pool: List[Dict[str, Any]],
    patient_state: Optional[Dict[str, Any]] = None,
) -> str:
    # Fix H: format chat_history instead of discarding it
    chat_history_text = _format_chat_history_brief(chat_history)
    positives_str = ", ".join(positives) if positives else "None reported"
    negatives_str = ", ".join(negatives) if negatives else "None reported"

    rule_lines = []
    for idx, cond in enumerate(rule_context.get("conditions", [])[:3], 1):
        name = cond.get("name", "Unknown")
        prob = cond.get("probability", "Unknown")
        rule_lines.append(f"{idx}. {name} ({prob})")
    rule_context_text = "\n".join(rule_lines) if rule_lines else "None"

    state_summary = ""
    state_modifiers = "None"
    state_red_flags = "None"
    asked_count = 0
    if isinstance(patient_state, dict):
        running_summary = patient_state.get("running_summary")
        differential = patient_state.get("differential_diagnosis")
        symptom_state = patient_state.get("symptom_state") if isinstance(patient_state.get("symptom_state"), dict) else {}
        modifier_map = symptom_state.get("modifier_map") if isinstance(symptom_state.get("modifier_map"), dict) else {}
        modifiers = symptom_state.get("modifiers") if isinstance(symptom_state.get("modifiers"), list) else []
        red_flags = symptom_state.get("red_flags") if isinstance(symptom_state.get("red_flags"), list) else patient_state.get("red_flags", [])
        asked = symptom_state.get("questions_asked") if isinstance(symptom_state.get("questions_asked"), list) else []
        if modifier_map:
            kv_items = [f"{k}:{v}" for k, v in modifier_map.items() if str(v).strip()]
            state_modifiers = ", ".join(kv_items) if kv_items else "None"
        else:
            state_modifiers = ", ".join(str(m).strip() for m in modifiers if str(m).strip()) or "None"
        state_red_flags = ", ".join(str(r).strip() for r in red_flags if str(r).strip()) or "None"
        asked_count = len(asked)
        if running_summary:
            state_summary += f"\nRunning summary: {running_summary}"
        if isinstance(differential, list) and differential:
            ddx_lines = []
            for idx, item in enumerate(differential[:3], 1):
                name = item.get("name", "Unknown")
                confidence = item.get("confidence", "Unknown")
                ddx_lines.append(f"{idx}. {name} ({confidence})")
            state_summary += "\nRecent differential: " + "; ".join(ddx_lines)

    # Fix J: build a human-readable evidence trace for each candidate
    candidate_lines = []
    for idx, cand in enumerate(candidate_pool[:6], 1):
        name = cand.get("name", "Unknown")
        prob = cand.get("probability", "?")
        score_details = cand.get("score_details") if isinstance(cand.get("score_details"), dict) else {}
        matched = score_details.get("matched_positive_features", [])[:5]
        contradicted = score_details.get("contradicted_features", [])[:3]
        excluded = score_details.get("exclude_hits", [])[:2]
        reasoning = str(cand.get("reasoning", "")).strip()[:100]
        evidence_line = f"{idx}. {name} ({prob})"
        if matched:
            evidence_line += f"\n   + Evidence: {', '.join(matched)}"
        if contradicted:
            evidence_line += f"\n   - Contradicted by: {', '.join(contradicted)}"
        if excluded:
            evidence_line += f"\n   ! Exclude-hit conflict: {', '.join(excluded)}"
        if reasoning:
            evidence_line += f"\n   Reasoning: {reasoning}"
        candidate_lines.append(evidence_line)
    candidate_context_text = "\n".join(candidate_lines) if candidate_lines else "None"

    return f"""Expert clinical diagnostician doing final diagnostic weighing. The deterministic ranking is primary truth; reorder only when evidence clearly supports it. Output JSON only.

Patient: {age}/{gender}
+Findings: {positives_str}
-Findings: {negatives_str}
Modifiers: {state_modifiers}
Red flags: {state_red_flags}
Questions asked: {asked_count}

Q&A history:
{chat_history_text}

Rule-based matches:
{rule_context_text}
{state_summary}

Candidate pool with evidence trace:
{candidate_context_text}

TASK:
1) Rank the TOP 3 conditions, reordering only within the candidate pool.
2) Allow an out-of-pool condition ONLY if explicitly supported by positives/modifiers/red flags and not contradicted by negatives.
3) Per condition: probability (High/Moderate/Low), 1-2 sentence reasoning anchored to (+)/(-)/modifiers/red flags and consistent with the probability, urgency (Emergency/Routine/Monitor).
4) Use the Q&A history for refinement (exact wording, negatives, progression).

Return JSON only:
{{
  "diagnosis_summary": "Short summary.",
  "conditions": [
    {{"name": "...", "probability": "High|Moderate|Low", "reasoning": "...", "urgency": "Emergency|Routine|Monitor"}},
    {{"name": "...", "probability": "High|Moderate|Low", "reasoning": "...", "urgency": "Emergency|Routine|Monitor"}},
    {{"name": "...", "probability": "High|Moderate|Low", "reasoning": "...", "urgency": "Emergency|Routine|Monitor"}}
  ],
  "follow_up_questions": [],
  "override": {{"used": false, "condition": "", "reason": ""}}
}}
"""


def get_final_diagnosis_v5(
    age: Any,
    gender: Any,
    symptoms: Any,
    chat_history,
    negatives: Optional[List[str]] = None,
    weight: Optional[float] = None,
    height: Optional[float] = None,
    occupation: Optional[str] = None,
    location: Optional[Dict[str, Any]] = None,
    physical_activity: Optional[str] = None,
    diet_type: Optional[str] = None,
    patient_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Final weighing pipeline:
    - Rule-based scoring from disease registry
    - LLM refinement using structured symptom state (+/- findings and red flags)
    """
    _ensure_profiles_loaded()

    positives: List[str] = []
    if isinstance(symptoms, list):
        positives = [str(s).strip() for s in symptoms if str(s).strip()]
    elif symptoms:
        positives = [str(symptoms).strip()]

    negatives_list = negatives if isinstance(negatives, list) else []

    symptom_state = patient_state.get("symptom_state") if isinstance(patient_state, dict) and isinstance(patient_state.get("symptom_state"), dict) else {}
    red_flags = symptom_state.get("red_flags") if isinstance(symptom_state.get("red_flags"), list) else []
    modifiers = symptom_state.get("modifier_map") if isinstance(symptom_state.get("modifier_map"), dict) else symptom_state.get("modifiers")

    rule_result = analyze_case(
        age=age,
        gender=gender,
        symptoms=positives,
        chat_history="No raw chat history used. Structured state only.",
        weight=weight,
        height=height,
        negatives=negatives_list,
        modifiers=modifiers,
        red_flags=red_flags if isinstance(red_flags, list) else [],
    )

    # Primary ranking = the belief-state posterior (the SAME distribution that drove
    # the follow-up questions, and which factors in duration/lifestyle/history), so
    # the final report is consistent with the loop. Falls back to the raw rule
    # ranking if the belief state can't be built (e.g. no structured positives).
    belief = None
    if isinstance(patient_state, dict):
        try:
            from followup.information_gain import rank_final_diagnoses
            belief = rank_final_diagnoses(patient_state, limit=3)
        except Exception as exc:
            logger.warning("get_final_diagnosis_v5: belief ranking failed: %s", exc)
    if belief and belief.get("conditions"):
        fallback = {"conditions": belief["conditions"]}
        candidate_pool = _extract_candidate_pool(fallback)
    else:
        fallback = _fallback_from_rule(rule_result)
        candidate_pool = _extract_candidate_pool(rule_result)

    if not _DIAG_V6_SCORER:
        return fallback

    model_ok, _ = get_gemini_model()
    if not model_ok:
        return fallback

    prompt = _build_prompt(
        age=age,
        gender=gender,
        positives=positives,
        negatives=negatives_list,
        chat_history=chat_history,
        rule_context=fallback,
        candidate_pool=candidate_pool,
        patient_state=patient_state,
    )

    try:
        success, text, error = generate_content_with_fallback(
            prompt=prompt,
            max_retries=None,
            temperature=0.3,
            max_output_tokens=900,
        )
        if not success or not text:
            logger.warning("get_final_diagnosis_v5: generation failed: %s", error)
            return fallback

        parsed = extract_json_from_text(text)
        normalized = _normalize_conditions(
            parsed,
            fallback,
            candidate_pool=candidate_pool,
            positives=positives,
            negatives=negatives_list,
        )
        normalized_conditions = normalized.get("conditions") if isinstance(normalized, dict) else None
        if not isinstance(normalized_conditions, list) or not normalized_conditions:
            return fallback
        candidate_names = {str(c.get("name", "")).strip().lower() for c in candidate_pool if isinstance(c, dict)}
        normalized_names = {str(c.get("name", "")).strip().lower() for c in normalized_conditions if isinstance(c, dict)}
        raw_names = set()
        if isinstance(parsed, dict) and isinstance(parsed.get("conditions"), list):
            for cond in parsed.get("conditions"):
                if isinstance(cond, dict):
                    nm = str(cond.get("name", "")).strip().lower()
                    if nm:
                        raw_names.add(nm)
        rejected_out_of_pool = [nm for nm in raw_names if nm not in candidate_names and nm not in normalized_names]
        if rejected_out_of_pool and isinstance(patient_state, dict):
            counters = patient_state.setdefault("diagnostic_counters", {})
            counters["out_of_pool_llm_suggestion_rejections"] = int(counters.get("out_of_pool_llm_suggestion_rejections", 0) or 0) + len(rejected_out_of_pool)
        return normalized
    except Exception as exc:
        logger.warning("get_final_diagnosis_v5: error: %s", exc)
        return fallback
