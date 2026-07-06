#!/usr/bin/env python3
"""Verify all 4 follow-up refactor phases are wired correctly."""

import ast
import os
import sys

BACKEND = os.path.dirname(os.path.abspath(__file__))
FAILURES = []


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def phase1_module_and_feature_tracking():
    print("\n=== Phase 1: Module + feature_ids_asked ===")
    required = [
        "followup/constants.py",
        "followup/feature_tracking.py",
        "followup/orchestrator.py",
    ]
    for rel in required:
        check(f"file exists: {rel}", os.path.isfile(os.path.join(BACKEND, rel)))

    from followup.constants import JACCARD_REPEAT_THRESHOLD, MAX_FOLLOWUP_QUESTIONS, MIN_FOLLOWUP_QUESTIONS
    from followup.feature_tracking import record_sent_question, is_feature_already_asked

    check("constants loaded", MIN_FOLLOWUP_QUESTIONS == 4 and MAX_FOLLOWUP_QUESTIONS == 10)
    check("Jaccard threshold", JACCARD_REPEAT_THRESHOLD == 0.72)

    ss = {"questions_asked": [], "feature_ids_asked": []}
    record_sent_question(ss, {"Question": "Q1", "feature_id": "fever_pattern", "A": "a", "B": "b", "C": "c", "D": "d"})
    check("feature_ids_asked tracked", is_feature_already_asked(ss, "fever_pattern"))
    check("questions_asked tracked", "Q1" in ss.get("questions_asked", []))


def phase2_critic_and_validators():
    print("\n=== Phase 2: Critic + unified validators ===")
    from followup.agents.critic import QuestionCritic
    from followup.constants import JACCARD_REPEAT_THRESHOLD
    from followup.validators.repetition import is_repeated_question
    from followup.validators.mcq_structure import normalize_mcq_keys, validate_mcq_structure
    from followup.validators.mcq_quality import validate_mcq_quality
    from diagnosis_methods.patient_state import initialize_patient_state

    ss = {"questions_asked": ["How long have you had fever?"], "feature_ids_asked": ["duration"], "_asked_option_sigs": []}
    critic = QuestionCritic(ss)

    good = {
        "Question": "Do you have night sweats with fever?",
        "A": "Yes, drenching sweats", "B": "Mild sweats only",
        "C": "No night sweats", "D": "Not sure when sweats occur",
        "E": "None of these / Not sure", "feature_id": "night_sweats",
    }
    check("critic accepts valid MCQ", critic.validate(good, ss["questions_asked"]))

    bad_repeat = dict(good)
    bad_repeat["Question"] = "How long have you had fever?"
    check("critic rejects text repeat", not critic.validate(bad_repeat, ss["questions_asked"]))

    bad_feature = dict(good)
    bad_feature["feature_id"] = "duration"
    ok, reason = critic.validate_with_reason(bad_feature, ss["questions_asked"])
    check("critic rejects feature repeat", not ok and reason == "feature_repeated")

    parsed = normalize_mcq_keys({"question": "Test?", "a": "1", "b": "2", "c": "3", "d": "4"})
    check("mcq normalize", validate_mcq_structure(parsed))

    state = initialize_patient_state(25, "Female", ["cough"])
    state["symptom_state"] = {"questions_asked": []}
    ok, _ = validate_mcq_quality(good, state)
    check("mcq quality validator", ok)

    from diagnosis_methods.state_followup import _is_repeated_question

    check(
        "state_followup delegates unified repeat",
        _is_repeated_question(
            "How long have you had fever",
            ["How long have you had fever?"],
        ),
    )
    check(
        "unified threshold is 0.72",
        is_repeated_question("How long have you had fever", ["How long have you had fever?"]),
    )


def phase3_app_split_and_fallbacks():
    print("\n=== Phase 3: app.py split + fallbacks + websocket ===")
    app_path = os.path.join(BACKEND, "app.py")
    with open(app_path, encoding="utf-8") as fh:
        app_src = fh.read()
    app_lines = app_src.count("\n") + 1

    check("app.py slimmed (<1100 lines)", app_lines < 1100, f"{app_lines} lines")
    check("app delegates websocket", "handle_followup_websocket" in app_src)
    check("app no inline _select_question_candidate", "_select_question_candidate" not in app_src)
    check("app no inline _force_unique_min_depth", "_force_unique_min_depth_question" not in app_src)

    from followup.websocket_handler import handle_followup_websocket
    from followup.selection import select_question_candidate
    from followup.fallbacks.min_depth import build_min_depth_question
    from followup.fallbacks.turn_templates import build_turn_indexed_question
    from followup.fallbacks.contextual import build_contextual_fallback
    from followup.session_helpers import ensure_states, record_question_trace

    check("websocket_handler importable", callable(handle_followup_websocket))
    check("selection importable", callable(select_question_candidate))
    check("fallbacks importable", all(map(callable, [
        build_min_depth_question, build_turn_indexed_question, build_contextual_fallback,
    ])))
    check("session_helpers importable", callable(ensure_states))


def phase4_orchestrator_and_legacy():
    print("\n=== Phase 4: Orchestrator + legacy facade ===")
    from followup.orchestrator import get_next_followup_question, update_state_with_answer
    from Followup_Generation.followup_v5 import (
        get_followup_for_diagnosis_v5,
        update_state_with_answer_v5,
    )
    from Followup_Generation.followup import _normalize_mcq_keys, _validate_mcq_structure, get_followup_for_diagnosis
    from diagnosis_methods.state_followup import get_followup_from_state

    check("orchestrator exports", callable(get_next_followup_question))
    check("v5 facade", get_followup_for_diagnosis_v5 is get_next_followup_question)
    check("v5 update facade", update_state_with_answer_v5 is update_state_with_answer)
    check("legacy mcq helpers", callable(_normalize_mcq_keys) and callable(_validate_mcq_structure))
    check("legacy shim", callable(get_followup_for_diagnosis))
    check("state_followup delegates", get_followup_from_state.__doc__ and "orchestrator" in get_followup_from_state.__doc__.lower())

    followup_py = os.path.join(BACKEND, "Followup_Generation", "followup.py")
    with open(followup_py, encoding="utf-8") as fh:
        legacy_lines = sum(1 for _ in fh)
    check("legacy followup.py small", legacy_lines < 80, f"{legacy_lines} lines")


def syntax_all_followup_py():
    print("\n=== Syntax: all followup/*.py ===")
    followup_root = os.path.join(BACKEND, "followup")
    py_files = []
    for dp, _, fns in os.walk(followup_root):
        for fn in fns:
            if fn.endswith(".py"):
                py_files.append(os.path.join(dp, fn))
    for path in sorted(py_files):
        rel = os.path.relpath(path, BACKEND)
        try:
            with open(path, encoding="utf-8") as fh:
                ast.parse(fh.read())
            check(f"syntax {rel}", True)
        except SyntaxError as exc:
            check(f"syntax {rel}", False, str(exc))


def main():
    print("VADG Follow-up Phase Verification")
    phase1_module_and_feature_tracking()
    phase2_critic_and_validators()
    phase3_app_split_and_fallbacks()
    phase4_orchestrator_and_legacy()
    syntax_all_followup_py()

    print("\n" + "=" * 50)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s)")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL PHASE CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
