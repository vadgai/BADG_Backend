"""
Comprehensive Test Suite for Robust Diagnosis System
Tests patient data handling, null field management, and Gemini integration
"""

import asyncio
import json
import sys
from datetime import datetime
import httpx
import websockets

# Configuration
API_BASE_URL = "http://127.0.0.1:8000"
WS_BASE_URL = "ws://127.0.0.1:8000"

# Test scenarios
TEST_SCENARIOS = {
    "complete_profile": {
        "name": "Complete Patient Profile Test",
        "data": {
            "name": "John Doe",
            "age": 35,
            "gender": "male",
            "symptoms": "Persistent headache for 3 days, mild fever, fatigue",
            "weight": 75.5,
            "height": 175,
            "occupation": "Desk Job",
            "location": {
                "country": "India",
                "state": "Maharashtra",
                "city": "Mumbai"
            },
            "physical_activity": "moderate",
            "diet_type": "mixed"
        }
    },
    "minimal_required": {
        "name": "Minimal Required Fields Only",
        "data": {
            "name": "Jane Smith",
            "age": 28,
            "gender": "female",
            "symptoms": "Cough and chest pain since yesterday"
        }
    },
    "partial_optional": {
        "name": "Partial Optional Fields",
        "data": {
            "name": "Michael Chen",
            "age": 42,
            "gender": "male",
            "symptoms": "Abdominal pain, nausea, loss of appetite",
            "weight": 82,
            "height": 168,
            "location": {
                "country": "India",
                "state": "Karnataka"
            }
        }
    },
    "edge_case_elderly": {
        "name": "Elderly Patient with Chronic Conditions",
        "data": {
            "name": "Rajesh Kumar",
            "age": 72,
            "gender": "male",
            "symptoms": "Shortness of breath, chest tightness, dizziness",
            "weight": 68,
            "height": 165,
            "occupation": "Retired",
            "location": {
                "country": "India",
                "state": "Delhi",
                "city": "New Delhi"
            },
            "physical_activity": "low",
            "diet_type": "veg"
        }
    },
    "edge_case_young": {
        "name": "Young Adult with Active Lifestyle",
        "data": {
            "name": "Priya Sharma",
            "age": 19,
            "gender": "female",
            "symptoms": "Joint pain in knees, mild swelling",
            "weight": 55,
            "height": 160,
            "occupation": "Student",
            "physical_activity": "high",
            "diet_type": "vegan"
        }
    }
}

# Test Results Tracker
test_results = []

def log_test(scenario_name: str, step: str, status: str, details: str = ""):
    """Log test results"""
    result = {
        "timestamp": datetime.now().isoformat(),
        "scenario": scenario_name,
        "step": step,
        "status": status,
        "details": details
    }
    test_results.append(result)
    
    # Print to console
    status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"{status_icon} [{scenario_name}] {step}: {status} {details}")

async def test_server_health():
    """Test if server is running"""
    print("\n" + "="*80)
    print("TESTING SERVER HEALTH")
    print("="*80)
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{API_BASE_URL}/health")
            if response.status_code == 200:
                log_test("Server Health", "Health Check", "PASS", str(response.json()))
                return True
            else:
                log_test("Server Health", "Health Check", "FAIL", f"Status: {response.status_code}")
                return False
    except Exception as e:
        log_test("Server Health", "Health Check", "FAIL", str(e))
        return False

async def test_patient_submission(scenario_name: str, patient_data: dict):
    """Test patient data submission"""
    print("\n" + "-"*80)
    print(f"TESTING: {scenario_name}")
    print("-"*80)
    print(f"Patient Data: {json.dumps(patient_data, indent=2)}")
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/symptom",
                json=patient_data
            )
            
            if response.status_code == 200:
                data = response.json()
                session_id = data.get("session_id")
                
                if session_id:
                    log_test(scenario_name, "Patient Submission", "PASS", f"Session ID: {session_id}")
                    return session_id
                else:
                    log_test(scenario_name, "Patient Submission", "FAIL", "No session_id in response")
                    return None
            else:
                log_test(scenario_name, "Patient Submission", "FAIL", 
                        f"Status: {response.status_code}, Body: {response.text}")
                return None
                
    except Exception as e:
        log_test(scenario_name, "Patient Submission", "FAIL", str(e))
        return None

