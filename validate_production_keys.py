#!/usr/bin/env python3
"""
Production Gemini API Keys Validation Script

This script validates that Gemini API keys are properly configured for production.
Run this script before deploying to ensure keys are set correctly.

Usage:
    python validate_production_keys.py
    python validate_production_keys.py --check-remote
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_local_keys():
    """Check if keys are set in local environment."""
    print("🔍 Checking local environment for Gemini API keys...")
    print("=" * 80)
    
    keys_found = []
    
    # Check for GEMINI_API_KEY_1 through GEMINI_API_KEY_20
    for i in range(1, 21):
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key and key.strip():
            keys_found.append(f"GEMINI_API_KEY_{i}")
            print(f"✅ Found: GEMINI_API_KEY_{i} (length: {len(key.strip())})")
    
    # Check legacy keys
    legacy_keys = ["GOOGLE_API_KEY", "GEMINI_API_KEY"]
    for key_name in legacy_keys:
        key = os.getenv(key_name)
        if key and key.strip():
            keys_found.append(key_name)
            print(f"✅ Found: {key_name} (length: {len(key.strip())})")
    
    if not keys_found:
        print("❌ No Gemini API keys found in environment!")
        print("\nTo set keys:")
        print("  1. Create a .env file in Backend/ directory")
        print("  2. Add: GEMINI_API_KEY_1=your-actual-api-key")
        print("  3. Or set as system environment variable")
        return False
    
    print(f"\n✅ Found {len(keys_found)} key(s): {', '.join(keys_found)}")
    return True


def validate_key_format(key: str) -> bool:
    """Validate that the key has the correct format."""
    if not key:
        return False
    key = key.strip()
    # Gemini API keys typically start with "AIza" and are ~39 characters
    if len(key) < 20:
        return False
    if not key.startswith("AIza"):
        print(f"⚠️  Warning: Key doesn't start with 'AIza' (unusual format)")
    return True


def test_key(key: str, key_name: str) -> bool:
    """Test if a key actually works."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content("Say 'API key works'")
        if response and response.text:
            print(f"✅ {key_name}: Key is valid and working")
            return True
        else:
            print(f"❌ {key_name}: Key returned empty response")
            return False
    except Exception as e:
        print(f"❌ {key_name}: Key test failed - {str(e)}")
        return False


def main():
    """Main validation function."""
    print("=" * 80)
    print("🔐 Production Gemini API Keys Validation")
    print("=" * 80)
    print()
    
    # Check environment
    environment = os.getenv("ENVIRONMENT", "development").lower()
    is_production = environment == "production"
    
    print(f"Environment: {environment}")
    print(f"Production mode: {is_production}")
    print()
    
    # Check for keys
    if not check_local_keys():
        print()
        print("=" * 80)
        print("❌ VALIDATION FAILED: No API keys found")
        print("=" * 80)
        sys.exit(1)
    
    print()
    print("=" * 80)
    print("🧪 Testing API keys...")
    print("=" * 80)
    
    # Test each key
    keys_tested = 0
    keys_working = 0
    
    # Test GEMINI_API_KEY_1 through GEMINI_API_KEY_20
    for i in range(1, 21):
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key and key.strip():
            keys_tested += 1
            if validate_key_format(key):
                if test_key(key.strip(), f"GEMINI_API_KEY_{i}"):
                    keys_working += 1
            else:
                print(f"❌ GEMINI_API_KEY_{i}: Invalid key format")
    
    # Test legacy keys
    for key_name in ["GOOGLE_API_KEY", "GEMINI_API_KEY"]:
        key = os.getenv(key_name)
        if key and key.strip():
            keys_tested += 1
            if validate_key_format(key):
                if test_key(key.strip(), key_name):
                    keys_working += 1
            else:
                print(f"❌ {key_name}: Invalid key format")
    
    print()
    print("=" * 80)
    print("📊 Validation Summary")
    print("=" * 80)
    print(f"Keys found: {keys_tested}")
    print(f"Keys working: {keys_working}")
    print(f"Keys failed: {keys_tested - keys_working}")
    print()
    
    if keys_working == 0:
        print("❌ VALIDATION FAILED: No working API keys found")
        print()
        print("Troubleshooting:")
        print("  1. Verify your API key is correct")
        print("  2. Check that you have quota for Gemini API")
        print("  3. Ensure the key has proper permissions")
        print("  4. Test the key manually in Google AI Studio")
        sys.exit(1)
    elif keys_working < keys_tested:
        print("⚠️  WARNING: Some keys are not working")
        print(f"   {keys_working} of {keys_tested} keys are functional")
        print("   Consider removing or fixing failed keys")
    else:
        print("✅ VALIDATION PASSED: All keys are working")
    
    if is_production:
        print()
        print("=" * 80)
        print("🚀 Production Deployment Checklist")
        print("=" * 80)
        print("✅ Keys are set in environment")
        print("✅ Keys are validated and working")
        print()
        print("Next steps:")
        print("  1. Ensure keys are set in Google Cloud Run environment variables")
        print("  2. Deploy your application")
        print("  3. Verify keys are working in production:")
        print("     - Check /health endpoint")
        print("     - Check /api/diagnostic/gemini-keys endpoint")
        print("     - Check Cloud Run logs for initialization messages")
    else:
        print()
        print("ℹ️  Development mode: Keys are validated locally")
        print("   For production, ensure keys are set in deployment platform")
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Validation error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

