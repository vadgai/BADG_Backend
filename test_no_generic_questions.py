"""
Test to ensure NO generic/default questions are ever generated.
This test validates that the fallback system produces ONLY clinical questions.
"""

import sys
sys.path.insert(0, '.')

from Followup_Generation.followup import get_followup_for_diagnosis

# List of FORBIDDEN generic question patterns
FORBIDDEN_PATTERNS = [
    "any other symptoms",
    "how long have you been",
    "how are you feeling",
    "anything else",
    "past medical history",
    "started suddenly or gradually",  # The specific one user reported
    "sudden onset",  # Part of the generic question
    "tell me more",
    "what else",
    "any additional",
]

def test_no_generic_questions():
    """Test that system never generates generic questions"""
    
    print("="*80)
    print("TESTING: No Generic Questions Policy")
    print("="*80)
    print()
    
    # Test scenarios
    test_cases = [
        {
            "name": "Minimal symptoms (fever only)",
            "symptoms": ["fever"],
            "age": 30,
            "gender": "Male"
        },
        {
            "name": "Vague symptoms",
            "symptoms": ["not feeling well"],
            "age": 25,
            "gender": "Female"
        },
        {
            "name": "Pain symptoms",
            "symptoms": ["pain"],
            "age": 40,
            "gender": "Male"
        },
        {
            "name": "Multiple symptoms",
            "symptoms": ["fever", "cough", "headache"],
            "age": 35,
            "gender": "Female"
        },
        {
            "name": "GI symptoms",
            "symptoms": ["nausea", "vomiting"],
            "age": 28,
            "gender": "Male"
        }
    ]
    
    all_passed = True
    
    for idx, case in enumerate(test_cases, 1):
        print(f"\n[Test {idx}] {case['name']}")
        print(f"Symptoms: {case['symptoms']}")
        
        try:
            result = get_followup_for_diagnosis(
                age=case['age'],
                gender=case['gender'],
                symptoms=case['symptoms'],
                chat_history=""
            )
            
            if isinstance(result, dict) and "Question" in result:
                question = result["Question"].lower()
                print(f"Generated: {result['Question']}")
                
                # Check for forbidden patterns
                violations = []
                for pattern in FORBIDDEN_PATTERNS:
                    if pattern.lower() in question:
                        violations.append(pattern)
                
                if violations:
                    print(f"[FAIL] Generic question detected!")
                    print(f"       Violations: {violations}")
                    all_passed = False
                else:
                    print(f"[PASS] Clinical question (no generic patterns)")
                    
                # Check options too
                for opt_key in ["A", "B", "C", "D"]:
                    if opt_key in result:
                        opt = result[opt_key].lower()
                        for pattern in FORBIDDEN_PATTERNS:
                            if pattern.lower() in opt:
                                print(f"[FAIL] Generic pattern in option {opt_key}: {pattern}")
                                all_passed = False
            
            elif result == "Ready for diagnosis":
                print("[INFO] System ready for diagnosis (expected)")
            else:
                print(f"[WARN] Unexpected result type: {type(result)}")
                
        except Exception as e:
            print(f"[ERROR] Test failed with exception: {e}")
            all_passed = False
    
    print("\n" + "="*80)
    if all_passed:
        print("[SUCCESS] All tests passed - No generic questions detected!")
    else:
        print("[FAILURE] Some tests failed - Generic questions found!")
    print("="*80)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit_code = test_no_generic_questions()
    sys.exit(exit_code)
