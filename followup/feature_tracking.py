"""Track asked clinical dimensions (feature_id) to prevent same-topic repeats."""

from typing import Any, Dict, List


def get_feature_ids_asked(symptom_state: Dict) -> List[str]:
    if not isinstance(symptom_state, dict):
        return []
    ids = symptom_state.get("feature_ids_asked")
    if not isinstance(ids, list):
        return []
    return [str(item).strip() for item in ids if str(item).strip()]


def is_feature_already_asked(symptom_state: Dict, feature_id: str) -> bool:
    fid = str(feature_id or "").strip().lower()
    if not fid:
        return False
    return fid in {f.lower() for f in get_feature_ids_asked(symptom_state)}


def record_sent_question(symptom_state: Dict, question_payload: Dict[str, Any]) -> None:
    """Record question text and feature_id after a question is sent to the patient."""
    if not isinstance(symptom_state, dict) or not isinstance(question_payload, dict):
        return

    question_text = str(question_payload.get("Question", "")).strip()
    if question_text:
        asked = symptom_state.setdefault("questions_asked", [])
        if question_text not in asked:
            asked.append(question_text)

    feature_id = str(question_payload.get("feature_id", "")).strip()
    if feature_id:
        feature_ids = symptom_state.setdefault("feature_ids_asked", [])
        if feature_id not in feature_ids:
            feature_ids.append(feature_id)

    opts: List[str] = []
    for key in ("A", "B", "C", "D"):
        val = str(question_payload.get(key, "")).strip().lower()
        if val:
            opts.append(val)
    if len(opts) >= 3:
        sig = "|".join(sorted(opts))
        sigs = symptom_state.setdefault("_asked_option_sigs", [])
        if sig not in sigs:
            sigs.append(sig)
