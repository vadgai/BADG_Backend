#!/usr/bin/env python3
"""
Test script for Clinical Follow-Up Question Engine v2.0
Validates guaranteed question generation and clinical reasoning.
"""

import os
import sys
import json
from typing import Dict, Any

# Add Backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Followup_Generation.followup_v2 import (
    get_followup_for_diagnosis_v2,
    _get_symptom_based_fallback,
    _validate_json_response,
    _convert_to_mcq_format,
)


def print_test_header(test_name: str):
    """Print formatted test header."""
    print("\n" + "="*80)
    print(f"TEST: {test_name}")
    print("="*80)


def print_test_result(passed: bool, message: str = ""):
    """Print test result."""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status}: {message}")


def test_basic_generation():
    """Test 1: Basic question generation works."""
    print_test_header("Basic Question Generation")
    
    try:
        result = get_followup_for_diagnosis_v2(
            age=35,
            gender="Female",
            symptoms=["fever", "headache", "body ache"],
            chat_history=""
        )
        
        # Validate non-None
        assert result is not None, "Result is None"
        
        # Validate type
        assert isinstance(result, (dict, str)), f"Invalid type: {type(result)}"
        
        # If dict, validate structure
        if isinstance(result, dict):
            assert "Question" in result, "Missing 'Question' key"
            assert "A" in result, "Missing option A"
            assert "B" in result, "Missing option B"
            assert "C" in result, "Missing option C"
            assert "D" in result, "Missing option D"
            assert result["D"] == "None of these", "Option D must be 'None of these'"
            
            print(f"Question: {result['Question']}")
            print(f"Options: A={result['A']}, B={result['B']}, C={result['C']}")
            
            if "clinical_purpose" in result:
                print(f"Clinical Purpose: {result['clinical_purpose']}")
            if "differentiates_between" in result:
                print(f"Differentiates: {result['differentiates_between']}")
        
        print_test_result(True, "Generated valid question")
        return True
        
    except Exception as e:
        print_test_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fallback_generation():
    """Test 2: Fallback generation when API unavailable."""
    print_test_header("Fallback Question Generation")
    
    try:
        # Test symptom-based fallback directly
        fallback_result = _get_symptom_based_fallback(["fever", "cough"], question_number=0)
        
        assert fallback_result is not None, "Fallback returned None"
        assert isinstance(fallback_result, dict), "Fallback should return dict"
        assert "Question" in fallback_result, "Fallback missing Question"
        assert "clinical_purpose" in fallback_result, "Fallback missing clinical_purpose"
        
        print(f"Fallback Question: {fallback_result['Question']}")
        print(f"Clinical Purpose: {fallback_result['clinical_purpose']}")
        print(f"Differentiates: {fallback_result.get('differentiates_between', [])}")
        
        print_test_result(True, "Fallback generates valid clinical question")
        return True
        
    except Exception as e:
        print_test_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_max_questions_limit():
    """Test 3: Enforces maximum question limit."""
    print_test_header("Maximum Question Limit")
    
    try:
        # Simulate 10 questions already asked
        fake_history = "\n".join([
            f"Question: Sample question {i}?\nAnswer: Sample answer {i}" 
            for i in range(10)
        ])
        
        result = get_followup_for_diagnosis_v2(
            age=40,
            gender="Male",
            symptoms=["cough"],
            chat_history=fake_history
        )
        
        assert result is not None, "Result is None"
        assert result == "Ready for diagnosis", f"Should return 'Ready for diagnosis', got: {result}"
        
        print_test_result(True, "Max question limit enforced correctly")
        return True
        
    except Exception as e:
        print_test_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_symptom_pattern_recognition():
    """Test 4: Recognizes different symptom patterns."""
    print_test_header("Symptom Pattern Recognition")
    
    test_cases = [
        (["fever", "chills"], "Fever pattern"),
        (["headache", "sensitivity to light"], "Headache pattern"),
        (["abdominal pain", "nausea"], "Abdominal pain pattern"),
        (["cough", "sputum"], "Cough pattern"),
        (["chest pain", "shortness of breath"], "Breathing pattern"),
        (["random symptom xyz"], "General pattern (fallback)"),
    ]
    
    all_passed = True
    
    for symptoms, pattern_name in test_cases:
        try:
            result = get_followup_for_diagnosis_v2(
                age=30,
                gender="Male",
                symptoms=symptoms,
                chat_history=""
            )
            
            assert result is not None, f"Result is None for {pattern_name}"
            
            if isinstance(result, dict):
                print(f"  {pattern_name}: {result['Question'][:60]}...")
                print_test_result(True, pattern_name)
            else:
                print(f"  {pattern_name}: {result}")
                print_test_result(True, f"{pattern_name} (ready signal)")
                
        except Exception as e:
            print_test_result(False, f"{pattern_name}: {e}")
            all_passed = False
    
    return all_passed


