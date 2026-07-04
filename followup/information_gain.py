"""
Expected Information Gain (EIG) question selection over a Bayesian belief state.

Instead of asking the LLM "what should I ask next?", this module computes a
probability distribution over the live differential and picks the unasked finding
whose answer would most reduce diagnostic uncertainty (entropy) — the way an
experienced clinician prioritizes questions.

Design (all derived from data already in diseases/*.json — no new data needed):
  - Belief state: naive-Bayes posterior P(disease | findings) over the rule
    engine's top-K candidates, using each disease's feature buckets as likelihoods.
  - EIG(feature) = H(posterior) − E_answer[ H(posterior | answer) ].
  - Selection = argmax EIG over unasked clinical dimensions.
  - Early stop when the posterior concentrates (low entropy / high top mass).

This module is defensive: any failure returns None so the live follow-up flow
falls back to the existing strategist/writer behavior. It costs ~0 LLM tokens
(pure computation); the LLM only phrases the selected dimension into an MCQ.
"""

import logging
import math
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# --- Tunable constants (validate/adjust via tests/eval_information_gain.py) -----
TOP_K = 6                     # candidate diagnoses the belief state ranges over
CONFIDENCE_STOP = 0.85        # stop if the top posterior exceeds this
ENTROPY_STOP = 0.45           # ...or if entropy (nats) drops below this

# P(finding present | disease) by which bucket the disease lists the finding in.
_BUCKET_PROB = {"key": 0.85, "supportive": 0.50, "rare": 0.20}
_ABSENT_PROB = 0.10           # finding not in the disease profile at all
_EXCLUDE_PROB = 0.03          # finding is an exclude-feature for this disease
_PREVALENCE_PRIOR = {"common": 1.0, "unknown": 0.5, "rare": 0.25}

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


def _term_present(term: str, feature_term: str) -> bool:
    """Whole-word match between a patient term and a disease feature term."""
    from diagnosis_rule_engine import _terms_match
    return _terms_match(term, feature_term)


def _p_present_given_disease(term: str, profile: Dict[str, Any]) -> float:
    """Likelihood P(finding present | disease) from the disease's feature buckets."""
    feats = profile.get("features", {}) if isinstance(profile.get("features"), dict) else {}
    for f in feats.get("exclude", []) or []:
        if _term_present(term, str(f.get("term", ""))):
            return _EXCLUDE_PROB
    for bucket in ("key", "supportive", "rare"):
        for f in feats.get(bucket, []) or []:
            if _term_present(term, str(f.get("term", ""))):
                return _BUCKET_PROB[bucket]
    return _ABSENT_PROB


# Acuity gating: diseases whose names mark them as inherently chronic vs acute.
# Used with the patient's reported symptom DURATION so a weeks/months course
# down-weights strictly acute conditions (e.g. appendicitis) and a <48h course
# down-weights chronic ones (gently — chronic disease can present acutely).
_CHRONIC_NAME_HINTS = (
    "chronic", "cancer", "malignan", "tumor", "tuberculosis", "tb)", "diabetes",
    "cirrhosis", "fibrosis", "crohn", "colitis", "inflammatory bowel", "arthritis",
    "hypothyroid", "hyperthyroid", "copd", "asthma", "hypertension", "anemia",
    "kidney disease", "heart failure", "hepatitis b", "hepatitis c", "hiv", "silicosis",
)
_ACUTE_NAME_HINTS = (
    "acute", "appendicitis", "infarction", "stroke", "embolism", "pneumothorax",
    "rupture", "torsion", "anaphylaxis", "gastroenteritis", "food poisoning",
    "influenza", "common cold",
)


def _duration_bucket(patient_state_extra: Dict[str, Any]) -> str:
    """Classify reported duration into acute (<1wk) / subacute / chronic (>4wk) / unknown."""
    text = _norm(patient_state_extra.get("duration"))
    if not text:
        return "unknown"
    if any(k in text for k in ("hour", "48", "less than 2 day", "1 day", "2 day", "yesterday", "today")):
        return "acute"
    if any(k in text for k in ("3-7 day", "week1", "one week", "a week", "few day", "day")):
        # "3-7 days" and generic day-counts → still acute-leaning
        return "acute"
    if any(k in text for k in ("2-4 week", "2 week", "3 week", "4 week")):
        return "subacute"
    if any(k in text for k in ("month", "year", "more than 6", "1-6", "chronic", "long")):
        return "chronic"
    return "unknown"


