#!/usr/bin/env python3
"""
Test script to verify the simplified server is working
"""

import requests
import json

def test_server():
    base_url = "http://localhost:8000"
    
    try:
        # Test root endpoint
        print("Testing root endpoint...")
        response = requests.get(f"{base_url}/", timeout=5)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test symptom submission with enhanced data
        print("\nTesting symptom submission with enhanced data...")
        test_data = {
            "name": "Test Patient",
            "age": 35,
            "gender": "male",
            "symptoms": ["fever", "headache"],
            "weight": 75.5,
            "height": 175.0,
            "occupation": "Desk Job",
            "location": {
                "country": "India",
                "state": "Maharashtra",
                "city": "Pune"
            },
            "physical_activity": "moderate",
            "diet_type": "non_veg"
        }
        
        response = requests.post(f"{base_url}/symptom", json=test_data, timeout=10)
        print(f"Status Code: {response.status_code}")
        result = response.json()
        print(f"Response: {result}")
        
        if "session_id" in result:
            session_id = result["session_id"]
            print(f"\nSession created: {session_id}")
            
            # Test session retrieval
            print("Testing session retrieval...")
            response = requests.get(f"{base_url}/session/{session_id}", timeout=5)
            print(f"Status Code: {response.status_code}")
            print(f"Session Data: {response.json()}")
            
            return True
        else:
            print("❌ No session_id in response")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Is it running?")
        return False
    except Exception as e:
        print(f"❌ Error testing server: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing VADG Simplified Server")
    print("=" * 40)
    
    success = test_server()
    
    if success:
        print("\n✅ Server is working correctly!")
        print("🎉 Enhanced patient form integration is ready!")
    else:
        print("\n❌ Server test failed")
        print("💡 Make sure the server is running: python app_simple.py")

