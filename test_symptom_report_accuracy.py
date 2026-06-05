#!/usr/bin/env python3
"""Verify diagnosis reports reflect submitted symptoms."""

import json
import sys
import time

import requests

BASE = "http://localhost:8000"

TEST_CASES = [
    {
        "name": "Respiratory",
        "symptoms": "fever, cough, sore throat",
        "expected_symptoms": ["fever", "cough", "sore throat"],
        "expected_diseases": [
            "influenza", "flu", "common cold", "covid", "pharyngitis",
            "bronchitis", "pneumonia", "viral",
        ],
    },
    {
        "name": "GI",
        "symptoms": "nausea, vomiting, abdominal pain",
        "expected_symptoms": ["nausea", "vomiting", "abdominal pain"],
        "expected_diseases": [
            "gastroenteritis", "food poisoning", "gastritis",
            "appendicitis", "peptic",
        ],
    },
    {
        "name": "Neuro",
        "symptoms": "severe headache, dizziness, blurred vision",
        "expected_symptoms": ["headache", "dizziness", "blurred vision"],
        "expected_diseases": [
            "migraine", "hypertension", "vertigo", "tension",
            "stroke", "meningitis",
        ],
    },
]


def norm(value):
    return str(value).lower().strip()


def overlap(items, keywords):
    text = " ".join(norm(x) for x in items)
    return any(keyword in text for keyword in keywords)


def run_case(test_case):
    print(f"\n--- {test_case['name']} case: {test_case['symptoms']} ---")
    patient = {
        "name": "Test Patient",
        "age": 30,
        "gender": "Male",
        "symptoms": test_case["symptoms"],
        "weight": 70,
        "height": 175,
        "occupation": "Engineer",
        "location": {"country": "India", "state": "Maharashtra", "city": "Mumbai"},
        "physical_activity": "Moderate",
        "diet_type": "Mixed",
    }

    response = requests.post(f"{BASE}/symptom", json=patient, timeout=30)
    if response.status_code != 200:
        print(f"FAIL: symptom submit {response.status_code} {response.text[:200]}")
        return False

    payload = response.json()
    session_id = payload.get("session_id") or payload.get("sessionId")
    print(f"Session: {session_id}")

    time.sleep(1)
    report_response = requests.get(f"{BASE}/generate_report/{session_id}", timeout=120)
    if report_response.status_code != 200:
        print(f"FAIL: report {report_response.status_code} {report_response.text[:300]}")
        return False

    response_payload = report_response.json()
    report = response_payload.get("report") or response_payload
    main_symptoms = report.get("MainSymptoms") or []
    top_matches = report.get("TopDiseaseMatches") or []
    disease_names = []
    for match in top_matches:
        if isinstance(match, dict):
            disease_names.append(match.get("Name") or match.get("name") or "")

    clinical = report.get("ClinicalSummary") or ""
    urgency = report.get("Urgency") or ""

    print(f"MainSymptoms: {main_symptoms}")
    print(f"Top diseases: {disease_names[:3]}")
    print(f"Urgency: {urgency}")
    print(f"ClinicalSummary: {clinical[:120]}...")

    checks = {
        "report_main_symptoms_match": overlap(
            main_symptoms,
            [norm(symptom) for symptom in test_case["expected_symptoms"]],
        ),
        "disease_matches_relevant": (
            overlap(disease_names, test_case["expected_diseases"])
            or overlap([clinical], test_case["expected_diseases"])
        ),
        "has_clinical_summary": bool(clinical.strip()),
        "has_top_matches": len(top_matches) > 0,
    }

    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

    case_passed = all(checks.values())
    print("RESULT:", "PASS" if case_passed else "FAIL")
    return case_passed


def main():
    print("=" * 70)
    print("SYMPTOM-BASED REPORT GENERATION TEST")
    print("=" * 70)

    try:
        health = requests.get(f"{BASE}/health", timeout=5)
        health.raise_for_status()
    except Exception as exc:
        print(f"Backend not available: {exc}")
        return 1

    passed = sum(1 for case in TEST_CASES if run_case(case))
    total = len(TEST_CASES)

    print("\n" + "=" * 70)
    print(f"SUMMARY: {passed}/{total} cases passed")
    print("=" * 70)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
