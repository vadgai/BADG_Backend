"""
Diagnosis Rule Engine v5 — final diagnosis weighing.

Fully LLM-driven: no disease-registry scoring, no Bayesian posterior. The
patient's own accumulated differential (tracked turn-by-turn through the
follow-up loop by diagnosis_methods.state_followup.analyze_answer_for_state)
is the primary input; this module makes one finalizing LLM call over the full
evidence trail and returns the top-3 conditions with clinician-style reasoning.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from utils.gemini_api_manager import (
    generate_content_with_fallback,
    extract_json_from_text,
    get_gemini_model,
)

logger = logging.getLogger(__name__)


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


def _existing_differential(patient_state: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The differential the LLM has already been maintaining turn-by-turn."""
    if not isinstance(patient_state, dict):
        return []
    differential = patient_state.get("differential_diagnosis")
    if not isinstance(differential, list):
        return []
    out = []
    for item in differential:
        if isinstance(item, dict) and str(item.get("name", "")).strip():
            out.append(item)
    return out


def _fallback_from_differential(differential: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Used only if the finalizing LLM call itself fails — never an empty result
    when the follow-up loop already built a working differential."""
    normalized = []
    for item in differential[:3]:
        normalized.append(
            {
                "name": str(item.get("name", "")).strip(),
                "probability": str(item.get("confidence") or item.get("probability") or "Low").strip(),
                "reasoning": str(item.get("reasoning", "")).strip() or "Based on reported symptoms and history.",
                "urgency": str(item.get("urgency", "Routine")).strip() or "Routine",
            }
        )
    return {"conditions": normalized}


def _normalize_term_set(items: List[str]) -> set:
    values = set()
    for item in items:
        text = str(item or "").strip().lower()
        if text:
            values.add(text)
    return values


# Cues that mean a mentioned finding is being cited as RULED OUT, not claimed
# as present. Standard clinical reasoning routinely explains why competing
# diagnoses are less likely by naming the very findings the patient denied
# ("absence of vomiting", "patient denied a missed period") — that is correct,
# expected reasoning, not a hallucination, and must not be penalized.
_NEGATION_CUES = (
    "no ", "not ", "denies", "denied", "denying", "denial", "absence of",
    "absent", "without", "lack of", "lacks", "lacking", "ruled out",
    "rules out", "negative for", "no evidence of", "doesn't have",
    "does not have", "didn't have", "did not have", "excludes", "excluded",
    "unlikely given", "reports no", "free of", "no history of",
)


def _term_asserted_as_present(term: str, reasoning: str) -> bool:
    """True only if `term` appears in the reasoning WITHOUT a negation cue
    earlier in the same clause — i.e. the model is treating a denied finding
    as if it were present/supportive (a real hallucination), not correctly
    citing its absence to rule an alternative out. The window is wide enough
    to cover "denied X, Y, or Z" style comma-lists after a single cue, but
    stops at the start of the current clause (a preceding '.' or ';') so a
    cue from an unrelated, earlier sentence can't suppress a real hit."""
    idx = reasoning.find(term)
    if idx == -1:
        return False
    window = reasoning[max(0, idx - 100):idx]
    clause_start = max(window.rfind("."), window.rfind(";"))
    if clause_start != -1:
        window = window[clause_start + 1:]
    return not any(cue in window for cue in _NEGATION_CUES)


def _condition_supported_by_evidence(
    condition: Dict[str, Any],
    positives_text: set,
    negatives_text: set,
) -> bool:
    """Anti-hallucination guard: the LLM's stated reasoning must reference the
    patient's actual confirmed findings and must not claim a denied finding is
    present/supportive. There's no registry pool to check membership against
    anymore, so this is the sole safety net against an ungrounded diagnosis."""
    reasoning = str(condition.get("reasoning", "")).strip().lower()
    if not reasoning:
        return False
    if positives_text and not any(term in reasoning for term in positives_text):
        # No positives at all is unusual but not necessarily wrong (e.g. a
        # purely demographic/red-flag-driven consideration) — only reject when
        # we DO have positives and the reasoning cites none of them.
        return False
    if any(_term_asserted_as_present(term, reasoning) for term in negatives_text):
        return False
    return True


def _build_prompt(
    age: Any,
    gender: Any,
    positives: List[str],
    negatives: List[str],
    chat_history,
    differential: List[Dict[str, Any]],
    patient_state: Optional[Dict[str, Any]] = None,
) -> str:
    chat_history_text = _format_chat_history_brief(chat_history)
    positives_str = ", ".join(positives) if positives else "None reported"
    negatives_str = ", ".join(negatives) if negatives else "None reported"

    state_modifiers = "None"
    state_red_flags = "None"
    asked_count = 0
    running_summary_line = ""
    if isinstance(patient_state, dict):
        running_summary = patient_state.get("running_summary")
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
        if running_summary and str(running_summary).strip():
            running_summary_line = f"\nRunning clinical summary (built during the interview): {str(running_summary).strip()}"

    diff_lines = []
    for idx, item in enumerate(differential[:3], 1):
        name = item.get("name", "Unknown")
        confidence = item.get("confidence") or item.get("probability") or "Unknown"
        reasoning = str(item.get("reasoning", "")).strip()
        diff_lines.append(f"{idx}. {name} ({confidence}) — {reasoning[:150]}")
    diff_text = "\n".join(diff_lines) if diff_lines else "No working differential yet — build one from the evidence below."

    return f"""Expert clinical diagnostician doing the FINAL diagnostic weighing at the end of a patient interview. You have been reasoning about this case turn-by-turn already; this is your final, most careful pass over the full evidence. Output JSON only.

Patient: {age}/{gender}
+Findings (confirmed): {positives_str}
-Findings (denied): {negatives_str}
Modifiers: {state_modifiers}
Red flags: {state_red_flags}
Questions asked: {asked_count}{running_summary_line}

Q&A history:
{chat_history_text}

Your working differential from the interview so far:
{diff_text}

TASK:
1) Rank the TOP 3 conditions using standard clinical reasoning — you are not constrained to any predefined list, use your own medical knowledge. You may keep, reorder, or replace entries from your working differential above if the full evidence now supports something more specific or more likely.
2) Every condition's reasoning MUST explicitly reference the patient's actual confirmed (+) findings and MUST NOT be contradicted by a denied (-) finding — never invent a symptom not listed above.
3) Per condition: probability using this exact rubric — High (you'd estimate >=70% likely given this evidence), Moderate (50-70%), Low (<50%) — 1-2 sentence reasoning anchored to (+)/(-)/modifiers/red flags, urgency (Emergency/Routine/Monitor).
4) Use the Q&A history for refinement (exact wording, negatives, progression, chronicity — a chronic multi-week course with weight loss/night sweats argues against acute conditions).
4b) WEIGHT BY SPECIFICITY: a hallmark/near-specific finding (pain behind the eyes → dengue over chikungunya; right-shoulder radiation + fatty-food trigger → gallbladder; fixed-station morning cough in a smoker → COPD) outweighs a nonspecific symptom the top candidates share (fever, body ache, joint pain). Do not let a single shared symptom decide #1. Do NOT assign a chronic/inflammatory label (e.g. "chronic cholecystitis", "chronic pancreatitis") unless an inflammatory sign is present (fever, tenderness, raised markers) — recurrent episodes without inflammation stay the simpler diagnosis (e.g. biliary colic / symptomatic gallstones).
5) Name the MOST SPECIFIC diagnosis the evidence supports, never a broad category (e.g. "Pulmonary tuberculosis" not "Respiratory infection"; "Acute appendicitis" not "Abdominal pathology"; "Generalized Anxiety Disorder" not "Stress").
6) If red flags are present, urgency must be Emergency and this must be reflected in probability/ordering.

Return JSON only:
{{
  "diagnosis_summary": "Short summary.",
  "conditions": [
    {{"name": "...", "probability": "High|Moderate|Low", "reasoning": "...", "urgency": "Emergency|Routine|Monitor"}},
    {{"name": "...", "probability": "High|Moderate|Low", "reasoning": "...", "urgency": "Emergency|Routine|Monitor"}},
    {{"name": "...", "probability": "High|Moderate|Low", "reasoning": "...", "urgency": "Emergency|Routine|Monitor"}}
  ]
}}
"""


def _normalize_conditions(
    data: Dict[str, Any],
    fallback: Dict[str, Any],
    positives: List[str],
    negatives: List[str],
) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return fallback

    raw_conditions = data.get("conditions")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        return fallback

    positive_terms = _normalize_term_set(positives)
    negative_terms = _normalize_term_set(negatives)

    normalized: List[Dict[str, Any]] = []
    seen_names = set()
    for cond in raw_conditions:
        if not isinstance(cond, dict):
            continue
        name = str(cond.get("name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen_names:
            continue
        if not _condition_supported_by_evidence(cond, positive_terms, negative_terms):
            logger.info("get_final_diagnosis_v5: rejected ungrounded suggestion %r", name)
            continue
        seen_names.add(key)
        normalized.append(
            {
                "name": name,
                "probability": str(cond.get("probability", "Low")).strip() or "Low",
                "reasoning": str(cond.get("reasoning", "")).strip() or "Based on reported symptoms and history.",
                "urgency": str(cond.get("urgency", "Routine")).strip() or "Routine",
            }
        )
        if len(normalized) >= 3:
            break

    if not normalized:
        return fallback

    result: Dict[str, Any] = {"conditions": normalized}
    if "diagnosis_summary" in data:
        result["diagnosis_summary"] = str(data.get("diagnosis_summary", "")).strip()
    return result


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
    Final weighing pipeline — fully LLM-driven, no disease-registry scoring.

    The follow-up loop already builds and refines a differential turn-by-turn
    (patient_state["differential_diagnosis"], maintained by
    diagnosis_methods.state_followup.analyze_answer_for_state). This makes one
    last, most-careful LLM pass over the complete evidence trail to produce the
    final top-3, anchored only to the patient's own confirmed/denied findings —
    never to a hardcoded disease dataset.
    """
    del weight, height, occupation, location, physical_activity, diet_type  # unused here; kept for call-site compatibility

    positives: List[str] = []
    if isinstance(symptoms, list):
        positives = [str(s).strip() for s in symptoms if str(s).strip()]
    elif symptoms:
        positives = [str(symptoms).strip()]

    negatives_list = negatives if isinstance(negatives, list) else []

    differential = _existing_differential(patient_state)
    fallback = _fallback_from_differential(differential) if differential else {"conditions": []}

    model_ok, _ = get_gemini_model()
    if not model_ok:
        return fallback

    prompt = _build_prompt(
        age=age,
        gender=gender,
        positives=positives,
        negatives=negatives_list,
        chat_history=chat_history,
        differential=differential,
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
            positives=positives,
            negatives=negatives_list,
        )
        normalized_conditions = normalized.get("conditions") if isinstance(normalized, dict) else None
        if not isinstance(normalized_conditions, list) or not normalized_conditions:
            return fallback
        return normalized
    except Exception as exc:
        logger.warning("get_final_diagnosis_v5: error: %s", exc)
        return fallback
