#!/usr/bin/env python3
"""
Quick test to verify gemini-2.5-flash model is configured correctly
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("Quick Model Configuration Test")
print("=" * 60)

# Test 1: Import and check MODEL_NAME
try:
    from utils.gemini_api_manager import MODEL_NAME, get_current_key_info
    print(f"\n✅ MODEL_NAME: {MODEL_NAME}")
    
    if MODEL_NAME == "gemini-2.5-flash":
        print("✅ Model name is correct: gemini-2.5-flash")
    else:
        print(f"❌ ERROR: Expected 'gemini-2.5-flash', got '{MODEL_NAME}'")
        sys.exit(1)
    
    # Test 2: Check current key info
    key_info = get_current_key_info()
    print(f"\n📊 Model Status:")
    print(f"   - Model Name: {key_info['model_name']}")
    print(f"   - Model Available: {key_info['model_available']}")
    print(f"   - Total Keys: {key_info['total_keys']}")
    print(f"   - Current Key Index: {key_info['current_index']}")
    
    if key_info['model_name'] != "gemini-2.5-flash":
        print(f"\n❌ ERROR: Key info shows model as '{key_info['model_name']}', expected 'gemini-2.5-flash'")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✅ ALL CHECKS PASSED!")
    print("=" * 60)
    print("\n⚠️  IMPORTANT: Restart your uvicorn server for changes to take effect!")
    print("   The model is initialized when the server starts.")
    print()
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