async def test_followup_questions(scenario_name: str, session_id: str, max_questions: int = 3):
    """Test follow-up questions via WebSocket"""
    print(f"\n Testing Follow-up Questions for {scenario_name}...")
    
    try:
        uri = f"{WS_BASE_URL}/followup/{session_id}"
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as websocket:
            
            # Wait for initial message
            initial_msg = await asyncio.wait_for(websocket.recv(), timeout=30.0)
            initial_data = json.loads(initial_msg)
            
            if initial_data.get("status") == "connected":
                log_test(scenario_name, "WebSocket Connection", "PASS", "Connected successfully")
            else:
                log_test(scenario_name, "WebSocket Connection", "WARN", f"Unexpected initial: {initial_data}")
            
            questions_received = 0
            
            # Process questions
            while questions_received < max_questions:
                try:
                    # Wait for question
                    msg = await asyncio.wait_for(websocket.recv(), timeout=45.0)
                    data = json.loads(msg)
                    
                    if data.get("question"):
                        questions_received += 1
                        question = data["question"]
                        options = data.get("options", [])
                        
                        log_test(scenario_name, f"Question #{questions_received}", "PASS", 
                                f"Q: {question[:60]}... Options: {len(options)}")
                        
                        # Validate question format
                        if len(options) < 2:
                            log_test(scenario_name, f"Question #{questions_received} Validation", "FAIL", 
                                    "Insufficient options")
                        else:
                            log_test(scenario_name, f"Question #{questions_received} Validation", "PASS", 
                                    f"{len(options)} options provided")
                        
                        # Send answer (select first option)
                        if options:
                            answer = options[0]["value"]
                            await websocket.send(answer)
                            log_test(scenario_name, f"Answer #{questions_received}", "PASS", 
                                    f"Sent: {answer[:40]}...")
                        
                    elif data.get("status") == "ready_for_diagnosis":
                        log_test(scenario_name, "Diagnosis Ready", "PASS", 
                                f"After {questions_received} questions")
                        break
                        
                    elif data.get("error"):
                        log_test(scenario_name, "Follow-up Error", "FAIL", data["error"])
                        break
                        
                    elif data.get("warning"):
                        log_test(scenario_name, "Follow-up Warning", "WARN", data["warning"])
                        
                except asyncio.TimeoutError:
                    log_test(scenario_name, f"Question #{questions_received + 1}", "FAIL", 
                            "Timeout waiting for response")
                    break
                    
            return questions_received
            
    except Exception as e:
        log_test(scenario_name, "Follow-up Questions", "FAIL", str(e))
        return 0

async def run_comprehensive_tests():
    """Run all test scenarios"""
    print("\n" + "="*80)
    print("VADG ROBUST DIAGNOSIS TEST SUITE")
    print("="*80)
    print(f"Started at: {datetime.now().isoformat()}")
    print(f"API URL: {API_BASE_URL}")
    print(f"WS URL: {WS_BASE_URL}")
    
    # Check server health first
    if not await test_server_health():
        print("\n❌ Server is not running. Please start the backend server first.")
        print("   Run: cd Backend && python app.py")
        return
    
    # Run each test scenario
    for scenario_key, scenario_info in TEST_SCENARIOS.items():
        scenario_name = scenario_info["name"]
        patient_data = scenario_info["data"]
        
        # Test patient submission
        session_id = await test_patient_submission(scenario_name, patient_data)
        
        if session_id:
            # Test follow-up questions
            await asyncio.sleep(1)  # Brief pause between tests
            questions_count = await test_followup_questions(scenario_name, session_id, max_questions=3)
            
            if questions_count >= 1:
                log_test(scenario_name, "Overall Test", "PASS", 
                        f"Completed successfully with {questions_count} questions")
            else:
                log_test(scenario_name, "Overall Test", "FAIL", 
                        "No follow-up questions received")
        else:
            log_test(scenario_name, "Overall Test", "FAIL", 
                    "Failed to create session")
        
        # Pause between scenarios
        await asyncio.sleep(2)
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    total_tests = len(test_results)
    passed = sum(1 for r in test_results if r["status"] == "PASS")
    failed = sum(1 for r in test_results if r["status"] == "FAIL")
    warnings = sum(1 for r in test_results if r["status"] == "WARN")
    
    print(f"Total Tests: {total_tests}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⚠️ Warnings: {warnings}")
    print(f"Success Rate: {(passed / total_tests * 100):.1f}%")
    
    # Print detailed failures
    if failed > 0:
        print("\n" + "="*80)
        print("FAILED TESTS")
        print("="*80)
        for result in test_results:
            if result["status"] == "FAIL":
                print(f"❌ [{result['scenario']}] {result['step']}: {result['details']}")
    
    # Save results to file
    output_file = "test_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total_tests,
                "passed": passed,
                "failed": failed,
                "warnings": warnings,
                "success_rate": f"{(passed / total_tests * 100):.1f}%"
            },
            "results": test_results
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: {output_file}")
    
    return failed == 0

if __name__ == "__main__":
    print("Starting VADG Robust Diagnosis Test Suite...")
    print("Make sure the backend server is running on http://127.0.0.1:8000")
    print()
    
    try:
        success = asyncio.run(run_comprehensive_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test suite crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

