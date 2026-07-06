"""
Maps a free-form clinical feature term to a canonical follow-up dimension.

Extracted from the old information_gain.py (which also did registry-backed
Bayesian scoring, now removed) because this specific mapping is a pure static
keyword table with no dependency on the disease dataset — it's still needed by
symptom_card.py to track which clinical dimensions a submitted card covered, so
the follow-up loop doesn't re-ask them.
"""

import re
from typing import Any

# Map a free-form disease feature term to a canonical follow-up dimension, so the
# selected finding dedups against symptom_state["feature_ids_asked"] and the LLM
# phrases a question about the right axis. Ordered specific → general; first hit
# wins. Unmapped terms fall back to a slug of the term (still trackable).
_TERM_DIMENSION = (
    (("leakage",), "urinary_symptoms"),
    (("incontinence",), "urinary_symptoms"),
    (("cough", "blood"), "sputum_hemoptysis"),
    (("hemoptysis",), "sputum_hemoptysis"),
    (("sputum",), "sputum_hemoptysis"),
    (("blood", "stool"), "blood_in_stool"),
    (("melena",), "blood_in_stool"),
    (("rectal", "bleed"), "blood_in_stool"),
    (("night", "sweat"), "night_sweats"),
    (("weight", "loss"), "weight_loss"),
    (("jaundice",), "jaundice"),
    (("appetite",), "appetite"),
    (("diarrhea",), "bowel_habits"),
    (("constipation",), "bowel_habits"),
    (("bowel",), "bowel_habits"),
    (("stool",), "bowel_habits"),
    (("nausea",), "nausea_vomiting"),
    (("vomit",), "nausea_vomiting"),
    (("breath",), "breathlessness"),
    (("chest", "pain"), "chest_pain"),
    (("palpitation",), "palpitations"),
    (("cough",), "cough"),
    (("fever",), "fever_pattern"),
    (("headache",), "headache"),
    (("vertigo",), "dizziness"),
    (("dizz",), "dizziness"),
    (("rash",), "rash"),
    (("joint",), "joint_pain"),
    (("lymph",), "lymphadenopathy"),
    (("node",), "lymphadenopathy"),
    (("dysuria",), "urinary_symptoms"),
    (("urin",), "urinary_symptoms"),
    (("radiat",), "pain_radiation"),
    (("burning",), "pain_quality"),
    (("crampy",), "pain_quality"),
    (("colicky",), "pain_quality"),
    (("quadrant",), "pain_location"),
    (("epigastr",), "pain_location"),
    (("abdomen",), "pain_location"),
    (("abdominal",), "pain_location"),
    (("flank",), "pain_location"),
    (("pelvic",), "pain_location"),
    (("duration",), "duration"),
    (("onset",), "onset"),
    (("sudden",), "onset"),
    (("travel",), "travel_history"),
    (("tuberculosis",), "tb_exposure"),
    (("contact",), "tb_exposure"),
    (("family",), "family_history"),
    (("menstru",), "menstrual_pregnancy"),
    (("pregnan",), "menstrual_pregnancy"),
    (("vaginal",), "menstrual_pregnancy"),
)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def term_to_dimension(term: str) -> str:
    """Map a clinical feature term to a canonical follow-up dimension."""
    t = _norm(term)
    if not t:
        return "other"
    for keywords, dimension in _TERM_DIMENSION:
        if all(k in t for k in keywords):
            return dimension
    slug = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return slug or "other"
