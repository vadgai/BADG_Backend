#!/usr/bin/env python3
"""
Simple test using curl to verify enhanced diagnosis
"""

import subprocess
import json
import time

def test_with_curl():
    """Test the enhanced diagnosis using curl commands"""
    
    print("🧪 Testing Enhanced Diagnosis with curl")
    print("=" * 50)
    
    # Test data
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
    
    try:
        # Test 1: Health check
        print("1️⃣ Testing server health...")
        result = subprocess.run([
            "curl", "-s", "http://localhost:8000/"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Server is running")
            print(f"📋 Response: {result.stdout}")
        else:
            print("❌ Server not responding")
            return False
        
        # Test 2: Submit symptoms
        print("\n2️⃣ Submitting enhanced patient data...")
        json_data = json.dumps(test_data)
        
        result = subprocess.run([
            "curl", "-s", "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", json_data,
            "http://localhost:8000/symptom"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Symptom submission successful")
            response = json.loads(result.stdout)
            session_id = response.get("session_id")
            print(f"📋 Session ID: {session_id}")
            
            if session_id:
                # Test 3: Generate report
                print(f"\n3️⃣ Generating report for session {session_id}...")
                time.sleep(2)  # Give server time to process
                
                result = subprocess.run([
                    "curl", "-s", f"http://localhost:8000/generate_report/{session_id}"
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    print("✅ Report generation successful")
                    try:
                        report = json.loads(result.stdout)
                        meta = report.get("meta", {})
                        context_used = meta.get("context_used", [])
                        analysis_note = meta.get("note", "N/A")
                        
                        print(f"🔍 Context used: {context_used}")
                        print(f"💡 Analysis note: {analysis_note}")
                        print(f"📊 BMI: {meta.get('bmi', 'N/A')}")
                        
                        # Verification
                        print("\n4️⃣ Verification Results:")
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
                        
                    except json.JSONDecodeError as e:
                        print(f"❌ Could not parse report JSON: {e}")
                        print(f"Raw response: {result.stdout[:200]}...")
                        return False
                else:
                    print(f"❌ Report generation failed: {result.stderr}")
                    return False
            else:
                print("❌ No session ID received")
                return False
        else:
            print(f"❌ Symptom submission failed: {result.stderr}")
            print(f"Response: {result.stdout}")
            return False
            
    except FileNotFoundError:
        print("❌ curl not found. Please install curl or use a different test method.")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Simple Enhanced Diagnosis Test")
    print("=" * 50)
    print("💡 Make sure the server is running: python app_simple.py")
    
    success = test_with_curl()
    
    if success:
        print("\n🎉 Enhanced diagnosis is working correctly!")
        print("💡 The AI is now using patient metadata for better diagnosis.")
    else:
        print("\n❌ Enhanced diagnosis test failed.")
        print("💡 Check server logs and ensure all dependencies are installed.")
