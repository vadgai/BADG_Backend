"""
Headless accuracy eval for the follow-up belief-state / information-gain selector.

Runs the diagnostic loop WITHOUT the LLM: a scripted "patient" (each vignette's
true finding set) answers questions chosen by a selection policy, findings
accumulate, and we score the final rule-engine ranking. This isolates and
measures exactly the machinery we're building (posterior + EIG), and lets us A/B
question-selection policies with numbers instead of eyeballing transcripts.

Policies compared:
  - none      : no follow-up (initial symptoms only) — baseline
  - heuristic : the previous utility-score discriminator
  - eig       : expected-information-gain over the belief state (new)

Metrics per policy: top-1 accuracy, top-3 accuracy, avg questions asked.

Run:  python -m tests.eval_information_gain

NOTE: absolute numbers are bounded by disease-data quality (uneven profiles), so
read this as a RELATIVE A/B + regression guard, not a clinical accuracy claim.
Expand VIGNETTES over time — 8 cases is a starter set.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from diagnosis_rule_engine import (  # noqa: E402
    analyze_case, load_diseases_from_folder, build_disease_profiles, _terms_match,
)
from followup.information_gain import select_by_information_gain, term_to_dimension  # noqa: E402
from diagnosis_methods.state_followup import _deterministic_top2_and_feature  # noqa: E402

MAX_QUESTIONS = 12

# Each vignette: presenting symptoms (initial) + the FULL true finding set (present),
# and a list of acceptable correct diagnosis names (matched loosely).
VIGNETTES = [
    {"label": "Appendicitis", "age": 24, "gender": "male",
     "initial": ["right lower quadrant pain", "fever"],
     "present": ["right lower quadrant pain", "fever", "nausea", "loss of appetite",
                 "abdominal pain", "rebound tenderness", "migratory pain"],
     "expected": ["appendicitis"]},
    {"label": "Pneumonia", "age": 62, "gender": "male",
     "initial": ["cough", "fever"],
     "present": ["cough", "fever", "productive cough", "shortness of breath",
                 "chest pain", "sputum"],
     "expected": ["pneumonia", "bronchitis"]},
    {"label": "Migraine", "age": 30, "gender": "female",
     "initial": ["headache"],
     "present": ["headache", "throbbing headache", "photophobia", "nausea", "unilateral headache"],
     "expected": ["migraine"]},
    {"label": "Myocardial infarction", "age": 58, "gender": "male",
     "initial": ["chest pain"],
     "present": ["chest pain", "shortness of breath", "sweating", "radiating pain", "left arm pain"],
     "expected": ["myocardial infarction", "heart attack"]},
    {"label": "Chikungunya/arboviral", "age": 28, "gender": "female",
     "initial": ["fever", "joint pain"],
     "present": ["fever", "joint pain", "high fever", "rash", "severe headache", "muscle pain"],
     "expected": ["chikungunya", "dengue", "scrub typhus", "rubella"]},
    {"label": "Gastroenteritis", "age": 20, "gender": "male",
     "initial": ["diarrhea", "abdominal pain"],
     "present": ["diarrhea", "abdominal pain", "vomiting", "nausea", "fever"],
     "expected": ["gastroenteritis"]},
    {"label": "UTI", "age": 35, "gender": "female",
     "initial": ["dysuria", "urinary frequency"],
     "present": ["dysuria", "urinary frequency", "lower abdominal pain", "fever"],
     "expected": ["urinary tract infection", "cystitis"]},
    {"label": "Intestinal TB", "age": 26, "gender": "male",
     "initial": ["abdominal pain", "weight loss"],
     "present": ["abdominal pain", "weight loss", "night sweats", "fever",
                 "chronic diarrhea", "loss of appetite"],
     "expected": ["tuberculosis", "tubercul"]},
]


def _norm(s):
    return str(s or "").strip().lower()


def _patient_has(feature_term, present):
    return any(_terms_match(feature_term, tf) for tf in present)


def _final_top(positives, negatives, age, gender, n=3):
    ranking = analyze_case(age=age, gender=gender, symptoms=positives, negatives=negatives)
    conds = (ranking or {}).get("conditions") or []
    return [str(c.get("name", "")) for c in conds[:n]]


def _credit(expected, names):
    for exp in expected:
        for name in names:
            n = _norm(name)
            if exp in n or n in exp:
                return True
    return False


def _pick_feature(policy, state):
    """Return (feature_term, dimension, ready) for the given policy, or (None, None, True)."""
    if policy == "eig":
        ig = select_by_information_gain(state)
        if not ig or not ig.get("feature_term"):
            return None, None, True
        return ig["feature_term"], ig["dimension"], bool(ig.get("ready"))
    if policy == "heuristic":
        res = _deterministic_top2_and_feature(state)
        if not isinstance(res, dict):
            return None, None, True
        feat = res.get("feature") or {}
        term = str(feat.get("term", "")).strip()
        if not term:
            return None, None, True
        return term, term_to_dimension(term), False  # heuristic has no early stop
    return None, None, True


def run_policy(vig, policy):
    positives = list(vig["initial"])
    negatives = []
    asked_dims = set()
    qcount = 0
    if policy != "none":
        for _ in range(MAX_QUESTIONS):
            state = {
                "demographics": {"age": vig["age"], "gender": vig["gender"]},
                "identified_symptoms": positives,
                "negatives": negatives,
                "symptom_state": {
                    "current_symptoms": positives,
                    "feature_ids_asked": list(asked_dims),
                    "red_flags": [],
                },
            }
            term, dim, ready = _pick_feature(policy, state)
            if term is None or ready:
                break
            if dim in asked_dims:
                # dimension exhausted for this policy; stop to avoid a spin
                break
            asked_dims.add(dim)
            qcount += 1
            if _patient_has(term, vig["present"]):
                if term not in positives:
                    positives.append(term)
            else:
                if term not in negatives:
                    negatives.append(term)
    top = _final_top(positives, negatives, vig["age"], vig["gender"], n=3)
    return {
        "top3": top,
        "questions": qcount,
        "hit1": _credit(vig["expected"], top[:1]),
        "hit3": _credit(vig["expected"], top),
    }


def main():
    load_diseases_from_folder()
    build_disease_profiles()
    policies = ["none", "heuristic", "eig"]
    agg = {p: {"hit1": 0, "hit3": 0, "q": 0} for p in policies}

    print(f"{'Vignette':<24} {'policy':<10} {'q':>2}  top1 top3  final top-3")
    print("-" * 100)
    for vig in VIGNETTES:
        for p in policies:
            r = run_policy(vig, p)
            agg[p]["hit1"] += int(r["hit1"])
            agg[p]["hit3"] += int(r["hit3"])
            agg[p]["q"] += r["questions"]
            print(f"{vig['label']:<24} {p:<10} {r['questions']:>2}   "
                  f"{'Y' if r['hit1'] else '.'}    {'Y' if r['hit3'] else '.'}   "
                  f"{', '.join(r['top3'])[:60]}")
        print()

    n = len(VIGNETTES)
    print("=" * 60)
    print(f"{'policy':<10} {'top1':>6} {'top3':>6} {'avgQ':>6}")
    for p in policies:
        print(f"{p:<10} {agg[p]['hit1']/n*100:>5.0f}% {agg[p]['hit3']/n*100:>5.0f}% {agg[p]['q']/n:>6.1f}")


if __name__ == "__main__":
    main()
