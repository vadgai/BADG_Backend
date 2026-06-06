"""
Agent 4 — Question Critic (rules-only gate before sending to patient).

Unifies repetition, generic, placeholder, and option-overlap checks.
"""

from typing import Any, Dict, List, Optional, Tuple

from followup.constants import GENERIC_QUESTION_MARKERS, OPTION_OVERLAP_THRESHOLD, PLACEHOLDER_MARKERS
from followup.validators.repetition import is_repeated_question, normalize_text


class QuestionCritic:
    """Stateful critic that tracks option fingerprints on symptom_state."""

    def __init__(self, symptom_state: Optional[Dict] = None):
        self.symptom_state = symptom_state if isinstance(symptom_state, dict) else {}

    def options_already_seen(self, question_obj: Dict) -> bool:
        opts = []
        for key in ("A", "B", "C", "D"):
            val = normalize_text(str(question_obj.get(key, "")))
            if val:
                opts.append(val)
        if len(opts) < 3:
            return False

        current_sig = "|".join(sorted(opts))
        seen_sigs = self.symptom_state.get("_asked_option_sigs", [])
        for sig in seen_sigs:
            sig_parts = set(sig.split("|"))
            cur_parts = set(current_sig.split("|"))
            overlap = len(sig_parts & cur_parts) / max(len(sig_parts | cur_parts), 1)
            if overlap >= OPTION_OVERLAP_THRESHOLD:
                return True
        return False

    def feature_already_asked(self, question_obj: Dict) -> bool:
        from followup.feature_tracking import is_feature_already_asked

        feature_id = str(question_obj.get("feature_id", "")).strip()
        if not feature_id:
            return False
        return is_feature_already_asked(self.symptom_state, feature_id)

    def validate(self, question_obj: Any, asked_questions: List[str]) -> bool:
        ok, _ = self.validate_with_reason(question_obj, asked_questions)
        return ok

    def validate_with_reason(self, question_obj: Any, asked_questions: List[str]) -> Tuple[bool, str]:
        if not isinstance(question_obj, dict):
            return False, "invalid_format"

        question_text = str(question_obj.get("Question", "")).strip()
        if not question_text:
            return False, "missing_question"

        combined = " ".join(
            str(question_obj.get(key, "")).strip().lower()
            for key in ("Question", "A", "B", "C", "D")
        )
        if not combined:
            return False, "placeholder"
        if any(marker in combined for marker in PLACEHOLDER_MARKERS):
            return False, "placeholder"
        if any(marker in normalize_text(question_text) for marker in GENERIC_QUESTION_MARKERS):
            return False, "generic"
        if is_repeated_question(question_text, asked_questions):
            return False, "repeated"
        if self.feature_already_asked(question_obj):
            return False, "feature_repeated"
        if self.options_already_seen(question_obj):
            return False, "options_repeated"

        options = [normalize_text(str(question_obj.get(key, ""))) for key in ("A", "B", "C")]
        if not all(options) or len(set(options)) < 3:
            return False, "non_distinct_options"

        return True, "ok"


def validate_question_payload(
    question_obj: Any,
    asked_questions: List[str],
    symptom_state: Optional[Dict] = None,
) -> bool:
    return QuestionCritic(symptom_state).validate(question_obj, asked_questions)
