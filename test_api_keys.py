"""
Test script for Gemini API Multi-Key Manager
Verifies that all configured API keys are working correctly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from utils.gemini_api_manager import (
    test_all_api_keys, 
    get_current_key_info,
    generate_content_with_fallback
)

def main():
    print("=" * 80)
    print("🔑 GEMINI API MULTI-KEY MANAGER TEST")
    print("=" * 80)
    print()
    
    # Test 1: Check current configuration
    print("📋 Step 1: Checking current configuration...")
    current = get_current_key_info()
    print(f"   Current key index: #{current['current_index']}")
    print(f"   Total keys configured: {current['total_keys']}")
    print(f"   Model: {current['model_name']}")
    print(f"   Model available: {'✅ Yes' if current['model_available'] else '❌ No'}")
    print()
    
    if current['total_keys'] == 0:
        print("❌ ERROR: No API keys configured!")
        print("   Please add your keys to Backend/.env")
        print("   Example: GEMINI_API_KEY_1=your_key_here")
        return
    
    # Test 2: Test a simple generation
    print("📋 Step 2: Testing content generation...")
    print("   Sending test prompt: 'Say hello!'")
    success, response, error = generate_content_with_fallback("Say hello!")
    
    if success:
        print(f"   ✅ Success! Response: {response[:100]}...")
    else:
        print(f"   ❌ Failed: {error}")
    print()
    
    # Test 3: Test all keys comprehensively
    print("📋 Step 3: Testing all configured API keys...")
    print("   This may take a minute...")
    print()
    
    results = test_all_api_keys()
    
    print("=" * 80)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 80)
    print(f"Total keys configured: {results['total_keys']}")
    print(f"Working keys: {results['working_keys']} ✅")
    print(f"Failed keys: {results['failed_keys']} ❌")
    print()
    
    if results['working_keys'] == 0:
        print("⚠️  WARNING: No working API keys found!")
        print("   Please check your keys and try again.")
        print()
    
    # Detailed results
    print("🔍 DETAILED KEY STATUS")
    print("-" * 80)
    
    for key_info in results['keys']:
        status_icon = "✅" if key_info['status'] == 'working' else "❌"
        print(f"{status_icon} Key #{key_info['index']}: {key_info.get('key_masked', '****')}")
        print(f"   Status: {key_info['status'].upper()}")
        
        if key_info['error']:
            print(f"   Error: {key_info['error']}")
        print()
    
    # Final recommendations
    print("=" * 80)
    print("💡 RECOMMENDATIONS")
    print("=" * 80)
    
    if results['working_keys'] == results['total_keys']:
        print("✅ Excellent! All your API keys are working perfectly.")
        print("   Your system has maximum redundancy.")
    elif results['working_keys'] > 0:
        print(f"⚠️  {results['failed_keys']} key(s) are not working.")
        print("   Consider replacing failed keys with new ones.")
        print(f"   You still have {results['working_keys']} working key(s) for fallback.")
    else:
        print("❌ None of your API keys are working!")
        print("   Possible reasons:")
        print("   1. Keys are invalid or expired")
        print("   2. All keys have exceeded quota")
        print("   3. Network connectivity issues")
        print("   4. Google AI service issues")
        print()
        print("   Solutions:")
        print("   1. Check your keys at: https://makersuite.google.com/app/apikey")
        print("   2. Verify quota at: https://console.cloud.google.com/")
        print("   3. Try creating new keys")
    
    print()
    print("=" * 80)
    print("✨ Test complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()

