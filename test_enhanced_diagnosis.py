#!/usr/bin/env python3
"""
Test script to verify enhanced diagnosis with different patient profiles
This tests that the LLM uses patient metadata for more accurate reasoning
"""

import asyncio
import httpx
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

async def test_patient_profile(profile_name, patient_data):
    """Test a specific patient profile and return the diagnosis"""
    print(f"\n{'='*60}")
    print(f"🧪 TESTING: {profile_name}")
    print(f"{'='*60}")
    print(f"Patient Data: {json.dumps(patient_data, indent=2)}")
    
    try:
        async with httpx.AsyncClient() as client:
            # Submit symptoms
            response = await client.post(f"{BASE_URL}/symptom", json=patient_data)
            response.raise_for_status()
            result = response.json()
            session_id = result.get("session_id")
            
            print(f"✅ Session created: {session_id}")
            
            # Generate report
            report_response = await client.get(f"{BASE_URL}/generate_report/{session_id}")
            report_response.raise_for_status()
            report = report_response.json()
            
            print(f"📊 Report generated successfully")
            print(f"📋 Context used: {report.get('meta', {}).get('context_used', [])}")
            print(f"💡 Analysis note: {report.get('meta', {}).get('note', 'N/A')}")
            
            if 'mapped_diseases' in report:
                print(f"🔍 Mapped diseases: {report['mapped_diseases']}")
            
            return {
                "profile": profile_name,
                "session_id": session_id,
                "context_used": report.get('meta', {}).get('context_used', []),
                "analysis_note": report.get('meta', {}).get('note', 'N/A'),
                "mapped_diseases": report.get('mapped_diseases', {}),
                "success": True
            }
            
    except Exception as e:
        print(f"❌ Error testing {profile_name}: {e}")
        return {
            "profile": profile_name,
            "error": str(e),
            "success": False
        }

async def main():
    """Run comprehensive tests with different patient profiles"""
    print("🚀 VADG Enhanced Diagnosis Testing")
    print("=" * 60)
    print("Testing AI reasoning with different patient profiles...")
    
    # Test profiles designed to show different AI reasoning
    test_profiles = [
        {
            "name": "🏃‍♂️ Active Young Person",
            "data": {
                "name": "Alex Johnson",
                "age": 25,
                "gender": "male",
                "symptoms": ["chest pain", "shortness of breath"],
                "weight": 70,
                "height": 175,
                "occupation": "Physical Labor",
                "location": {
                    "country": "India",
                    "state": "Karnataka",
                    "city": "Bangalore"
                },
                "physical_activity": "High",
                "diet_type": "Non-Veg"
            }
        },
        {
            "name": "💻 Sedentary Office Worker",
            "data": {
                "name": "Sarah Chen",
                "age": 35,
                "gender": "female",
                "symptoms": ["chest pain", "shortness of breath"],
                "weight": 85,
                "height": 160,
                "occupation": "Desk Job",
                "location": {
                    "country": "India",
                    "state": "Maharashtra",
                    "city": "Mumbai"
                },
                "physical_activity": "Low",
                "diet_type": "Veg"
            }
        },
        {
            "name": "👴 Elderly with Health Issues",
            "data": {
                "name": "Robert Kumar",
                "age": 65,
                "gender": "male",
                "symptoms": ["chest pain", "shortness of breath"],
                "weight": 95,
                "height": 170,
                "occupation": "Retired",
                "location": {
                    "country": "India",
                    "state": "Tamil Nadu",
                    "city": "Chennai"
                },
                "physical_activity": "Low",
                "diet_type": "Non-Veg"
            }
        },
        {
            "name": "🏃‍♀️ Fitness Enthusiast",
            "data": {
                "name": "Priya Sharma",
                "age": 28,
                "gender": "female",
                "symptoms": ["chest pain", "shortness of breath"],
                "weight": 55,
                "height": 165,
                "occupation": "Physical Labor",
                "location": {
                    "country": "India",
                    "state": "Delhi",
                    "city": "New Delhi"
                },
                "physical_activity": "High",
                "diet_type": "Veg"
            }
        },
        {
            "name": "📊 Basic Profile (No Metadata)",
            "data": {
                "name": "John Doe",
                "age": 30,
                "gender": "male",
                "symptoms": ["chest pain", "shortness of breath"]
            }
        }
    ]
    
    results = []
    
    for profile in test_profiles:
        result = await test_patient_profile(profile["name"], profile["data"])
        results.append(result)
        await asyncio.sleep(1)  # Brief pause between tests
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}")
    
    successful_tests = [r for r in results if r.get("success")]
    failed_tests = [r for r in results if not r.get("success")]
    
    print(f"✅ Successful tests: {len(successful_tests)}")
    print(f"❌ Failed tests: {len(failed_tests)}")
    
    if successful_tests:
        print(f"\n🔍 CONTEXT USAGE ANALYSIS:")
        for result in successful_tests:
            context_used = result.get("context_used", [])
            print(f"  • {result['profile']}: {context_used}")
    
    if failed_tests:
        print(f"\n❌ FAILED TESTS:")
        for result in failed_tests:
            print(f"  • {result['profile']}: {result.get('error', 'Unknown error')}")
    
    print(f"\n💡 VERIFICATION CHECKLIST:")
    print(f"  ✅ Different profiles should show different context usage")
    print(f"  ✅ BMI should be calculated for profiles with weight/height")
    print(f"  ✅ Occupation should influence diagnosis reasoning")
    print(f"  ✅ Activity level should be considered")
    print(f"  ✅ Location should be included in context")
    print(f"  ✅ Basic profile should work without metadata")
    
    return results

if __name__ == "__main__":
    print("🧪 Starting Enhanced Diagnosis Tests...")
    print("💡 Make sure the server is running: python app_simple.py")
    print("⏳ This will test 5 different patient profiles...")
    
    try:
        results = asyncio.run(main())
        print(f"\n🎉 Testing completed! Check the console output above for detailed results.")
    except KeyboardInterrupt:
        print(f"\n⏹️  Testing interrupted by user")
    except Exception as e:
        print(f"\n💥 Testing failed with error: {e}")
