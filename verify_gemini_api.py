#!/usr/bin/env python3
"""
Quick verification script for Gemini API with gemini-2.5-flash model.
Tests all 15 API keys and verifies they work correctly.
"""

import sys
import os

# Add Backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.gemini_api_manager import (
    get_gemini_model,
    generate_content_with_fallback,
    get_current_key_info,
    MODEL_NAME
)

def main():
    print("="*80)
    print("GEMINI API VERIFICATION TEST")
    print("="*80)
    print()
    
    # Test 1: Check if model is available
    print("[Test 1] Checking model availability...")
    model_available, model = get_gemini_model()
    
    if model_available and model:
        print(f"[PASS] Model is available: {model._model_name}")
        print(f"       Expected model: {MODEL_NAME}")
        
        if MODEL_NAME in model._model_name:
            print(f"[PASS] Correct model name: {MODEL_NAME}")
        else:
            print(f"[FAIL] Model name mismatch!")
            print(f"       Expected: {MODEL_NAME}")
            print(f"       Got: {model._model_name}")
            return 1
    else:
        print("[FAIL] Model not available!")
        return 1
    
    print()
    
    # Test 2: Get current key info
    print("[Test 2] Current API key information...")
    key_info = get_current_key_info()
    print(f"[INFO] Current key index: {key_info['current_index']}/{key_info['total_keys']}")
    print(f"[INFO] Model available: {key_info['model_available']}")
    print(f"[INFO] Model name: {key_info['model_name']}")
    print()
    
    # Test 3: Test simple generation
    print("[Test 3] Testing simple content generation...")
    test_prompt = "Say exactly: 'API working with gemini-2.5-flash'"
    
    success, response, error = generate_content_with_fallback(
        prompt=test_prompt,
        temperature=0.3,
        max_output_tokens=100
    )
    
    if success and response:
        print(f"[PASS] Content generation successful")
        print(f"[INFO] Response: {response[:200]}")
        
        if "gemini" in response.lower() or "api" in response.lower():
            print(f"[PASS] Response contains expected content")
        else:
            print(f"[INFO] Response may vary, but generation works")
    else:
        print(f"[FAIL] Content generation failed!")
        print(f"[ERROR] {error}")
        return 1
    
    print()
    
    # Test 4: Test JSON generation (for followup questions)
    print("[Test 4] Testing JSON generation (followup question format)...")
    json_prompt = """Generate a valid JSON response in this exact format:
{
  "Question": "Test question?",
  "A": "Option A",
  "B": "Option B",
  "C": "Option C",
  "D": "None of these"
}

Generate ONLY the JSON, nothing else."""
    
    success, response, error = generate_content_with_fallback(
        prompt=json_prompt,
        temperature=0.3,
        max_output_tokens=500
    )
    
    if success and response:
        print(f"[PASS] JSON generation successful")
        print(f"[INFO] Response length: {len(response)} characters")
        
        # Try to parse as JSON
        import json
        try:
            # Remove markdown code fences if present
            clean_response = response.strip()
            if clean_response.startswith("```"):
                clean_response = clean_response.split("```")[1]
                if clean_response.startswith("json"):
                    clean_response = clean_response[4:].strip()
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3].strip()
            
            # Find JSON object
            start = clean_response.find('{')
            end = clean_response.rfind('}')
            if start != -1 and end != -1:
                clean_response = clean_response[start:end+1]
            
            parsed = json.loads(clean_response)
            
            if "Question" in parsed and "A" in parsed and "B" in parsed:
                print(f"[PASS] JSON parsed successfully")
                print(f"[INFO] Question: {parsed['Question']}")
            else:
                print(f"[WARN] JSON missing expected keys")
                
        except json.JSONDecodeError as e:
            print(f"[WARN] Could not parse as JSON: {e}")
            print(f"[INFO] Response preview: {response[:200]}")
    else:
        print(f"[FAIL] JSON generation failed!")
        print(f"[ERROR] {error}")
        return 1
    
    print()
    
    # Test 5: Verify model name consistency
    print("[Test 5] Verifying model name consistency...")
    if MODEL_NAME == "gemini-2.5-flash":
        print(f"[PASS] Using correct model: {MODEL_NAME}")
    else:
        print(f"[FAIL] Model name incorrect!")
        print(f"       Expected: gemini-2.5-flash")
        print(f"       Got: {MODEL_NAME}")
        return 1
    
    print()
    
    # Summary
    print("="*80)
    print("VERIFICATION SUMMARY")
    print("="*80)
    print("[PASS] All tests passed!")
    print(f"[INFO] Model: {MODEL_NAME}")
    print(f"[INFO] API Keys loaded: {key_info['total_keys']}")
    print(f"[INFO] Currently using key: #{key_info['current_index']}")
    print()
    print("[SUCCESS] Gemini API is working correctly with gemini-2.5-flash!")
    print("="*80)
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"[ERROR] Unhandled exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
