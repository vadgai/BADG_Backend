"""Shared follow-up flow constants."""

JACCARD_REPEAT_THRESHOLD = 0.72
OPTION_OVERLAP_THRESHOLD = 0.75

# The flow is 8-12 diagnostic "questions" (MCQs 1-6, midpoint symptom card as
# #7, MCQs 8-12). Early stop is allowed ONLY inside the 8-12 window:
#   - turn <  EARLY_STOP_MIN_QUESTIONS (8): never stop, regardless of
#     confidence — every session gathers at least 8 answers.
#   - turn >= EARLY_STOP_MIN_QUESTIONS: stop when the LLM signals ready
#     (can_stop_early), or autonomously when the tracked state is conclusive
#     (confidence_score >= EARLY_STOP_CONFIDENCE, top differential High,
#     runner-up Low — see followup.selection.should_stop_now), instead of
#     asking filler questions to reach 12.
#   - turn >= MAX: hard stop.
EARLY_STOP_MIN_QUESTIONS = 8
EARLY_STOP_CONFIDENCE = 0.85
MIN_FOLLOWUP_QUESTIONS = 8
MAX_FOLLOWUP_QUESTIONS = 12

# Canonical clinical dimensions a follow-up question can probe. The LLM must tag
# each question with ONE feature_id from this closed set, and dimensions already in
# symptom_state["feature_ids_asked"] are removed before prompting — so repetition is
# prevented by exact set-membership (no paraphrase leakage) and we no longer resend
# the full text of every prior question each turn. Keep clinically broad but compact.
FOLLOWUP_DIMENSIONS = (
    # onset & course
    "onset", "duration", "progression", "timing_pattern",
    # pain characterization
    "pain_location", "pain_migration", "pain_quality", "pain_severity",
    "pain_radiation", "aggravating_relieving",
    # constitutional / systemic
    "fever_pattern", "night_sweats", "weight_loss", "appetite", "fatigue",
    # gastrointestinal
    "bowel_habits", "blood_in_stool", "nausea_vomiting", "jaundice", "urinary_symptoms",
    # respiratory / cardiac
    "cough", "sputum_hemoptysis", "breathlessness", "chest_pain", "palpitations",
    # neuro / derm / msk
    "headache", "neuro_deficit", "dizziness", "rash", "joint_pain", "lymphadenopathy",
    # exposures & history
    "tb_exposure", "sick_contacts", "travel_history", "family_history",
    "comorbidities", "medications", "menstrual_pregnancy",
)

# Markers of lazy, non-differentiating filler questions. NOTE: keep genuine
# clinical topics (e.g. "breathing difficulty") OUT of this list — a targeted
# red-flag question like "new breathing difficulty at rest?" is legitimate and
# must not be rejected as generic. Only phrasings that carry no diagnostic
# specificity belong here.
GENERIC_QUESTION_MARKERS = (
    "getting worse",
    "can you share more details",
    "any other symptoms",
    "new or worsening symptoms",
    "symptom progression",
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
