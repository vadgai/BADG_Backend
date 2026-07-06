"""
Lightweight smoke test for the fully LLM-driven diagnosis pipeline.

There is no more registry/rule-engine determinism to assert on, so this only
checks that a canned patient_state flows through get_final_diagnosis_v5() and
generate_symptom_card() and comes back well-formed, without crashing —
whether or not a live Gemini API key is available in this environment.

Run:  python -m tests.smoke_diagnosis_pipeline
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from diagnosis_methods.patient_state import initialize_patient_state  # noqa: E402
from diagnosis_rule_engine_v5 import get_final_diagnosis_v5  # noqa: E402
from symptom_card import generate_symptom_card  # noqa: E402

FAILURES = []


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def _canned_patient_state():
    state = initialize_patient_state(
        age=30, gender="male",
        symptoms=["chest pain", "shortness of breath", "sweating"],
    )
    state["chief_complaint"] = "chest pain"
    state["negatives"] = ["cough"]
    state["symptom_state"] = {
        "current_symptoms": ["chest pain", "shortness of breath", "sweating"],
        "red_flags": ["chest pain"],
        "questions_asked": ["How long have you had chest pain?"],
        "feature_ids_asked": ["duration"],
        "modifier_map": {"duration": "2 hours"},
    }
    state["differential_diagnosis"] = [
        {"name": "Acute coronary syndrome", "confidence": "High",
         "reasoning": "Chest pain with sweating and breathlessness in a red-flag context."},
        {"name": "Unstable angina", "confidence": "Moderate",
         "reasoning": "Chest pain with exertional-type features."},
        {"name": "Panic attack", "confidence": "Low",
         "reasoning": "Less likely given the red flag, but shares symptom overlap."},
    ]
    state["chat_history"] = [
        {"bot": "How long have you had chest pain?", "user": "About 2 hours, it started suddenly."},
    ]
    return state


def smoke_final_diagnosis():
    print("\n=== get_final_diagnosis_v5 ===")
    state = _canned_patient_state()
    result = get_final_diagnosis_v5(
        age=30, gender="male",
        symptoms=state["symptom_state"]["current_symptoms"],
        chat_history=state["chat_history"],
        negatives=state["negatives"],
        patient_state=state,
    )
    check("returns a dict", isinstance(result, dict))
    conditions = result.get("conditions") if isinstance(result, dict) else None
    check("has a non-empty conditions list", isinstance(conditions, list) and len(conditions) > 0)
    if isinstance(conditions, list):
        for cond in conditions:
            check(
                f"condition well-formed: {cond.get('name')!r}",
                isinstance(cond, dict) and cond.get("name") and cond.get("probability") in {"High", "Moderate", "Low"},
            )


def smoke_symptom_card():
    print("\n=== generate_symptom_card ===")
    state = _canned_patient_state()
    for stage in ("initial", "midpoint", "refined"):
        card = generate_symptom_card(state, stage=stage)
        check(f"[{stage}] returns a dict", isinstance(card, dict))
        check(f"[{stage}] has symptoms list", isinstance(card.get("symptoms"), list))
        check(f"[{stage}] has top_conditions list", isinstance(card.get("top_conditions"), list))
        check(f"[{stage}] has clinical_factors list", isinstance(card.get("clinical_factors"), list))


def main():
    print("VADG Diagnosis Pipeline Smoke Test (pure-LLM)")
    smoke_final_diagnosis()
    smoke_symptom_card()

    print("\n" + "=" * 50)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s)")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL SMOKE CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
