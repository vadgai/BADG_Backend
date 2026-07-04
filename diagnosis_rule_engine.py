"""
Diagnosis Rule Engine with Disease Registry.
Supports both disease schema families and returns traceable evidence scores.
"""

import json
import logging
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global disease registry
DISEASE_REGISTRY: Dict[str, Dict[str, Any]] = {}

# Global disease profiles (processed for faster lookup)
DISEASE_PROFILES: List[Dict[str, Any]] = []

_EMERGENCY_NAME_HINTS = (
    "infarction",
    "stroke",
    "anaphylaxis",
    "sepsis",
    "rupture",
    "tamponade",
    "ectopic",
    "aneurysm",
    "ards",
    "encephalitis",
)


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"\s+", " ", text)


def _dedupe_preserve(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        term = _normalize_text(item)
        if not term or term in seen:
            continue
        out.append(term)
        seen.add(term)
    return out


def _to_weighted_features(value: Any, default_weight: float, source: str) -> List[Dict[str, Any]]:
    features: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        for raw_term, raw_weight in value.items():
            term = _normalize_text(raw_term)
            if not term:
                continue
            try:
                weight = float(raw_weight)
            except (TypeError, ValueError):
                weight = default_weight
            features.append({"term": term, "weight": max(0.1, weight), "source": source})
    elif isinstance(value, list):
        for item in value:
            term = _normalize_text(item)
            if term:
                features.append({"term": term, "weight": default_weight, "source": source})
    return features


def _merge_weighted_features(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for group in groups:
        for feature in group:
            term = _normalize_text(feature.get("term"))
            if not term:
                continue
            try:
                weight = float(feature.get("weight", 1.0))
            except (TypeError, ValueError):
                weight = 1.0
            current = merged.get(term)
            if current is None or weight > float(current.get("weight", 0.0)):
                merged[term] = {
                    "term": term,
                    "weight": weight,
                    "source": feature.get("source", "unknown"),
                }
    return list(merged.values())


# Fix I: clinical synonym expansion for common abbreviations and variants
_CLINICAL_SYNONYMS: Dict[str, List[str]] = {
    "rif pain": ["right lower abdominal pain", "right iliac fossa pain"],
    "rif": ["right lower abdomen", "right iliac fossa"],
    "luq": ["left upper quadrant", "left upper abdomen"],
    "ruq": ["right upper quadrant", "right upper abdomen"],
    "llq": ["left lower quadrant", "left lower abdomen"],
    "rlq": ["right lower quadrant", "right lower abdomen"],
    "sob": ["shortness of breath", "difficulty breathing", "breathlessness"],
    "cp": ["chest pain"],
    "ha": ["headache"],
    "n/v": ["nausea", "vomiting"],
    "n&v": ["nausea", "vomiting"],
    "nv": ["nausea", "vomiting"],
    "gi": ["gastrointestinal"],
    "uti": ["urinary tract infection"],
    "uri": ["upper respiratory infection"],
    "urti": ["upper respiratory tract infection"],
    "lrti": ["lower respiratory tract infection"],
    "mi": ["myocardial infarction", "heart attack"],
    "dvt": ["deep vein thrombosis"],
    "pe": ["pulmonary embolism"],
    "bp": ["blood pressure"],
    "hr": ["heart rate"],
    "abd pain": ["abdominal pain"],
    "abd": ["abdominal", "abdomen"],
    "stomach pain": ["abdominal pain"],
    "tummy pain": ["abdominal pain"],
    "belly pain": ["abdominal pain"],
    "lost weight": ["weight loss"],
    "losing weight": ["weight loss"],
    "can't breathe": ["difficulty breathing", "shortness of breath"],
    "trouble breathing": ["difficulty breathing", "shortness of breath"],
    "hard to breathe": ["difficulty breathing", "shortness of breath"],
    "feeling dizzy": ["dizziness", "vertigo"],
    "spinning sensation": ["vertigo", "dizziness"],
    "loose motion": ["diarrhea"],
    "loose stools": ["diarrhea"],
    "watery stools": ["diarrhea"],
    "runny stool": ["diarrhea"],
    "blood in urine": ["hematuria"],
    "blood in stool": ["rectal bleeding", "melena"],
    "black stool": ["melena"],
    "dark stool": ["melena"],
    "difficulty swallowing": ["dysphagia"],
    "trouble swallowing": ["dysphagia"],
    "burning urination": ["dysuria"],
    "pain on urination": ["dysuria"],
    "frequent urination": ["urinary frequency", "polyuria"],
    "chest tightness": ["chest pain", "angina"],
    "tight chest": ["chest pain", "angina"],
    "racing heart": ["palpitations", "tachycardia"],
    "heart racing": ["palpitations", "tachycardia"],
    "high temperature": ["fever"],
    "running fever": ["fever"],
    "feeling hot": ["fever"],
    # Layperson ↔ clinical bridges: follow-up questions are phrased in plain
    # language, so patient positives/negatives arrive as everyday words while
    # disease profiles use clinical terms. Without these, a denial like
    # "no burning chest" never matches GERD's "heartburn" and has zero effect.
    "burning chest": ["heartburn"],
    "chest burning": ["heartburn"],
    "burning in chest": ["heartburn"],
    "acid taste": ["regurgitation", "heartburn"],
    "sour taste": ["regurgitation", "heartburn"],
    "acid reflux": ["heartburn", "regurgitation"],
    "food coming back up": ["regurgitation"],
    "throwing up": ["vomiting"],
    "threw up": ["vomiting"],
    "puking": ["vomiting"],
    "phlegm": ["sputum"],
    "mucus": ["sputum"],
    "coughing up blood": ["hemoptysis"],
    "blood in phlegm": ["hemoptysis"],
    "blood in sputum": ["hemoptysis"],
    "blood in cough": ["hemoptysis"],
    "short of breath": ["shortness of breath", "difficulty breathing", "dyspnea"],
    "breathless": ["shortness of breath", "difficulty breathing", "dyspnea"],
    "breathlessness": ["shortness of breath", "difficulty breathing", "dyspnea"],
    "shortness of breath": ["dyspnea", "difficulty breathing"],
    "wheezing": ["wheeze"],
    "whistling breathing": ["wheeze", "wheezing"],
    "sweating at night": ["night sweats"],
    "night sweating": ["night sweats"],
    "no appetite": ["loss of appetite", "anorexia"],
    "poor appetite": ["loss of appetite", "anorexia"],
    "not hungry": ["loss of appetite"],
    "tiredness": ["fatigue"],
    "exhausted": ["fatigue"],
    "very tired": ["fatigue"],
    "yellow skin": ["jaundice"],
    "yellow eyes": ["jaundice"],
    "yellowing": ["jaundice"],
    "swollen glands": ["lymphadenopathy", "swollen lymph nodes"],
    "swollen nodes": ["lymphadenopathy", "swollen lymph nodes"],
}


@lru_cache(maxsize=4096)
def _expand_synonyms(term: str) -> Tuple[str, ...]:
    """Expand a normalized term to include all known synonyms.

    Cached: called for every feature of every disease on each analyze_case
    pass, but the distinct term vocabulary is small.
    """
    expansions = [term]
    lower_term = term.strip().lower()
    if lower_term in _CLINICAL_SYNONYMS:
        expansions.extend(_CLINICAL_SYNONYMS[lower_term])
    # Partial match: check if any synonym key is a substring of the term
    for key, values in _CLINICAL_SYNONYMS.items():
        if key in lower_term or lower_term in key:
            expansions.extend(values)
    return tuple(dict.fromkeys(expansions))  # deduplicate preserving order


def _tokenize(value: Any) -> List[str]:
    return re.findall(r"[a-z0-9]+", str(value or "").lower())


def _phrase_contains(haystack_tokens: List[str], needle_tokens: List[str]) -> bool:
    """True if needle_tokens appear as a contiguous whole-word run in haystack_tokens."""
    n = len(needle_tokens)
    if n == 0 or n > len(haystack_tokens):
        return False
    for i in range(len(haystack_tokens) - n + 1):
        if haystack_tokens[i:i + n] == needle_tokens:
            return True
    return False


# Qualifier words that split a compound feature into HEAD (the actual finding)
# and TAIL (its trigger/context), e.g. "leakage w/ cough" → head "leakage".
_QUALIFIER_SPLIT = re.compile(r"\b(?:w|with|during|after|when|while|on|upon|following)\b")


def _head_tokens(tokens: List[str]) -> List[str]:
    """Tokens of the finding itself, before any trigger/context qualifier."""
    for idx, tok in enumerate(tokens):
        if _QUALIFIER_SPLIT.fullmatch(tok):
            return tokens[:idx] if idx > 0 else tokens
    return tokens


def _terms_match(a: str, b: str) -> bool:
    """
    Whole-word phrase match. True when a == b, or one is a contiguous word-level
    subphrase of the other (e.g. "abdominal pain" ⊆ "right lower abdominal pain").

    Two guards against false positives:
    - token boundaries (no "ill" ⊆ "chills" / "art" ⊆ "heart"), and
    - qualifier heads: for compound terms like "leakage w/ cough", the finding is
      the HEAD ("leakage"), and a shorter term may only match if it overlaps the
      head — so a patient's "cough" no longer matches "leakage w/ cough".
    """
    at = _tokenize(a)
    bt = _tokenize(b)
    if not at or not bt:
        return False
    if at == bt:
        return True
    if _phrase_contains(bt, at):  # a is the shorter phrase inside b
        return _phrase_contains(_head_tokens(bt), at)
    if _phrase_contains(at, bt):  # b is the shorter phrase inside a
        return _phrase_contains(_head_tokens(at), bt)
    return False


def _feature_match(term: str, values: List[str]) -> bool:
    if not term:
        return False
    # Expand the term to include synonyms before matching
    expanded_terms = _expand_synonyms(term)
    for candidate in expanded_terms:
        for value in values:
            if value and _terms_match(candidate, value):
                return True
    # Also expand values side for abbreviations in patient answers
    for value in values:
        for expanded_val in _expand_synonyms(value):
            if _terms_match(term, expanded_val):
                return True
    return False


def _extract_age_ranges(disease_data: Dict[str, Any]) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    risk = disease_data.get("risk_factors", {}) if isinstance(disease_data.get("risk_factors"), dict) else {}
    age_range = risk.get("age_range", [])
    if isinstance(age_range, list):
        for item in age_range:
            if isinstance(item, dict):
                try:
                    mn = int(item.get("min", 0))
                    mx = int(item.get("max", 120))
                except (TypeError, ValueError):
                    continue
                if mn <= mx:
                    ranges.append((mn, mx))
            elif isinstance(item, list) and len(item) == 2:
                try:
                    mn = int(item[0])
                    mx = int(item[1])
                except (TypeError, ValueError):
                    continue
                if mn <= mx:
                    ranges.append((mn, mx))

    typical_age = disease_data.get("typical_age_range")
    if isinstance(typical_age, list) and len(typical_age) == 2:
        try:
            mn = int(typical_age[0])
            mx = int(typical_age[1])
            if mn <= mx:
                ranges.append((mn, mx))
        except (TypeError, ValueError):
            pass

    deduped: List[Tuple[int, int]] = []
    seen = set()
    for rng in ranges:
        if rng in seen:
            continue
        deduped.append(rng)
        seen.add(rng)
    return deduped


def _is_core_tier(disease_data: Dict[str, Any]) -> bool:
    tier_value = _normalize_text(disease_data.get("tier") or disease_data.get("category"))
    if tier_value in {"core", "common", "emergency"}:
        return True
    prevalence = _normalize_text(disease_data.get("prevalence"))
    if prevalence == "common":
        return True
    urgency_indicators = disease_data.get("urgency_indicators")
    return bool(isinstance(urgency_indicators, list) and urgency_indicators)


def _is_emergency_candidate(disease_name: str, disease_data: Dict[str, Any]) -> bool:
    urgency_indicators = disease_data.get("urgency_indicators")
    if isinstance(urgency_indicators, list) and urgency_indicators:
        return True
    name = _normalize_text(disease_name)
    return any(hint in name for hint in _EMERGENCY_NAME_HINTS)


def load_diseases_from_folder(folder_path: Optional[str] = None) -> int:
    """
    Load all disease definitions from JSON files in the diseases folder.
    
    Args:
        folder_path: Optional path to diseases folder. Defaults to backend/diseases/
    
    Returns:
        Number of diseases loaded
    """
    global DISEASE_REGISTRY
    
    if folder_path is None:
        # Get the directory where this file is located
        current_dir = Path(__file__).parent
        folder_path = current_dir / "diseases"
    else:
        folder_path = Path(folder_path)
    
    if not folder_path.exists():
        logger.warning(f"Diseases folder not found: {folder_path}")
        return 0
    
    DISEASE_REGISTRY = {}
    loaded_count = 0
    
    # Load all JSON files matching the pattern D###_*.json
    for json_file in sorted(folder_path.glob("D*.json")):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                disease_data = json.load(f)
                
            # Validate required fields
            if not isinstance(disease_data, dict):
                logger.warning(f"Invalid format in {json_file.name}: expected dict")
                continue
            
            disease_id = disease_data.get("id") or disease_data.get("code") or json_file.stem
            disease_name = disease_data.get("name", "Unknown Disease")

            # Key the registry by the (always-unique) filename stem, NOT by id/code.
            # Many files reuse the same id/code (e.g. an old "symptoms"-schema file and
            # a newer "key_symptoms" file both tagged D001), which previously caused the
            # earlier disease to be silently overwritten — ~20 conditions were dropped.
            # Preserve the declared id/code inside the record for display/traceability.
            disease_data.setdefault("id", disease_id)
            registry_key = json_file.stem
            if registry_key in DISEASE_REGISTRY:
                logger.warning(f"Duplicate disease file {json_file.name}; skipping")
                continue

            DISEASE_REGISTRY[registry_key] = disease_data
            loaded_count += 1
            logger.debug(f"Loaded disease: {disease_id} - {disease_name}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON in {json_file.name}: {e}")
        except Exception as e:
            logger.error(f"Error loading {json_file.name}: {e}")
    
    logger.info(f"✅ Loaded {loaded_count} disease(s) from {folder_path}")
    return loaded_count


def build_disease_profiles() -> List[Dict[str, Any]]:
    """
    Build optimized disease profiles from the registry for faster matching.
    
    Returns:
        List of disease profiles with normalized symptom lists and metadata
    """
    global DISEASE_REGISTRY, DISEASE_PROFILES

    profiles: List[Dict[str, Any]] = []
    for registry_key, disease_data in DISEASE_REGISTRY.items():
        disease_id = disease_data.get("id") or disease_data.get("code") or registry_key
        name = str(disease_data.get("name", "Unknown")).strip()
        symptoms_block = disease_data.get("symptoms", {}) if isinstance(disease_data.get("symptoms"), dict) else {}

        required_list = _dedupe_preserve(symptoms_block.get("required", []) if isinstance(symptoms_block.get("required"), list) else [])
        common_list = _dedupe_preserve(symptoms_block.get("common", []) if isinstance(symptoms_block.get("common"), list) else [])
        rare_list = _dedupe_preserve(symptoms_block.get("rare", []) if isinstance(symptoms_block.get("rare"), list) else [])

        key_features = _to_weighted_features(disease_data.get("key_symptoms"), default_weight=1.1, source="key_symptoms")
        supportive_features = _to_weighted_features(
            disease_data.get("supportive_symptoms"),
            default_weight=0.7,
            source="supportive_symptoms",
        )
        exclude_features = _to_weighted_features(
            disease_data.get("exclude_symptoms"),
            default_weight=0.9,
            source="exclude_symptoms",
        )

        weighted_required = _to_weighted_features(required_list, default_weight=1.0, source="symptoms.required")
        weighted_common = _to_weighted_features(common_list, default_weight=0.6, source="symptoms.common")
        weighted_rare = _to_weighted_features(rare_list, default_weight=0.35, source="symptoms.rare")

        risk = disease_data.get("risk_factors", {}) if isinstance(disease_data.get("risk_factors"), dict) else {}
        genders = [str(g).strip().lower() for g in (risk.get("gender") if isinstance(risk.get("gender"), list) else []) if str(g).strip()]

        age_ranges = _extract_age_ranges(disease_data)
        profile = {
            "id": str(disease_id),
            "name": name,
            "organ_system": str(disease_data.get("organ_system", "General")).strip(),
            "symptoms": {
                "required": required_list,
                "common": common_list,
                "rare": rare_list,
            },
            "features": {
                "key": _merge_weighted_features(key_features, weighted_required),
                "supportive": _merge_weighted_features(supportive_features, weighted_common),
                "rare": _merge_weighted_features(weighted_rare),
                "exclude": exclude_features,
            },
            "risk_factors": {
                "age_ranges": age_ranges,
                "age_range": age_ranges,
                "gender": genders,
                "other": risk.get("other", []) if isinstance(risk.get("other"), list) else [],
            },
            "urgency_indicators": _dedupe_preserve(
                disease_data.get("urgency_indicators", []) if isinstance(disease_data.get("urgency_indicators"), list) else []
            ),
            "prevalence": str(disease_data.get("prevalence", "unknown")).strip().lower() or "unknown",
            "diagnostic_criteria": disease_data.get("diagnostic_criteria", []),
            "is_core_tier": _is_core_tier(disease_data),
            "is_emergency_candidate": _is_emergency_candidate(name, disease_data),
            "raw_data": disease_data,
        }
        profiles.append(profile)

    # Deduplicate genuine same-name conditions (a handful of files repeat a disease
    # under different ids). Keep the richer profile so both copies don't split the
    # ranking. Distinct conditions that merely share a word (e.g. "Hepatitis" vs
    # "Hepatitis A") keep their own normalized names and are unaffected.
    def _profile_richness(p: Dict[str, Any]) -> int:
        feats = p.get("features", {}) if isinstance(p.get("features"), dict) else {}
        return sum(len(feats.get(bucket, []) or []) for bucket in ("key", "supportive", "rare", "exclude"))

    by_name: Dict[str, Dict[str, Any]] = {}
    for profile in profiles:
        name_key = _normalize_text(profile.get("name"))
        if not name_key:
            by_name[profile.get("id", id(profile))] = profile
            continue
        existing = by_name.get(name_key)
        if existing is None or _profile_richness(profile) > _profile_richness(existing):
            by_name[name_key] = profile
    deduped = list(by_name.values())

    DISEASE_PROFILES = deduped
    logger.info(
        "✅ Built %s disease profile(s) (%s after name-dedup)", len(profiles), len(deduped)
    )
    return deduped


def score_disease_match(
    disease_profile: Dict[str, Any],
    patient_symptoms: List[str],
    age: Optional[int] = None,
    gender: Optional[str] = None,
    weight: Optional[float] = None,
    height: Optional[float] = None,
    chat_history: Optional[str] = None,
    negatives: Optional[List[str]] = None,
    modifiers: Optional[Any] = None,
    red_flags: Optional[List[str]] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Score how well a disease profile matches a patient case.
    
    Args:
        disease_profile: Disease profile from build_disease_profiles()
        patient_symptoms: List of patient symptoms (normalized to lowercase)
        age: Patient age
        gender: Patient gender
        weight: Patient weight in kg
        height: Patient height in cm
        chat_history: Additional clinical history
    
    Returns:
        Tuple of (score: float, details: dict)
    """
    del weight, height, chat_history, modifiers  # retained for compatibility

    positives = _dedupe_preserve(patient_symptoms if isinstance(patient_symptoms, list) else [])
    negatives_norm = _dedupe_preserve(negatives if isinstance(negatives, list) else [])
    red_flags_norm = _dedupe_preserve(red_flags if isinstance(red_flags, list) else [])

    details = {
        "symptom_matches": {"required": 0, "common": 0, "rare": 0},
        "risk_factor_matches": 0.0,
        "urgency_match": False,
        "match_reasons": [],
        "matched_positive_features": [],
        "contradicted_features": [],
        "exclude_hits": [],
        "demographic_adjustments": [],
        "raw_score": 0.0,
        "final_numeric_score": 0.0,
    }

    positive_score = 0.0
    positive_max = 0.0
    contradiction_penalty = 0.0
    exclude_penalty = 0.0

    key_feature_count = 0
    matched_key_count = 0
    denied_key_count = 0
    feature_buckets = [
        ("key", 1.25, 0.95),
        ("supportive", 0.75, 0.55),
        ("rare", 0.35, 0.2),
    ]
    for bucket_name, pos_factor, neg_factor in feature_buckets:
        features = disease_profile.get("features", {}).get(bucket_name, [])
        for feature in features:
            term = _normalize_text(feature.get("term"))
            if not term:
                continue
            try:
                weight_value = float(feature.get("weight", 1.0))
            except (TypeError, ValueError):
                weight_value = 1.0
            weighted_max = pos_factor * weight_value
            positive_max += weighted_max
            if bucket_name == "key":
                key_feature_count += 1
            if _feature_match(term, positives):
                positive_score += weighted_max
                details["matched_positive_features"].append(term)
                if bucket_name == "key":
                    matched_key_count += 1
            if _feature_match(term, negatives_norm):
                contradiction_penalty += (neg_factor * weight_value)
                details["contradicted_features"].append(term)
                if bucket_name == "key":
                    denied_key_count += 1

    # Coverage of the disease's own key (defining) features by the patient's positives.
    # Used to gate high-confidence labels so a single incidental match cannot read "High".
    details["matched_key_count"] = matched_key_count
    details["key_feature_count"] = key_feature_count
    details["key_coverage"] = round(matched_key_count / key_feature_count, 3) if key_feature_count else 0.0
    details["denied_key_count"] = denied_key_count

    for feature in disease_profile.get("features", {}).get("exclude", []):
        term = _normalize_text(feature.get("term"))
        if not term:
            continue
        try:
            weight_value = float(feature.get("weight", 1.0))
        except (TypeError, ValueError):
            weight_value = 1.0
        if _feature_match(term, positives):
            exclude_penalty += (1.35 * weight_value)
            details["exclude_hits"].append(term)
        elif _feature_match(term, negatives_norm):
            positive_score += (0.12 * weight_value)
            positive_max += (0.12 * weight_value)

    required_symptoms = disease_profile.get("symptoms", {}).get("required", [])
    common_symptoms = disease_profile.get("symptoms", {}).get("common", [])
    rare_symptoms = disease_profile.get("symptoms", {}).get("rare", [])
    details["symptom_matches"]["required"] = sum(1 for item in required_symptoms if _feature_match(item, positives))
    details["symptom_matches"]["common"] = sum(1 for item in common_symptoms if _feature_match(item, positives))
    details["symptom_matches"]["rare"] = sum(1 for item in rare_symptoms if _feature_match(item, positives))

    positive_component = positive_score / max(1.0, positive_max)
    penalty_component = (contradiction_penalty + exclude_penalty) / max(1.0, positive_max * 0.8)
    penalty_component = min(1.4, penalty_component)

    demographic_adjustment = 0.0
    risk_factors = disease_profile.get("risk_factors", {})
    age_ranges = risk_factors.get("age_ranges", []) if isinstance(risk_factors, dict) else []
    if age is not None and age_ranges:
        age_match = any(isinstance(item, tuple) and item[0] <= age <= item[1] for item in age_ranges)
        if age_match:
            demographic_adjustment += 0.18
            details["demographic_adjustments"].append("age_match")
        else:
            demographic_adjustment -= 0.12
            details["demographic_adjustments"].append("age_mismatch")

    risk_genders = risk_factors.get("gender", []) if isinstance(risk_factors, dict) else []
    gender_norm = _normalize_text(gender)
    if gender_norm and risk_genders:
        restricted = {g for g in risk_genders if g in {"male", "female", "man", "woman"}}
        if len(restricted) == 1:
            if gender_norm in restricted:
                demographic_adjustment += 0.08
                details["demographic_adjustments"].append("gender_match")
            else:
                demographic_adjustment -= 0.08
                details["demographic_adjustments"].append("gender_mismatch")
    details["risk_factor_matches"] = round(demographic_adjustment, 4)

    tier_adjustment = 0.12 if disease_profile.get("is_core_tier") else -0.04
    prevalence = disease_profile.get("prevalence", "")
    if prevalence == "common":
        tier_adjustment += 0.05
    elif prevalence == "rare":
        tier_adjustment -= 0.03

    urgency_bonus = 0.0
    urgency_indicators = disease_profile.get("urgency_indicators", [])
    urgency_match = any(_feature_match(indicator, positives) for indicator in urgency_indicators)
    if urgency_match:
        urgency_bonus += 0.18
    if disease_profile.get("is_emergency_candidate") and red_flags_norm:
        urgency_bonus += 0.15
    elif disease_profile.get("is_emergency_candidate") and not red_flags_norm:
        urgency_bonus -= 0.02
    details["urgency_match"] = urgency_match

    raw_score = positive_component - penalty_component + demographic_adjustment + tier_adjustment + urgency_bonus
    details["raw_score"] = round(raw_score, 4)

    score = 1.0 / (1.0 + math.exp(-3.25 * (raw_score - 0.18)))
    if not details["matched_positive_features"]:
        score *= 0.35
    if details["exclude_hits"] and len(details["matched_positive_features"]) < 2:
        score *= 0.55
    # Key-feature denial gate: the additive contradiction_penalty above is
    # normalized against positive_max, so a disease whose DEFINING features the
    # patient explicitly denied can still float on tier/urgency bonuses (e.g.
    # GERD ranking #2 after the patient answered "No" to every reflux question).
    # Denying the majority of a disease's key features must collapse its score.
    if key_feature_count:
        if denied_key_count >= key_feature_count:
            score *= 0.15
        elif denied_key_count / key_feature_count >= 0.5:
            score *= 0.40
    score = min(1.0, max(0.0, score))
    details["final_numeric_score"] = round(score, 4)

    if details["matched_positive_features"]:
        details["match_reasons"].append(
            "matched: " + ", ".join(details["matched_positive_features"][:5])
        )
    if details["contradicted_features"]:
        details["match_reasons"].append(
            "contradicted by negatives: " + ", ".join(details["contradicted_features"][:4])
        )
    if details["exclude_hits"]:
        details["match_reasons"].append(
            "exclude hits: " + ", ".join(details["exclude_hits"][:3])
        )

    return score, details


def analyze_case(
    age: int,
    gender: str,
    symptoms: List[str],
    chat_history: str = "",
    weight: Optional[float] = None,
    height: Optional[float] = None,
    negatives: Optional[List[str]] = None,
    modifiers: Optional[Any] = None,
    red_flags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Analyze a patient case using the disease registry and return top diagnoses.
    
    Args:
        age: Patient age
        gender: Patient gender
        symptoms: List of symptoms
        chat_history: Clinical history from Q&A
        weight: Patient weight in kg (optional)
        height: Patient height in cm (optional)
    
    Returns:
        Dictionary with conditions and follow-up questions in the expected format
    """
    global DISEASE_PROFILES
    del chat_history  # structured-state workflow: no raw chat scoring

    if not DISEASE_PROFILES:
        logger.warning("No disease profiles loaded. Call build_disease_profiles() first.")
        return {
            "conditions": [],
            "follow_up_questions": []
        }
    
    # Score all diseases
    scored_diseases: List[Dict[str, Any]] = []
    for profile in DISEASE_PROFILES:
        score, details = score_disease_match(
            profile,
            symptoms,
            age=age,
            gender=gender,
            weight=weight,
            height=height,
            chat_history=None,
            negatives=negatives,
            modifiers=modifiers,
            red_flags=red_flags,
        )
        
        if score > 0:
            scored_diseases.append({
                "profile": profile,
                "score": score,
                "details": details
            })
    
    # Sort by score (highest first)
    scored_diseases.sort(key=lambda x: x["score"], reverse=True)
    
    # Keep a wider shortlist for trace/reports; API still returns top 3 conditions.
    top_diseases = scored_diseases[:5]
    
    # Build response in expected format
    conditions = []
    for disease_data in top_diseases:
        profile = disease_data["profile"]
        score = disease_data["score"]
        details = disease_data["details"]
        
        # Evidence-aware confidence banding. The raw score saturates near 1.0 for
        # many candidates, so a strong score alone is not enough for "High" — the
        # patient must also cover a meaningful share of the disease's defining
        # (key) features. This prevents thin, single-feature matches from being
        # presented to patients as high-confidence.
        matched_key = details.get("matched_key_count", 0)
        key_coverage = details.get("key_coverage", 0.0)
        if score >= 0.72 and matched_key >= 2 and key_coverage >= 0.4:
            probability = "High"
        elif score >= 0.48 and (matched_key >= 1 or key_coverage >= 0.25):
            probability = "Moderate"
        elif score >= 0.72:
            # Strong score but thin key-feature coverage → cap at Moderate.
            probability = "Moderate"
        else:
            probability = "Low"
        
        urgency = "Monitor"
        if details.get("urgency_match") or (profile.get("is_emergency_candidate") and red_flags):
            urgency = "Emergency"
        elif probability in {"High", "Moderate"}:
            urgency = "Routine"
        
        reasoning_parts: List[str] = []
        matched = details.get("matched_positive_features", [])
        contrad = details.get("contradicted_features", [])
        if matched:
            reasoning_parts.append("Matches " + ", ".join(matched[:3]))
        if contrad:
            reasoning_parts.append("Conflicts with negatives: " + ", ".join(contrad[:2]))
        if details.get("exclude_hits"):
            reasoning_parts.append("Exclude-feature conflict present")
        reasoning = ". ".join(reasoning_parts) if reasoning_parts else "Limited but possible pattern match."
        
        conditions.append({
            "name": profile["name"],
            "probability": probability,
            "reasoning": reasoning,
            "urgency": urgency,
            "score": round(score, 4),
            "disease_id": profile.get("id"),
            "score_details": {
                "matched_positive_features": details.get("matched_positive_features", []),
                "contradicted_features": details.get("contradicted_features", []),
                "exclude_hits": details.get("exclude_hits", []),
                "demographic_adjustments": details.get("demographic_adjustments", []),
                "final_numeric_score": details.get("final_numeric_score", round(score, 4)),
            },
        })
    
    # Enforce monotonic confidence: a lower-ranked condition must never display a
    # higher confidence label than one ranked above it (conditions are sorted by
    # score). Keeps the confidence column consistent with the ranking order.
    _prob_rank = {"High": 2, "Moderate": 1, "Low": 0}
    _rank_prob = {2: "High", 1: "Moderate", 0: "Low"}
    ceiling = 2
    for cond in conditions:
        current = _prob_rank.get(cond["probability"], 0)
        capped = min(current, ceiling)
        cond["probability"] = _rank_prob[capped]
        ceiling = capped

    follow_up_questions = build_followup_questions(top_diseases, symptoms, "")

    return {
        "conditions": conditions,
        "follow_up_questions": follow_up_questions
    }


def build_followup_questions(
    top_diseases: List[Dict[str, Any]],
    symptoms: List[str],
    chat_history: str
) -> List[str]:
    """
    Build relevant follow-up questions based on top disease matches.
    
    Args:
        top_diseases: List of top-scoring disease matches
        symptoms: Current symptoms
        chat_history: Existing clinical history
    
    Returns:
        List of follow-up questions
    """
    del chat_history
    questions: List[str] = []

    if not top_diseases:
        return []

    top_disease = top_diseases[0]
    profile = top_disease["profile"]

    second_profile = {}
    if len(top_diseases) > 1 and isinstance(top_diseases[1], dict):
        second_profile = top_diseases[1].get("profile", {}) or {}

    known = _dedupe_preserve(symptoms if isinstance(symptoms, list) else [])
    top_key = [f.get("term", "") for f in profile.get("features", {}).get("key", [])]
    second_key = [f.get("term", "") for f in second_profile.get("features", {}).get("key", [])]
    unique_terms = [term for term in top_key if term and term not in second_key and term not in known]

    if unique_terms:
        questions.append(f"Are you currently experiencing {unique_terms[0]}?")
    if len(unique_terms) > 1:
        questions.append(f"Is {unique_terms[1]} present along with your main symptoms?")

    if not questions:
        required_symptoms = profile.get("symptoms", {}).get("required", [])
        for req_symptom in required_symptoms:
            if req_symptom and req_symptom not in known:
                questions.append(f"Have you experienced {req_symptom}?")
                break

    return questions[:3]


def build_json_prompt(
    age: int,
    gender: str,
    symptoms: List[str],
    chat_history: str = "",
    weight: Optional[float] = None,
    height: Optional[float] = None,
    disease_context: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Build a JSON-formatted prompt for LLM enhancement of rule-based analysis.
    
    Args:
        age: Patient age
        gender: Patient gender
        symptoms: List of symptoms
        chat_history: Clinical history
        weight: Patient weight (optional)
        height: Patient height (optional)
        disease_context: Optional list of top disease matches from rule engine
    
    Returns:
        Formatted prompt string
    """
    formatted_symptoms = ", ".join(symptoms)
    
    # BMI calculation disabled
    bmi_text = ""
    
    # Add disease context if available
    disease_context_text = ""
    if disease_context:
        disease_context_text = "\n\n    RULE-BASED ANALYSIS CONTEXT:\n"
        disease_context_text += "    The following conditions were identified by rule-based matching:\n"
        for idx, disease in enumerate(disease_context[:3], 1):
            disease_context_text += f"    {idx}. {disease.get('name', 'Unknown')} (Match Score: {disease.get('score', 0):.2f})\n"
        disease_context_text += "\n    Use this context to refine and enhance your clinical reasoning."
    
    prompt = f"""
    You are an expert clinical diagnostician performing differential diagnosis analysis. Your task is to synthesize ALL available patient data into a coherent clinical picture and rank the most likely conditions.
    
    Patient Profile:
    - Age: {age} years (consider age-related disease susceptibility, physiological changes, and epidemiology)
    - Gender: {gender} (consider gender-specific conditions and hormonal factors)
    {bmi_text}
    
    Reported Symptoms: {formatted_symptoms}
    
    Detailed Clinical History (Q&A Responses):
    {chat_history}
    {disease_context_text}
    
    CLINICAL REASONING APPROACH:
    1. **Pattern Recognition**: Analyze symptom constellation - which symptoms cluster together in known disease patterns?
    2. **Temporal Analysis**: Consider onset (acute vs gradual), duration, progression, timing patterns
    3. **Severity Assessment**: Evaluate symptom intensity and functional impact
    4. **Risk Stratification**: Factor in age and gender
    5. **Differential Diagnosis**: Distinguish between competing diagnoses using discriminating clinical features
    6. **Likelihood Ranking**: Assign probability based on symptom match, prevalence, and patient-specific risk factors
    
    PROBABILITY ASSIGNMENT RULES:
    - **High**: ≥70% symptom match + strong supporting evidence from history + consistent with patient demographics
    - **Moderate**: 50-70% symptom match + some supporting evidence + plausible for patient profile
    - **Low**: <50% symptom match OR missing key features BUT still possible differential
    
    URGENCY CLASSIFICATION:
    - **Emergency**: Life-threatening symptoms, severe organ dysfunction, requires immediate medical attention
    - **Routine**: Stable symptoms, schedule appointment within 24-48 hours
    - **Monitor**: Mild symptoms, self-limiting conditions, observe and seek care if worsening
    
    TASK: Identify the TOP 3 most likely medical conditions based on comprehensive analysis of ALL available data.
    
    For each condition provide:
    1. **Name**: Specific disease/condition (use medical terminology but clear)
    2. **Probability**: High / Moderate / Low (based on clinical reasoning above)
    3. **Reasoning**: 2-3 sentences explaining WHY this diagnosis fits (cite specific symptoms, risk factors, clinical features)
    4. **Urgency**: Emergency / Routine / Monitor
    
    Also suggest 2-3 relevant follow-up questions that would help confirm or rule out the top diagnoses.
    
    RESPOND STRICTLY IN JSON FORMAT (no markdown, no extra text):
    {{
      "conditions": [
        {{"name": "...", "probability": "High/Moderate/Low", "reasoning": "Clinical reasoning with specific symptom references", "urgency": "Emergency/Routine/Monitor"}},
        {{"name": "...", "probability": "...", "reasoning": "...", "urgency": "..."}},
        {{"name": "...", "probability": "...", "reasoning": "...", "urgency": "..."}}
      ],
      "follow_up_questions": ["...", "...", "..."]
    }}
    """
    
    return prompt
