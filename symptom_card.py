"""
Symptom selection cards that bracket the follow-up questionnaire.

Card 1 (stage="initial"): from the top-5 rule-engine candidates for the patient's
initial symptoms, surface the 7-10 highest-information-gain symptoms the patient
has NOT mentioned, plus key clinical-history factors (duration, smoking, alcohol,
past medical history, family history). The user multi-selects before follow-up.

Card 2 (stage="refined"): after the 12 follow-up questions, from the top-3
candidates, surface a second discriminating symptom set to confirm the narrowed
picture before the final 2-diagnosis analysis.

Selections merge into patient_state (selected -> positives, offered-but-unselected
-> negatives), so they flow into the existing rule-engine + report pipeline. Uses
the information-gain ranker so the card offers the MOST discriminating symptoms,
not arbitrary ones.
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Universal factors (asked regardless of the differential).
_BASE_FACTORS: List[Dict[str, Any]] = [
    {"key": "duration", "label": "How long have you had these symptoms?", "type": "single",
     "options": ["Less than 48 hours", "3-7 days", "2-4 weeks", "1-6 months", "More than 6 months"]},
    {"key": "smoking", "label": "Do you smoke or use tobacco?", "type": "single",
     "options": ["Never", "Former smoker", "Current smoker"]},
    {"key": "alcohol", "label": "Alcohol use?", "type": "single",
     "options": ["None", "Occasional", "Regular / heavy"]},
]

# Organ-system → relevant past-medical / family history. Makes the card adapt to
# the actual differential instead of always showing the same Cancer/TB/IBD list.
_SYSTEM_HISTORY: Dict[str, Dict[str, List[str]]] = {
    "respiratory": {"pmh": ["Asthma", "COPD", "Past TB", "Recurrent chest infections"],
                    "family": ["Asthma or allergies", "Tuberculosis"]},
    "cardiovascular": {"pmh": ["Hypertension", "Diabetes", "High cholesterol", "Prior heart disease"],
                       "family": ["Heart disease", "Stroke"]},
    "gastrointestinal": {"pmh": ["Acid reflux or ulcer", "Inflammatory bowel disease", "Prior abdominal surgery"],
                         "family": ["Colon cancer", "Inflammatory bowel disease"]},
    "hepatobiliary": {"pmh": ["Hepatitis", "Gallstones", "Heavy alcohol use"],
                      "family": ["Liver disease"]},
    "renal": {"pmh": ["Kidney disease", "Diabetes", "Recurrent urine infections"],
              "family": ["Kidney disease"]},
    "neurological": {"pmh": ["Migraine", "Seizures", "Prior stroke", "Hypertension"],
                     "family": ["Stroke", "Epilepsy"]},
    "endocrine": {"pmh": ["Diabetes", "Thyroid disorder"], "family": ["Diabetes", "Thyroid disorder"]},
    "infectious": {"pmh": ["Past TB", "HIV", "Recent travel"], "family": ["Tuberculosis"]},
    "musculoskeletal": {"pmh": ["Arthritis", "Prior injury"], "family": ["Arthritis", "Autoimmune disease"]},
}
_DEFAULT_HISTORY = {"pmh": ["Diabetes", "Hypertension", "Cancer", "Past TB"],
                    "family": ["Cancer", "Diabetes or heart disease", "Tuberculosis"]}

_STAGE_CONFIG = {
    "initial": {"top_k": 5, "limit": 10, "with_factors": True},
    "refined": {"top_k": 3, "limit": 8, "with_factors": False},
}

# Symptom-label cleaning for the card: collapse vague synonyms so near-duplicates
# (e.g. "Chest pain" / "Chest discomfort") dedup, and drop generic/verbose labels.
_SYMPTOM_SYNONYMS = {"discomfort": "pain", "ache": "pain", "aches": "pain", "soreness": "pain",
                     "tightness": "pain", "sob": "breath", "breathlessness": "breath",
                     "breathing": "breath", "breathe": "breath", "dyspnea": "breath"}
_SYMPTOM_STOP = {"of", "the", "a", "an", "and", "or", "with", "in", "on", "to", "mild", "new", "recent"}
_SYMPTOM_GENERIC = {"pain", "symptoms", "symptom", "malaise", "unwell", "illness", "feeling", "problem"}


def _title_case(term: str) -> str:
    term = str(term or "").strip()
    return term[:1].upper() + term[1:] if term else term


def _symptom_signature(label: str) -> frozenset:
    toks = [_SYMPTOM_SYNONYMS.get(t, t) for t in re.findall(r"[a-z0-9]+", label.lower())
            if t not in _SYMPTOM_STOP]
    return frozenset(toks)


def _clean_symptoms(findings: List[Dict[str, Any]], limit: int) -> List[Dict[str, str]]:
    """Dedup near-duplicates (synonym-aware), drop generic/verbose labels."""
    kept: List[Dict[str, str]] = []
    seen: List[frozenset] = []
    for f in findings:
        label = str(f.get("term", "")).strip()
        if not label or len(label.split()) > 5:  # skip verbose descriptive features
            continue
        sig = _symptom_signature(label)
        if not sig or sig <= _SYMPTOM_GENERIC:  # all-generic → skip
            continue
        # near-duplicate if a subset either way, or high token overlap
        if any(sig == s or sig <= s or s <= sig or len(sig & s) / max(1, len(sig | s)) >= 0.6 for s in seen):
            continue
        seen.append(sig)
        kept.append({"label": _title_case(label), "dimension": str(f.get("dimension", ""))})
        if len(kept) >= limit:
            break
    return kept


def _build_clinical_factors(organ_systems: List[str]) -> List[Dict[str, Any]]:
    """Base factors + past-medical/family-history tailored to the differential's organ systems."""
    pmh: List[str] = []
    fam: List[str] = []
    for osys in organ_systems or []:
        low = str(osys).lower()
        for key, hist in _SYSTEM_HISTORY.items():
            if key in low:
                for x in hist["pmh"]:
                    if x not in pmh:
                        pmh.append(x)
                for x in hist["family"]:
                    if x not in fam:
                        fam.append(x)
    if not pmh:
        pmh = list(_DEFAULT_HISTORY["pmh"])
    if not fam:
        fam = list(_DEFAULT_HISTORY["family"])
    return _BASE_FACTORS + [
        {"key": "past_medical_history", "label": "Any past medical conditions? (select all)",
         "type": "multi", "options": pmh[:6] + ["None"]},
        {"key": "family_history", "label": "Family history of major illness? (select all)",
         "type": "multi", "options": fam[:5] + ["None"]},
    ]


