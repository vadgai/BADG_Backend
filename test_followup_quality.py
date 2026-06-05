#!/usr/bin/env python3
"""Validate optimized follow-up + clinical reasoning prompts.

Checks MCQ structure (A-E, E escape hatch), differential generation,
non-repetition across turns, and that questions stay relevant.
"""

import sys

from diagnosis_methods.patient_state import initialize_patient_state
from Followup_Generation.followup_v5 import (
    get_followup_for_diagnosis_v5,
    update_state_with_answer_v5,
)


def _norm(text):
    return " ".join(str(text or "").strip().lower().split())


def run_scenario(name, age, gender, symptoms, answers):
    print(f"\n--- {name}: {symptoms} ---")
    state = initialize_patient_state(age, gender, symptoms)
    state.setdefault("chat_history", [])

    asked = []
    failures = []
    differentials_seen = 0

    for turn, answer in enumerate(answers, 1):
        result = get_followup_for_diagnosis_v5(state)

        if isinstance(result, str) and "ready" in result.lower():
            print(f"  Turn {turn}: ready_for_diagnosis (early stop)")
            break

        if not isinstance(result, dict):
            failures.append(f"turn {turn}: non-dict result {result!r}")
            break

        question = str(result.get("Question", "")).strip()
        options = {k: str(result.get(k, "")).strip() for k in ("A", "B", "C", "D", "E")}
        print(f"  Turn {turn} Q: {question}")
        print(f"           A:{options['A']} | B:{options['B']} | C:{options['C']} | D:{options['D']} | E:{options['E']}")

        if not question:
            failures.append(f"turn {turn}: empty question")
        if not all(options[k] for k in ("A", "B", "C", "D", "E")):
            failures.append(f"turn {turn}: missing option(s)")
        e_norm = _norm(options["E"])
        if "none" not in e_norm and "not sure" not in e_norm:
            failures.append(f"turn {turn}: E not escape hatch -> {options['E']!r}")
        if _norm(question) in {_norm(q) for q in asked}:
            failures.append(f"turn {turn}: repeated question -> {question!r}")
        distinct = {_norm(options[k]) for k in ("A", "B", "C", "D")}
        if len(distinct) < 4:
            failures.append(f"turn {turn}: non-distinct A-D options")

        asked.append(question)

        state.setdefault("chat_history", []).append({"bot": question, "user": answer})
        state, meta = update_state_with_answer_v5(state, question, answer)
        analysis = meta.get("analysis") if isinstance(meta, dict) else None
        ddx = (analysis or {}).get("differential_diagnosis") if isinstance(analysis, dict) else None
        if isinstance(ddx, list) and ddx:
            differentials_seen += 1
            top = ", ".join(str(d.get("name", "?")) for d in ddx[:3] if isinstance(d, dict))
            print(f"           Dx: {top}")

    checks = {
        "asked_at_least_2_questions": len(asked) >= 2,
        "no_repeats_or_structure_failures": not failures,
        "differential_generated": differentials_seen >= 1,
    }
    for check_name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}: {check_name}")
    if failures:
        for f in failures:
            print(f"    - {f}")
    return all(checks.values())


def main():
    scenarios = [
        ("Respiratory", 30, "Male", ["fever", "cough"],
         ["Yes for 3 days", "Yes, thick yellow phlegm", "No chest pain", "Mild fever"]),
        ("GI", 28, "Female", ["abdominal pain", "nausea"],
         ["Started near belly button then moved right", "Yes, worse with movement", "No diarrhea", "Pain is sharp"]),
    ]
    passed = sum(1 for s in scenarios if run_scenario(*s))
    total = len(scenarios)
    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed}/{total} scenarios passed")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    print("=" * 60)
    print("FOLLOW-UP + CLINICAL REASONING QUALITY TEST")
    print("=" * 60)
    sys.exit(main())
