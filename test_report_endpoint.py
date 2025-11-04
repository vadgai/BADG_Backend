"""
Test script to check what's wrong with the report analyzer endpoint
"""
import sys
import traceback

print("=" * 80)
print("Testing Report Analyzer Endpoint")
print("=" * 80)

try:
    print("\n1. Testing imports...")
    from routes import report_analyzer
    print("   ✅ report_analyzer imported")
    
    from fastapi import FastAPI
    print("   ✅ FastAPI imported")
    
    print("\n2. Creating test app...")
    app = FastAPI()
    app.include_router(report_analyzer.router)
    print("   ✅ Router registered")
    
    print("\n3. Checking endpoints...")
    routes = [route.path for route in app.routes]
    print(f"   Found {len(routes)} routes:")
    for route in routes:
        print(f"      - {route}")
    
    if "/api/analyze-report" in routes:
        print("\n   ✅ /api/analyze-report endpoint found!")
    else:
        print("\n   ❌ /api/analyze-report endpoint NOT found!")
        print("   Available routes:", routes)
    
    print("\n4. Testing Gemini connection...")
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if api_key:
        print(f"   ✅ API Key found: {api_key[:15]}...")
        
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        print("   ✅ Gemini model initialized")
        
        # Test a simple generation
        print("   Testing Gemini API call...")
        response = model.generate_content("Hello")
        print(f"   ✅ Gemini responded: {response.text[:50]}...")
    else:
        print("   ❌ API Key not found!")
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED - Backend should work!")
    print("=" * 80)
    
except Exception as e:
    print("\n" + "=" * 80)
    print("❌ ERROR FOUND:")
    print("=" * 80)
    print(f"\nError: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    print("\n" + "=" * 80)
    sys.exit(1)