def _disease_acuity(profile: Dict[str, Any]) -> str:
    name = _norm(profile.get("name"))
    if any(h in name for h in _CHRONIC_NAME_HINTS):
        return "chronic"
    if any(h in name for h in _ACUTE_NAME_HINTS):
        return "acute"
    return "either"


def _risk_terms_from_state(extra: Dict[str, Any]) -> List[str]:
    """Patient risk/lifestyle facts as matchable terms (smoking, alcohol, histories)."""
    terms: List[str] = []
    if "current" in _norm(extra.get("smoking")) or "former" in _norm(extra.get("smoking")):
        terms.append("smoking")
    if "regular" in _norm(extra.get("alcohol")) or "heavy" in _norm(extra.get("alcohol")):
        terms.append("alcohol")
    for key in ("past_medical_history", "family_history"):
        vals = extra.get(key)
        if isinstance(vals, list):
            for v in vals:
                v = _norm(v)
                if v and v != "none":
                    terms.append(v)
    return terms


def _prior(
    profile: Dict[str, Any],
    age: Optional[int],
    gender: Optional[str],
    extra: Optional[Dict[str, Any]] = None,
) -> float:
    """Pretest probability: prevalence × demographics × duration-acuity × risk factors."""
    p = _PREVALENCE_PRIOR.get(_norm(profile.get("prevalence")) or "unknown", 0.5)
    rf = profile.get("risk_factors", {}) if isinstance(profile.get("risk_factors"), dict) else {}
    age_ranges = rf.get("age_ranges") or rf.get("age_range") or []
    if age is not None and age_ranges:
        try:
            in_range = any(lo <= int(age) <= hi for (lo, hi) in age_ranges)
            p *= 1.3 if in_range else 0.6
        except (TypeError, ValueError):
            pass
    genders = [_norm(g) for g in (rf.get("gender") or [])]
    g = _norm(gender)
    restricted = {x for x in genders if x in {"male", "female"}}
    if g and len(restricted) == 1:
        p *= 1.2 if g in restricted else 0.4

    extra = extra if isinstance(extra, dict) else {}

    # Duration ↔ disease acuity (an experienced clinician's first filter).
    bucket = _duration_bucket(extra)
    acuity = _disease_acuity(profile)
    if bucket == "chronic" and acuity == "acute":
        p *= 0.35
    elif bucket == "acute" and acuity == "chronic":
        p *= 0.6   # gentler: chronic disease can present acutely
    elif bucket == "subacute" and acuity == "acute":
        p *= 0.7
    elif bucket != "unknown" and acuity != "either" and bucket[:2] == acuity[:2]:
        p *= 1.25  # course matches the disease's natural history

    # Risk factors / lifestyle (smoking, alcohol, past/family history) raise the
    # disease classes they predispose to.
    name = _norm(profile.get("name"))
    for rt in _risk_terms_from_state(extra):
        if rt == "smoking" and any(h in name for h in ("cancer", "malignan", "carcinoma", "copd", "bronchitis", "lung")):
            p *= 1.4
        elif rt == "alcohol" and any(h in name for h in ("liver", "hepat", "cirrhosis", "pancreat", "gastritis")):
            p *= 1.3
        elif rt not in ("smoking", "alcohol") and (rt in name or name in rt):
            p *= 1.6  # explicit past/family history of this condition
    return max(1e-3, p)


def _entropy(probs: List[float]) -> float:
    return -sum(p * math.log(p) for p in probs if p > 0.0)


def _posterior(
    profiles: List[Dict[str, Any]],
    positives: List[str],
    negatives: List[str],
    age: Optional[int],
    gender: Optional[str],
    extra: Optional[Dict[str, Any]] = None,
) -> List[float]:
    """Naive-Bayes posterior over the candidate profiles (log-space + softmax)."""
    log_probs: List[float] = []
    for prof in profiles:
        lp = math.log(_prior(prof, age, gender, extra))
        for term in positives:
            lp += math.log(_p_present_given_disease(term, prof))
        for term in negatives:
            lp += math.log(max(1e-3, 1.0 - _p_present_given_disease(term, prof)))
        log_probs.append(lp)
    m = max(log_probs)
    exps = [math.exp(lp - m) for lp in log_probs]
    total = sum(exps) or 1.0
    return [e / total for e in exps]


