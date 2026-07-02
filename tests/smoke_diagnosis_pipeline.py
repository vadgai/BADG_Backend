"""
Lightweight smoke test for the diagnosis rule engine (no LLM / no network).

Run:  python -m tests.smoke_diagnosis_pipeline
Prints how many diseases load and the top-5 ranking for a few canonical cases,
so we can confirm accuracy changes before/after without hitting Gemini.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import diagnosis_rule_engine as engine  # noqa: E402
from diagnosis_rule_engine import (  # noqa: E402
    load_diseases_from_folder,
    build_disease_profiles,
    analyze_case,
    _feature_match,
)

CASES = [
    {
        "label": "Appendicitis-like",
        "age": 24, "gender": "male",
        "symptoms": ["right lower abdominal pain", "nausea", "fever", "loss of appetite"],
        "negatives": ["diarrhea"], "red_flags": [],
    },
    {
        "label": "Pneumonia-like",
        "age": 60, "gender": "male",
        "symptoms": ["cough", "fever", "shortness of breath", "chest pain"],
        "negatives": [], "red_flags": [],
    },
    {
        "label": "Dengue-like (India)",
        "age": 30, "gender": "female",
        "symptoms": ["high fever", "severe headache", "joint pain", "rash"],
        "negatives": ["cough"], "red_flags": [],
    },
    {
        "label": "Cardiac red-flag",
        "age": 58, "gender": "male",
        "symptoms": ["chest pain", "shortness of breath", "sweating"],
        "negatives": [], "red_flags": ["chest pain"],
    },
]


def main():
    n = load_diseases_from_folder()
    build_disease_profiles()
    print(f"diseases loaded (files counted): {n}")
    print(f"unique registry keys (kept): {len(engine.DISEASE_REGISTRY)}")
    print(f"profiles built: {len(engine.DISEASE_PROFILES)}")

    # Precision probe: a generic token should NOT match an unrelated specific feature.
    print("\n-- feature-match precision probes --")
    probes = [
        ("pain", ["chest pain"]),          # generic 'pain' vs specific 'chest pain'
        ("chest", ["chest pain relief"]),  # 'chest' vs unrelated phrase
        ("fever", ["high fever"]),         # should still match (fever is a real subset word)
        ("cough", ["dry cough"]),          # should still match
        ("sob", ["shortness of breath"]),  # synonym expansion should still work
    ]
    for term, values in probes:
        print(f"  match({term!r}, {values}) = {_feature_match(term, values)}")

    for case in CASES:
        res = analyze_case(
            age=case["age"], gender=case["gender"], symptoms=case["symptoms"],
            negatives=case["negatives"], red_flags=case["red_flags"],
        )
        print(f"\n== {case['label']} ({case['age']}/{case['gender']}) ==")
        print(f"   symptoms: {case['symptoms']}")
        for i, c in enumerate(res.get("conditions", [])[:5], 1):
            print(f"   {i}. {c['name']:<40} score={c['score']:.3f} {c['probability']:<9} {c.get('urgency')}")


if __name__ == "__main__":
    main()
