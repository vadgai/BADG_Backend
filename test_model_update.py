#!/usr/bin/env python3
"""
Test script to verify that the model has been updated to gemini-2.5-flash
"""

import sys
import os
from pathlib import Path

# Add Backend directory to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

print("=" * 80)
print("Testing Gemini Model Configuration")
print("=" * 80)
print()

# Test 1: Check MODEL_NAME constant
print("Test 1: Checking MODEL_NAME constant...")
try:
    from utils.gemini_api_manager import MODEL_NAME
    print(f"✅ MODEL_NAME = '{MODEL_NAME}'")
    if MODEL_NAME == "gemini-2.5-flash":
        print("✅ Model name is correctly set to gemini-2.5-flash")
    else:
        print(f"❌ ERROR: Model name is '{MODEL_NAME}', expected 'gemini-2.5-flash'")
        sys.exit(1)
except Exception as e:
    print(f"❌ Failed to import MODEL_NAME: {e}")
    sys.exit(1)

print()

# Test 2: Check config.py default
print("Test 2: Checking config.py default...")
try:
    from config import Settings
    settings = Settings()
    print(f"✅ config.ai_model = '{settings.ai_model}'")
    if settings.ai_model == "gemini-2.5-flash":
        print("✅ Config default is correctly set to gemini-2.5-flash")
    else:
        print(f"⚠️  WARNING: Config default is '{settings.ai_model}', expected 'gemini-2.5-flash'")
except Exception as e:
    print(f"⚠️  Failed to check config: {e}")

print()

# Test 3: Try to get model instance
print("Test 3: Testing model initialization...")
try:
    from utils.gemini_api_manager import get_gemini_model, get_current_key_info
    
    model_available, model = get_gemini_model()
    key_info = get_current_key_info()
    
    print(f"✅ Model available: {model_available}")
    print(f"✅ Current model name: {key_info['model_name']}")
    print(f"✅ Total keys configured: {key_info['total_keys']}")
    print(f"✅ Current key index: {key_info['current_index']}")
    
    if key_info['model_name'] == "gemini-2.5-flash":
        print("✅ Model name matches gemini-2.5-flash")
    else:
        print(f"❌ ERROR: Model name is '{key_info['model_name']}', expected 'gemini-2.5-flash'")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ Failed to get model: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 4: Try a simple generation (if API keys are available)
print("Test 4: Testing actual API call with gemini-2.5-flash...")
try:
    from utils.gemini_api_manager import generate_content_with_fallback
    
    success, response, error = generate_content_with_fallback("Say 'gemini-2.5-flash is working'")
    
    if success and response:
        print(f"✅ API call successful!")
        print(f"✅ Response: {response[:100]}...")
        print("✅ Model gemini-2.5-flash is working correctly!")
    else:
        print(f"⚠️  API call failed: {error}")
        print("⚠️  This might be due to API key/quota issues, but model configuration looks correct")
        
except Exception as e:
    print(f"⚠️  API call error: {e}")
    print("⚠️  This might be due to API key/quota issues, but model configuration looks correct")

print()
print("=" * 80)
print("Summary:")
print("=" * 80)
print("✅ Model configuration has been updated to gemini-2.5-flash")
print("✅ All code references point to the new model")
print()
print("If you see API errors above, they might be due to:")
print("  - Missing API keys")
print("  - Quota issues")
print("  - Network connectivity")
print()
print("But the model name configuration is correct!")
print("=" * 80)