def _expected_info_gain(profiles: List[Dict[str, Any]], posterior: List[float], term: str) -> float:
    """H(posterior) − E_answer[H(posterior | answer)] for a binary present/absent finding."""
    likelihoods = [_p_present_given_disease(term, prof) for prof in profiles]
    p_present = sum(pd * lh for pd, lh in zip(posterior, likelihoods))
    p_present = min(max(p_present, 1e-6), 1.0 - 1e-6)

    yes = [pd * lh for pd, lh in zip(posterior, likelihoods)]
    no = [pd * (1.0 - lh) for pd, lh in zip(posterior, likelihoods)]
    sy = sum(yes) or 1.0
    sn = sum(no) or 1.0
    yes = [v / sy for v in yes]
    no = [v / sn for v in no]

    h_now = _entropy(posterior)
    h_expected = p_present * _entropy(yes) + (1.0 - p_present) * _entropy(no)
    return h_now - h_expected


def _ensure_profiles():
    from diagnosis_rule_engine import DISEASE_PROFILES, load_diseases_from_folder, build_disease_profiles
    if not DISEASE_PROFILES:
        load_diseases_from_folder()
        build_disease_profiles()
    from diagnosis_rule_engine import DISEASE_PROFILES as loaded
    return loaded


# Acuity / severity / catch-all qualifiers that distinguish DB entries for the
# same underlying condition (e.g. "Bronchitis" / "Acute Bronchitis" / "COPD
# Exacerbation"). Stripping them exposes the core so near-duplicates collapse.
_NAME_QUALIFIERS = {
    "acute", "chronic", "subacute", "exacerbation", "flare", "disease", "syndrome",
    "disorder", "infection", "condition", "primary", "secondary", "mild", "moderate",
    "severe", "early", "late", "stage", "of", "the", "a", "an", "and", "with", "type",
}


def _core_name_tokens(name: str) -> frozenset:
    """Core disease tokens with acuity/severity qualifiers stripped."""
    toks = [t for t in re.findall(r"[a-z0-9]+", str(name or "").lower())
            if t not in _NAME_QUALIFIERS]
    return frozenset(toks)


def _core_names_equivalent(a: str, b: str) -> bool:
    """Strict: same core token set. Used for DEDUP (must not merge AKI vs CKD)."""
    ca, cb = _core_name_tokens(a), _core_name_tokens(b)
    if not ca or not cb:
        return False
    # Equal cores, or one core is the whole of the other (e.g. {copd} vs {copd}).
    return ca == cb


def _core_names_related(a: str, b: str) -> bool:
    """Lenient: cores equal OR one is a subset of the other. Used for matching a
    paraphrased LLM diagnosis name back to a posterior key ("Adult-onset asthma"
    → "Asthma", "Community-acquired pneumonia" → "Pneumonia"). Safe here because
    the posterior key set is small and already deduped into distinct diseases."""
    ca, cb = _core_name_tokens(a), _core_name_tokens(b)
    if not ca or not cb:
        return False
    return ca == cb or ca <= cb or cb <= ca