def generate_symptom_card(patient_state: Dict[str, Any], stage: str = "initial") -> Dict[str, Any]:
    """Build a symptom-selection card for the given stage."""
    cfg = _STAGE_CONFIG.get(stage, _STAGE_CONFIG["initial"])

    from followup.information_gain import rank_candidate_findings
    ranked = rank_candidate_findings(patient_state, top_k=cfg["top_k"], limit=cfg["limit"] + 6)

    symptoms: List[Dict[str, str]] = []
    top_conditions: List[str] = []
    organ_systems: List[str] = []
    if ranked:
        top_conditions = ranked.get("top_conditions", [])[: cfg["top_k"]]
        organ_systems = ranked.get("organ_systems", [])
        symptoms = _clean_symptoms(ranked.get("findings", []), cfg["limit"])

    clinical_factors = _build_clinical_factors(organ_systems) if cfg["with_factors"] else []

    return {
        "stage": stage,
        "top_conditions": top_conditions,
        "instruction": (
            "Select any symptoms you also have — this sharpens the analysis."
            if symptoms else "Continue to the follow-up questions."
        ),
        "symptoms": symptoms,
        "clinical_factors": clinical_factors,
    }


def _merge_unique(target: List[str], items: List[str]) -> None:
    existing = {str(t).strip().lower() for t in target if str(t).strip()}
    for item in items:
        key = str(item).strip().lower()
        if key and key not in existing:
            target.append(str(item).strip())
            existing.add(key)


# Clinical-factor answers that become findings the rule engine / report can use.
def _factor_findings(factors: Dict[str, Any]) -> List[str]:
    findings: List[str] = []
    smoking = str(factors.get("smoking", "")).strip().lower()
    if "current" in smoking or "former" in smoking:
        findings.append("smoking history")
    alcohol = str(factors.get("alcohol", "")).strip().lower()
    if "regular" in alcohol or "heavy" in alcohol:
        findings.append("alcohol use")
    for pmh in factors.get("past_medical_history", []) or []:
        val = str(pmh).strip().lower()
        if val and val != "none":
            findings.append(f"history of {val}")
    for fh in factors.get("family_history", []) or []:
        val = str(fh).strip().lower()
        if val and val != "none":
            findings.append(f"family history of {val}")
    return findings


def apply_symptom_card(
    patient_state: Dict[str, Any],
    offered: List[str],
    selected: List[str],
    factors: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge a submitted card into patient_state.

    - selected symptoms  -> identified_symptoms (positives)
    - offered-but-unselected -> negatives (patient implicitly denies them)
    - clinical factors -> stored on patient_state["clinical_history"], with
      actionable ones added as findings and their dimensions marked asked so the
      follow-up loop does not re-ask them.
    """
    if not isinstance(patient_state, dict):
        return patient_state

    from followup.information_gain import term_to_dimension

    offered = [str(o).strip() for o in (offered or []) if str(o).strip()]
    selected_set = {str(s).strip().lower() for s in (selected or []) if str(s).strip()}
    selected_terms = [o for o in offered if o.strip().lower() in selected_set]
    unselected_terms = [o for o in offered if o.strip().lower() not in selected_set]

    patient_state.setdefault("identified_symptoms", [])
    patient_state.setdefault("negatives", [])
    symptom_state = patient_state.get("symptom_state") if isinstance(patient_state.get("symptom_state"), dict) else {}
    symptom_state.setdefault("current_symptoms", [])
    symptom_state.setdefault("feature_ids_asked", [])
    symptom_state.setdefault("modifier_map", {})

    _merge_unique(patient_state["identified_symptoms"], selected_terms)
    _merge_unique(patient_state["negatives"], unselected_terms)

    factors = factors if isinstance(factors, dict) else {}
    _merge_unique(patient_state["identified_symptoms"], _factor_findings(factors))

    # Duration → modifier; store the full factor set for the report.
    duration = str(factors.get("duration", "")).strip()
    if duration:
        symptom_state["modifier_map"]["duration"] = duration
    patient_state["clinical_history"] = {**patient_state.get("clinical_history", {}), **factors}

    # Mark the dimensions this card covered so the follow-up loop won't re-ask them.
    covered_dims = {term_to_dimension(t) for t in offered}
    if duration:
        covered_dims.add("duration")
    if factors.get("family_history"):
        covered_dims.add("family_history")
    if factors.get("past_medical_history"):
        covered_dims.add("comorbidities")
    for dim in covered_dims:
        if dim and dim not in symptom_state["feature_ids_asked"]:
            symptom_state["feature_ids_asked"].append(dim)

    symptom_state["current_symptoms"] = list(patient_state["identified_symptoms"])
    patient_state["symptom_state"] = symptom_state
    return patient_state
