"""MCQ JSON normalization and structural validation."""

from typing import Any, Dict


def normalize_mcq_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    out: Dict[str, Any] = dict(data)
    for key, value in list(data.items()):
        if not isinstance(key, str):
            continue
        low = key.lower()
        if low == "question":
            out["Question"] = str(value or "").strip()
        elif low in {"a", "b", "c", "d", "e"}:
            out[key.upper()] = str(value or "").strip() if value is not None else value

    if "Question" not in out:
        out["Question"] = str(data.get("Question") or data.get("question") or "").strip()

    for letter in ("A", "B", "C", "D", "E"):
        if letter not in out:
            low_val = data.get(letter.lower())
            if low_val is not None:
                out[letter] = str(low_val).strip()

    return out


def validate_mcq_structure(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    question = str(data.get("Question", "")).strip()
    options = [str(data.get(key, "")).strip() for key in ("A", "B", "C", "D")]
    return bool(question and all(options))
