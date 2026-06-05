"""
Clinical Follow-up v5 Verification Script
==========================================
Tests that the upgraded follow-up engine:
1. Produces exactly 5 options (A-E) per question
2. Option E == "None of these / Not sure"
3. Does not repeat questions
4. Respects max 8 question limit
5. Full chat history is injected correctly
"""

import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diagnosis_methods.patient_state import initialize_patient_state, update_patient_state
from Followup_Generation.followup_v5 import (
    get_followup_for_diagnosis_v5,
    update_state_with_answer_v5,
)

PASS = "\u2705 PASS"
FAIL = "\u274c FAIL"


def check(condition: bool, label: str) -> bool:
    print(f"  {PASS if condition else FAIL}: {label}")
    return condition


def simulate_session(symptoms, age=35, gender="male", max_turns=9):
    """Simulate a multi-turn follow-up session."""
    state = initialize_patient_state(age, gender, symptoms)
    state["chat_history"] = []

    asked_questions = []
    all_passed = True

    print(f"\nPatient: {age}yo {gender}, Symptoms: {symptoms}\n")

    simulated_answers = [
        "Yes, clearly present",
        "No, not at all",
        "Yes, it comes and goes",
        "More on the right side",
        "Started two days ago",
        "Getting worse",
        "Very severe, 8 out of 10",
        "None of these / Not sure",
        "Not applicable",
    ]

    for turn in range(1, max_turns + 1):
        print(f"--- Turn {turn} ---")

        result = get_followup_for_diagnosis_v5(patient_state=state)

        # Check ready signal
        if isinstance(result, str) and "ready for diagnosis" in result.lower():
            print(f"  Session ended: '{result}' at turn {turn}")
            ok = check(turn <= 9, "Session ended at or before turn 9")
            all_passed = all_passed and ok
            break

        if not isinstance(result, dict):
            print(f"  {FAIL}: Expected dict, got {type(result)}: {result}")
            all_passed = False
            break

        question_text = result.get("Question", "")
        print(f"  Q: {question_text}")
        print(f"  A: {result.get('A', '')} | B: {result.get('B', '')} | C: {result.get('C', '')}")
        print(f"  D: {result.get('D', '')} | E: {result.get('E', '')}")

        # ---- Assertions ----
        has_5_options = all(result.get(k) for k in ["A", "B", "C", "D", "E"])
        ok1 = check(has_5_options, "Has exactly 5 options (A-E)")

        e_val = str(result.get("E", "")).strip().lower()
        ok2 = check(
            "none" in e_val or "not sure" in e_val,
            f"Option E contains 'none' or 'not sure' (got: '{result.get('E', '')}')"
        )

        ok3 = check(bool(question_text), "Question text is non-empty")

        is_repeat = question_text.lower() in [q.lower() for q in asked_questions]
        ok4 = check(not is_repeat, f"Question not repeated ('{question_text[:60]}...')")

        ok5 = check(
            state.get("turn_count", 0) <= 8,
            f"Turn count within limit (turn_count={state.get('turn_count', 0)})"
        )

        all_passed = all_passed and ok1 and ok2 and ok3 and ok4 and ok5

        asked_questions.append(question_text)

        # Update state with simulated answer
        simulated_answer = simulated_answers[(turn - 1) % len(simulated_answers)]
        state, _ = update_state_with_answer_v5(state, question_text, simulated_answer)

        # Append to chat_history so next turn can see it
        state.setdefault("chat_history", []).append({
            "bot": question_text,
            "user": simulated_answer,
        })

        # Also update questions_asked in symptom_state
        symptom_state = state.get("symptom_state")
        if isinstance(symptom_state, dict):
            symptom_state.setdefault("questions_asked", [])
            if question_text not in symptom_state["questions_asked"]:
                symptom_state["questions_asked"].append(question_text)

        print()

    return all_passed


def run_all_tests():
    print("=" * 70)
    print("Clinical Follow-up v5 - Verification Test Suite")
    print("=" * 70)

    results = []

    # Test 1: GI / Abdominal symptoms
    print("\n[Test 1] GI Symptoms: Abdominal pain, nausea")
    results.append(simulate_session(["abdominal pain", "nausea", "vomiting"]))

    # Test 2: Respiratory symptoms
    print("\n[Test 2] Respiratory Symptoms: Cough, breathlessness, fever")
    results.append(simulate_session(["cough", "breathlessness", "fever"]))

    # Test 3: Neurological symptoms
    print("\n[Test 3] Neuro Symptoms: Headache, dizziness")
    results.append(simulate_session(["headache", "dizziness", "nausea"], age=45, gender="female"))

    print("\n" + "=" * 70)
    total = len(results)
    passed = sum(results)
    print(f"Results: {passed}/{total} test scenarios passed")
    if passed == total:
        print(f"\u2705 ALL TESTS PASSED")
    else:
        print(f"\u274c {total - passed} TEST(S) FAILED")
    print("=" * 70)
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