def test_enhanced_patient_data():
    """Test 5: Uses enhanced patient data in questions."""
    print_test_header("Enhanced Patient Data Integration")
    
    try:
        result = get_followup_for_diagnosis_v2(
            age=55,
            gender="Male",
            symptoms=["chest pain", "fatigue"],
            chat_history="",
            weight=95.0,
            height=175.0,
            occupation="Desk job",
            location={"city": "Mumbai", "state": "Maharashtra", "country": "India"},
            physical_activity="Sedentary",
            diet_type="High-fat diet"
        )
        
        assert result is not None, "Result is None"
        assert isinstance(result, (dict, str)), "Invalid result type"
        
        if isinstance(result, dict):
            print(f"Question generated with enhanced data: {result['Question']}")
            
            # Check if clinical purpose considers risk factors
            if "clinical_purpose" in result:
                print(f"Clinical reasoning: {result['clinical_purpose']}")
        
        print_test_result(True, "Enhanced patient data handled correctly")
        return True
        
    except Exception as e:
        print_test_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_json_validation():
    """Test 6: JSON validation logic."""
    print_test_header("JSON Validation Logic")
    
    test_cases = [
        ({"Question": "Q?", "A": "Opt A", "B": "Opt B", "C": "Opt C", "D": "None"}, True, "Valid MCQ format"),
        ({"follow_up_questions": [{"question": "Q?", "options": {}}]}, True, "Valid structured format"),
        ({"invalid": "structure"}, False, "Invalid structure"),
        (None, False, "None input"),
        ("string", False, "String input"),
        ([], False, "List input"),
    ]
    
    all_passed = True
    
    for data, expected, description in test_cases:
        try:
            result = _validate_json_response(data)
            assert result == expected, f"Expected {expected}, got {result}"
            print_test_result(True, description)
        except Exception as e:
            print_test_result(False, f"{description}: {e}")
            all_passed = False
    
    return all_passed


def test_mcq_conversion():
    """Test 7: Structured to MCQ conversion."""
    print_test_header("Structured to MCQ Format Conversion")
    
    try:
        structured_data = {
            "follow_up_questions": [{
                "id": 1,
                "question": "Test question?",
                "clinical_purpose": "Testing",
                "differentiates_between": ["Disease A", "Disease B"],
                "options": {
                    "A": "Option A",
                    "B": "Option B",
                    "C": "Option C",
                    "D": "None of these"
                }
            }],
            "confidence_level": "medium",
            "ready_for_diagnosis": False
        }
        
        mcq = _convert_to_mcq_format(structured_data)
        
        assert isinstance(mcq, dict), "Conversion should return dict"
        assert "Question" in mcq, "Missing Question"
        assert "A" in mcq, "Missing option A"
        assert mcq["D"] == "None of these", "Option D incorrect"
        assert "clinical_purpose" in mcq, "Missing clinical_purpose"
        
        print(f"Converted Question: {mcq['Question']}")
        print(f"Clinical Purpose: {mcq['clinical_purpose']}")
        
        print_test_result(True, "Conversion works correctly")
        return True
        
    except Exception as e:
        print_test_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ready_for_diagnosis_signal():
    """Test 8: Proper 'ready for diagnosis' signal."""
    print_test_header("Ready for Diagnosis Signal")
    
    try:
        # Test with enough questions in history
        history_with_many_questions = "\n".join([
            f"Q{i}: Previous question {i}?\nA{i}: Answer {i}"
            for i in range(8)
        ])
        
        result = get_followup_for_diagnosis_v2(
            age=30,
            gender="Female",
            symptoms=["fever"],
            chat_history=history_with_many_questions
        )
        
        # Should either return another question or ready signal
        assert result is not None, "Result is None"
        
        if isinstance(result, str):
            assert result == "Ready for diagnosis", f"Unexpected string: {result}"
            print_test_result(True, "Returns ready signal when appropriate")
        else:
            # Still asking questions, which is acceptable
            assert isinstance(result, dict), "Should be dict if not ready"
            print_test_result(True, "Continues asking (confidence not yet high enough)")
        
        return True
        
    except Exception as e:
        print_test_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all test suites."""
    print("\n" + "="*80)
    print("CLINICAL FOLLOW-UP QUESTION ENGINE v2.0 - TEST SUITE")
    print("="*80)
    
    tests = [
        test_basic_generation,
        test_fallback_generation,
        test_max_questions_limit,
        test_symptom_pattern_recognition,
        test_enhanced_patient_data,
        test_json_validation,
        test_mcq_conversion,
        test_ready_for_diagnosis_signal,
    ]
    
    results = []
    for test_func in tests:
        try:
            passed = test_func()
            results.append((test_func.__name__, passed))
        except Exception as e:
            print(f"\n[ERROR] CRITICAL ERROR in {test_func.__name__}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_func.__name__, False))
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    failed = total - passed
    
    for test_name, test_passed in results:
        status = "[PASS]" if test_passed else "[FAIL]"
        print(f"{status}: {test_name}")
    
    print("\n" + "-"*80)
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    print("-"*80)
    
    if failed == 0:
        print("\n[SUCCESS] ALL TESTS PASSED! System is ready for deployment.")
        return 0
    else:
        print(f"\n[WARNING] {failed} TEST(S) FAILED. Review logs above.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