def _dedupe_near_duplicate_conditions(conditions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse same-core disease variants, keeping the highest-ranked (first) one.

    analyze_case returns score-sorted conditions, so the first occurrence of a
    core is the best-scoring variant. Prevents the posterior mass for one
    condition being split across "X" / "Acute X" / "Chronic X" and stops the
    report showing a redundant variant of #1 as #2.
    """
    kept: List[Dict[str, Any]] = []
    kept_cores: List[frozenset] = []
    for cond in conditions:
        name = str(cond.get("name", ""))
        core = _core_name_tokens(name)
        if core and any(core == kc for kc in kept_cores):
            continue
        kept.append(cond)
        kept_cores.append(core)
    return kept


def _belief_state(patient_state: Dict[str, Any], top_k: int = TOP_K) -> Optional[Dict[str, Any]]:
    """Build the posterior belief state over the rule engine's top candidates."""
    from diagnosis_rule_engine import analyze_case
    profiles = _ensure_profiles()
    if not profiles:
        return None

    demo = patient_state.get("demographics", {}) if isinstance(patient_state.get("demographics"), dict) else {}
    age = demo.get("age")
    gender = demo.get("gender")
    positives = [p for p in (patient_state.get("identified_symptoms") or []) if str(p).strip()]
    negatives = [n for n in (patient_state.get("negatives") or []) if str(n).strip()]
    if not positives:
        return None

    symptom_state = patient_state.get("symptom_state", {}) if isinstance(patient_state.get("symptom_state"), dict) else {}
    asked_dims = {str(f).strip().lower() for f in (symptom_state.get("feature_ids_asked") or []) if str(f).strip()}

    ranking = analyze_case(age=age, gender=gender, symptoms=positives, negatives=negatives)
    conditions = (ranking or {}).get("conditions") or []
    # Collapse same-core variants (Bronchitis / Acute Bronchitis) BEFORE slicing
    # so top_k isn't spent on duplicates and the posterior isn't mass-split.
    conditions = _dedupe_near_duplicate_conditions(conditions)
    by_name = {_norm(p.get("name")): p for p in profiles}
    candidates: List[Dict[str, Any]] = []
    names: List[str] = []
    conds: List[Dict[str, Any]] = []
    for cond in conditions[:top_k]:
        prof = by_name.get(_norm(cond.get("name")))
        if prof is not None:
            candidates.append(prof)
            names.append(str(cond.get("name")))
            conds.append(cond)
    if len(candidates) < 2:
        return None

    # Clinical context (duration, lifestyle, history) from the symptom card and
    # follow-up modifiers — so the prior uses ALL available data, not just symptoms.
    clinical_history = patient_state.get("clinical_history") if isinstance(patient_state.get("clinical_history"), dict) else {}
    modifier_map = symptom_state.get("modifier_map") if isinstance(symptom_state.get("modifier_map"), dict) else {}
    extra = {
        "duration": clinical_history.get("duration") or modifier_map.get("duration") or "",
        "smoking": clinical_history.get("smoking", ""),
        "alcohol": clinical_history.get("alcohol", ""),
        "past_medical_history": clinical_history.get("past_medical_history", []),
        "family_history": clinical_history.get("family_history", []),
    }

    posterior = _posterior(candidates, positives, negatives, age, gender, extra)
    order = sorted(range(len(candidates)), key=lambda i: posterior[i], reverse=True)
    entropy = _entropy(posterior)
    top_prob = max(posterior)
    return {
        "candidates": candidates,
        "names": names,
        "conditions": conds,
        "posterior": posterior,
        "order": order,
        "top_conditions": [names[i] for i in order],
        "posterior_map": {names[i]: round(posterior[i], 3) for i in order},
        "entropy": entropy,
        "top_prob": top_prob,
        "ready": bool(top_prob >= CONFIDENCE_STOP or entropy <= ENTROPY_STOP),
        "known": {_norm(x) for x in positives + negatives},
        "asked_dims": asked_dims,
    }


def rank_final_diagnoses(patient_state: Dict[str, Any], limit: int = 2) -> Optional[Dict[str, Any]]:
    """
    Final ranked diagnoses straight from the belief-state posterior — the SAME
    distribution that drove the follow-up questions, so the report and the loop
    are guaranteed consistent. Each entry: name, confidence band, posterior,
    physician-style reasoning (matched vs contradicted findings), urgency.
    """
    bs = _belief_state(patient_state, top_k=TOP_K)
    if not bs:
        return None
    order, names, posterior, conds = bs["order"], bs["names"], bs["posterior"], bs["conditions"]

    out: List[Dict[str, Any]] = []
    ceiling = 2  # enforce monotonic confidence down the ranked list
    band_name = {2: "High", 1: "Moderate", 0: "Low"}
    for i in order[:limit]:
        post = posterior[i]
        cond = conds[i] if i < len(conds) else {}
        sd = cond.get("score_details") if isinstance(cond.get("score_details"), dict) else {}
        raw = 2 if post >= 0.50 else 1 if post >= 0.25 else 0
        raw = min(raw, ceiling)
        ceiling = raw
        matched = [str(m) for m in (sd.get("matched_positive_features") or [])[:4]]
        contra = [str(m) for m in (sd.get("contradicted_features") or [])[:2]]
        reasoning = str(cond.get("reasoning") or "").strip()
        if not reasoning:
            parts = []
            if matched:
                parts.append("supported by " + ", ".join(matched))
            if contra:
                parts.append("though " + ", ".join(contra) + " argues against it")
            reasoning = (
                f"Best fits the reported pattern ({'; '.join(parts)})." if parts
                else "Most consistent with the reported findings and history."
            )
        out.append({
            "name": names[i],
            "probability": band_name[raw],
            "posterior": round(post, 3),
            "reasoning": reasoning,
            "urgency": str(cond.get("urgency", "Routine")) or "Routine",
            "score": cond.get("score"),
            "score_details": sd,
        })
    if not out:
        return None
    return {"conditions": out, "posterior": bs["posterior_map"], "top_prob": round(bs["top_prob"], 3)}


def rank_candidate_findings(patient_state: Dict[str, Any], top_k: int = TOP_K, limit: int = 10) -> Optional[Dict[str, Any]]:
    """
    Rank unasked candidate findings by expected information gain.

    Returns {top_conditions, posterior, entropy, top_prob, ready, findings:[{term, dimension, eig}]}
    (findings sorted best-first, deduped by canonical dimension) or None.
    """
    try:
        bs = _belief_state(patient_state, top_k=top_k)
        if not bs:
            return None
        candidates, posterior = bs["candidates"], bs["posterior"]
        known, asked_dims = bs["known"], bs["asked_dims"]

        # Only source candidate findings from diseases carrying real posterior
        # mass (top-3 plus anything >= 15%), and only from key/supportive
        # buckets. Rare features of long-shot candidates are exactly the
        # "glossitis for a cough case" generic screens we must never surface.
        allowed = set(bs["order"][:3]) | {i for i, p in enumerate(posterior) if p >= 0.15}

        scored: List[Dict[str, Any]] = []
        seen_terms: set = set()
        seen_dims: set = set()
        for idx in bs["order"]:
            if idx not in allowed:
                continue
            prof = candidates[idx]
            feats = prof.get("features", {}) if isinstance(prof.get("features"), dict) else {}
            for bucket in ("key", "supportive"):
                for f in feats.get(bucket, []) or []:
                    term = _norm(f.get("term"))
                    if not term or term in seen_terms or term in known:
                        continue
                    seen_terms.add(term)
                    dimension = term_to_dimension(term)
                    if dimension in asked_dims or dimension in seen_dims:
                        continue
                    eig = _expected_info_gain(candidates, posterior, term)
                    scored.append({"term": term, "dimension": dimension, "eig": round(eig, 4)})
        scored.sort(key=lambda x: x["eig"], reverse=True)
        # one finding per dimension, best-first
        deduped: List[Dict[str, Any]] = []
        for item in scored:
            if item["dimension"] in seen_dims:
                continue
            seen_dims.add(item["dimension"])
            deduped.append(item)
            if len(deduped) >= limit:
                break

        # Organ systems + risk factors of the top candidates — lets the symptom
        # card tailor history/family-history options to the actual differential
        # (respiratory case → respiratory history, not a fixed Cancer/TB list).
        organ_systems: List[str] = []
        risk_other: List[str] = []
        for prof in candidates:
            osys = str(prof.get("organ_system", "")).strip()
            if osys and osys != "?" and osys.lower() not in {o.lower() for o in organ_systems}:
                organ_systems.append(osys)
            rf = prof.get("risk_factors", {}) if isinstance(prof.get("risk_factors"), dict) else {}
            for term in (rf.get("other") or []):
                t = str(term).strip()
                if t and t.lower() not in {r.lower() for r in risk_other}:
                    risk_other.append(t)

        return {
            "top_conditions": bs["top_conditions"],
            "posterior": bs["posterior_map"],
            "entropy": round(bs["entropy"], 4),
            "top_prob": round(bs["top_prob"], 4),
            "ready": bs["ready"],
            "findings": deduped,
            "organ_systems": organ_systems,
            "risk_other": risk_other,
        }
    except Exception as exc:
        logger.warning("information_gain: ranking failed: %s", exc)
        return None


def select_by_information_gain(patient_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Pick the single next question by expected information gain over the belief state.

    Returns {top_two, feature_term, dimension, eig, entropy, top_prob, ready, posterior}
    or None when EIG cannot be computed (caller falls back to the heuristic).
    """
    ranked = rank_candidate_findings(patient_state, top_k=TOP_K, limit=1)
    if not ranked:
        return None
    top = ranked["top_conditions"]
    best = ranked["findings"][0] if ranked["findings"] else None
    return {
        "top_two": top[:2],
        "feature_term": best["term"] if best else None,
        "dimension": best["dimension"] if best else None,
        "eig": best["eig"] if best else 0.0,
        "entropy": ranked["entropy"],
        "top_prob": ranked["top_prob"],
        "ready": ranked["ready"],
        "posterior": ranked["posterior"],
    }
