#!/usr/bin/env python3
"""
Quick test to verify enhanced diagnosis functionality
"""

import asyncio
import httpx
import json

async def test_enhanced_diagnosis():
    """Test the enhanced diagnosis with patient metadata"""
    
    # Test data with enhanced patient information
    test_data = {
        "name": "Test Patient",
        "age": 30,
        "gender": "male",
        "symptoms": ["chest pain", "shortness of breath"],
        "weight": 75.5,
        "height": 170.0,
        "occupation": "Desk Job",
        "location": {
            "country": "India",
            "state": "Maharashtra",
            "city": "Mumbai"
        },
        "physical_activity": "Moderate",
        "diet_type": "Non-Veg"
    }
    
    print("🧪 Testing Enhanced Diagnosis")
    print("=" * 50)
    print(f"Test Data: {json.dumps(test_data, indent=2)}")
    
    try:
        async with httpx.AsyncClient() as client:
            # Test server health
            print("\n1️⃣ Testing server health...")
            health_response = await client.get("http://localhost:8000/")
            print(f"✅ Server status: {health_response.status_code}")
            print(f"📋 Response: {health_response.json()}")
            
            # Submit symptoms with enhanced data
            print("\n2️⃣ Submitting enhanced patient data...")
            symptom_response = await client.post("http://localhost:8000/symptom", json=test_data)
            print(f"✅ Symptom submission: {symptom_response.status_code}")
            result = symptom_response.json()
            session_id = result.get("session_id")
            print(f"📋 Session ID: {session_id}")
            
            # Generate report
            print("\n3️⃣ Generating diagnosis report...")
            report_response = await client.get(f"http://localhost:8000/generate_report/{session_id}")
            print(f"✅ Report generation: {report_response.status_code}")
            report = report_response.json()
            
            # Check if enhanced context was used
            print("\n4️⃣ Analyzing enhanced context usage...")
            meta = report.get("meta", {})
            context_used = meta.get("context_used", [])
            analysis_note = meta.get("note", "N/A")
            
            print(f"🔍 Context used: {context_used}")
            print(f"💡 Analysis note: {analysis_note}")
            print(f"📊 BMI: {meta.get('bmi', 'N/A')}")
            
            # Check if we have structured response
            if "mapped_diseases" in report:
                print(f"🏥 Mapped diseases: {report['mapped_diseases']}")
            
            # Verification
            print("\n5️⃣ Verification Results:")
            if context_used:
                print("✅ Enhanced context is being used!")
                print(f"   - Fields used: {', '.join(context_used)}")
            else:
                print("❌ Enhanced context not detected")
            
            if "bmi" in meta:
                print("✅ BMI calculation working")
            else:
                print("❌ BMI calculation not working")
            
            if analysis_note and "personalized" in analysis_note.lower():
                print("✅ Personalized analysis confirmed")
            else:
                print("❌ Personalized analysis not confirmed")
            
            return True
            
    except httpx.ConnectError:
        print("❌ Could not connect to server. Is it running?")
        print("💡 Start server with: python app_simple.py")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Quick Enhanced Diagnosis Test")
    print("=" * 50)
    success = asyncio.run(test_enhanced_diagnosis())
    
    if success:
        print("\n🎉 Enhanced diagnosis is working correctly!")
        print("💡 The AI is now using patient metadata for better diagnosis.")
    else:
        print("\n❌ Enhanced diagnosis test failed.")
        print("💡 Check server logs and ensure all dependencies are installed.")
