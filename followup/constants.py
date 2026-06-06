"""Shared follow-up flow constants."""

JACCARD_REPEAT_THRESHOLD = 0.72
OPTION_OVERLAP_THRESHOLD = 0.75

MIN_FOLLOWUP_QUESTIONS = 4
MAX_FOLLOWUP_QUESTIONS = 12

GENERIC_QUESTION_MARKERS = (
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
    "share more details",
)

PLACEHOLDER_MARKERS = (
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
)
