#!/usr/bin/env python3
"""
VADG Complete Flow Test
Tests the entire diagnosis flow: Form → Report → WebSocket → PDF
"""
import requests
import asyncio
import websockets
import json
import sys
import time
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

# ANSI Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_step(step, message):
    """Print test step with formatting"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}STEP {step}: {message}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

def print_success(message):
    """Print success message"""
    print(f"{GREEN}✅ {message}{RESET}")

def print_error(message):
    """Print error message"""
    print(f"{RED}❌ {message}{RESET}")

def print_warning(message):
    """Print warning message"""
    print(f"{YELLOW}⚠️  {message}{RESET}")

def print_info(message):
    """Print info message"""
    print(f"   {message}")

# Test data
TEST_PATIENT_DATA = {
    "name": "Ravi Kumar",
    "age": 32,
    "gender": "male",
    "weight": 72.0,
    "height": 174.0,
    "occupation": "Software Engineer",
    "physical_activity": "Moderate",
    "diet_type": "Vegetarian",
    "location": {
        "country": "India",
        "state": "Maharashtra",
        "city": "Pune"
    },
    "symptoms": ["fever", "fatigue", "cough"],
    "notes": "No major medical conditions"
}

def test_backend_health():
    """Test 0: Verify backend is running"""
    print_step(0, "Backend Health Check")
    
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success("Backend is running")
            print_info(f"API Version: {data.get('version', 'Unknown')}")
            print_info(f"Status: {data.get('status', 'Unknown')}")
            return True
        else:
            print_error(f"Backend returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to backend at http://localhost:8000")
        print_info("Make sure backend is running:")
        print_info("  cd Backend")
        print_info("  python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload")
        return False
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False

def test_form_submission():
    """Test 1: Submit patient form"""
    print_step(1, "Patient Form Submission")
    
    try:
        print_info("Submitting patient data...")
        response = requests.post(
            f"{BASE_URL}/symptom",
            json=TEST_PATIENT_DATA,
            timeout=10
        )
        
        print_info(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            session_id = data.get('session_id')
            
            if session_id:
                print_success(f"Form submitted successfully")
                print_info(f"Session ID: {session_id}")
                print_info(f"Status: {data.get('status', 'Unknown')}")
                return session_id
            else:
                print_error("No session_id in response")
                print_info(f"Response: {json.dumps(data, indent=2)}")
                return None
        else:
            print_error(f"Form submission failed with status {response.status_code}")
            print_info(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Form submission error: {e}")
        return None

def test_session_retrieval(session_id):
    """Test 2: Verify session data"""
    print_step(2, "Session Data Verification")
    
    try:
        print_info(f"Retrieving session {session_id}...")
        response = requests.get(
            f"{BASE_URL}/session/{session_id}",
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Session data retrieved")
            print_info(f"Patient: {data.get('name', 'Unknown')}")
            print_info(f"Age: {data.get('age', 'Unknown')}")
            print_info(f"Gender: {data.get('gender', 'Unknown')}")
            print_info(f"Symptoms: {len(data.get('symptoms', []))} symptoms")
            return True
        else:
            print_error(f"Session retrieval failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Session retrieval error: {e}")
        return False

async def test_websocket_connection(session_id):
    """Test 3: WebSocket connection and communication"""
    print_step(3, "WebSocket Follow-up Questions")
    
    ws_url = f"{WS_URL}/followup/{session_id}"
    print_info(f"Connecting to: {ws_url}")
    
    try:
        async with websockets.connect(ws_url, ping_interval=None) as websocket:
            print_success("WebSocket connected successfully!")
            
            # Wait for initial question
            print_info("Waiting for initial question...")
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                data = json.loads(message)
                
                if "status" in data and data["status"] == "connected":
                    print_success("Received connection confirmation")
                    
                    # Wait for actual question
                    message = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                    data = json.loads(message)
                
                if "question" in data:
                    print_success("Received follow-up question")
                    print_info(f"Question: {data['question'][:100]}...")
                    
                    if "options" in data and data["options"]:
                        print_info(f"Options: {len(data['options'])} choices")
                        for opt in data["options"][:3]:
                            print_info(f"  - {opt.get('key')}: {opt.get('value')}")
                    
                    # Send answer
                    print_info("Sending answer: A")
                    await websocket.send("A")
                    
                    # Wait for next question or completion
                    print_info("Waiting for response...")
                    message = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                    data = json.loads(message)
                    
                    if "question" in data:
                        print_success("Received next question")
                        print_info(f"Question: {data['question'][:100]}...")
                    elif "status" in data and "ready" in data.get("status", "").lower():
                        print_success("Follow-up complete, ready for diagnosis")
                    else:
                        print_warning(f"Unexpected response: {data}")
                    
                    return True
                    
                elif "error" in data:
                    print_error(f"WebSocket error: {data['error']}")
                    return False
                else:
                    print_warning(f"Unexpected message format: {data}")
                    return False
                    
            except asyncio.TimeoutError:
                print_error("Timeout waiting for WebSocket message")
                print_warning("Backend may be processing slowly or having issues")
                return False
                
    except websockets.exceptions.InvalidStatusCode as e:
        print_error(f"WebSocket connection rejected: {e}")
        print_info("Check backend WebSocket endpoint configuration")
        return False
    except Exception as e:
        print_error(f"WebSocket error: {type(e).__name__}: {e}")
        return False

def test_report_generation(session_id):
    """Test 4: Generate diagnosis report"""
    print_step(4, "Diagnosis Report Generation")
    
    try:
        print_info(f"Generating report for session {session_id}...")
        response = requests.get(
            f"{BASE_URL}/generate_report/{session_id}",
            timeout=30
        )
        
        print_info(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if "report" in data:
                report = data["report"]
                print_success("Report generated successfully")
                
                # Check report structure
                if isinstance(report, str):
                    print_info(f"Report length: {len(report)} characters")
                    print_info(f"Preview: {report[:200]}...")
                elif isinstance(report, dict):
                    print_info("Report structure:")
                    for key in list(report.keys())[:5]:
                        print_info(f"  - {key}")
                
                # Check patient details
                if "patient_details" in data:
                    details = data["patient_details"]
                    print_success("Patient details included")
                    print_info(f"  Name: {details.get('name')}")
                    print_info(f"  Age: {details.get('age')}")
                    print_info(f"  Gender: {details.get('gender')}")
                
                return True
            else:
                print_error("No report in response")
                print_info(f"Response keys: {list(data.keys())}")
                return False
        else:
            print_error(f"Report generation failed with status {response.status_code}")
            print_info(f"Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print_error(f"Report generation error: {e}")
        return False

def main():
    """Run complete test suite"""
    print(f"\n{BLUE}{'='*60}")
    print("🧠 VADG COMPLETE FLOW TEST")
    print(f"{'='*60}{RESET}")
    print(f"\n📧 Team: vadg.office@gmail.com")
    print(f"🌐 Site: vadg.in")
    print(f"🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    results = {
        "backend_health": False,
        "form_submission": False,
        "session_retrieval": False,
        "websocket": False,
        "report_generation": False
    }
    
    # Test 0: Backend Health
    if not test_backend_health():
        print_error("\n❌ Backend is not running. Cannot proceed with tests.")
        sys.exit(1)
    results["backend_health"] = True
    
    # Test 1: Form Submission
    session_id = test_form_submission()
    if not session_id:
        print_error("\n❌ Form submission failed. Cannot proceed with tests.")
        sys.exit(1)
    results["form_submission"] = True
    
    # Test 2: Session Retrieval
    if test_session_retrieval(session_id):
        results["session_retrieval"] = True
    
    # Test 3: WebSocket
    print_info("\nStarting WebSocket test (this may take a few seconds)...")
    try:
        ws_result = asyncio.run(test_websocket_connection(session_id))
        results["websocket"] = ws_result
    except Exception as e:
        print_error(f"WebSocket test failed: {e}")
    
    # Test 4: Report Generation
    if test_report_generation(session_id):
        results["report_generation"] = True
    
    # Summary
    print(f"\n{BLUE}{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}{RESET}\n")
    
    total = len(results)
    passed = sum(results.values())
    
    for test_name, result in results.items():
        status = f"{GREEN}✅ PASS{RESET}" if result else f"{RED}❌ FAIL{RESET}"
        print(f"  {test_name.replace('_', ' ').title():<30} {status}")
    
    print(f"\n{BLUE}{'='*60}{RESET}")
    percentage = (passed / total) * 100
    
    if passed == total:
        print(f"{GREEN}🎉 ALL TESTS PASSED! ({passed}/{total} - {percentage:.0f}%){RESET}")
    elif passed >= total * 0.7:
        print(f"{YELLOW}⚠️  PARTIAL SUCCESS ({passed}/{total} - {percentage:.0f}%){RESET}")
    else:
        print(f"{RED}❌ TESTS FAILED ({passed}/{total} - {percentage:.0f}%){RESET}")
    
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}⚠️  Tests interrupted by user{RESET}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n{RED}❌ Unexpected error: {e}{RESET}\n")
        sys.exit(1)

