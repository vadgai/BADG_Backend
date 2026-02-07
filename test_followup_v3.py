"""
Test script for Follow-Up Question Generator v3.0
"""

import sys
import json

sys.path.insert(0, '.')

from Followup_Generation.followup_v3 import get_followup_for_diagnosis_v3

def test_v3():
    print("="*80)
    print("Testing Clinical Follow-Up Question Generator v3.0")
    print("="*80)
    print()
    
    # Test case 1: Basic symptoms
    print("[Test 1] Basic symptoms: fever, headache")
    result1 = get_followup_for_diagnosis_v3(
        age=35,
        gender="Female",
        symptoms=["fever", "headache", "body ache"],
        chat_history=""
    )
    
    print("\nResult:")
    print(json.dumps(result1, indent=2))
    
    question_count = len(result1.get("follow_up_questions", []))
    print(f"\n[VALIDATION]")
    print(f"Question count: {question_count}")
    print(f"Expected: 7-10")
    print(f"Status: {'[PASS]' if 7 <= question_count <= 10 else '[FAIL]'}")
    
    # Check for generic questions
    generic_patterns = [
        "any other symptoms",
        "how long have you been",
        "how are you feeling"
    ]
    
    generic_found = False
    for q in result1.get("follow_up_questions", []):
        question_lower = q.get("question", "").lower()
        for pattern in generic_patterns:
            if pattern in question_lower:
                print(f"[WARNING] Generic question detected: {q['question']}")
                generic_found = True
    
    if not generic_found:
        print("[PASS] No generic questions detected")
    
    print("\n" + "="*80)
    print("Test completed!")
    print("="*80)
    
    return True

if __name__ == "__main__":
    try:
        test_v3()
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
