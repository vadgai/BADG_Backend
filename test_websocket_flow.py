"""
🔍 WebSocket Flow Debug Script
Tests the complete patient data → follow-up questions flow
"""

import asyncio
import json
import httpx
import websockets
from datetime import datetime

# Configuration
API_BASE = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"

def log(emoji, message):
    """Pretty print logs"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {emoji} {message}")

async def test_complete_flow():
    """Test complete patient data → WebSocket → follow-up questions flow"""
    
    print("\n" + "="*80)
    print("🧪 TESTING COMPLETE WEBSOCKET FLOW")
    print("="*80 + "\n")
    
    # Step 1: Check server health
    log("🏥", "Step 1: Checking server health...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{API_BASE}/health")
            if response.status_code == 200:
                log("✅", f"Server is healthy: {response.json()}")
            else:
                log("❌", f"Server health check failed: {response.status_code}")
                return
    except Exception as e:
        log("❌", f"Cannot connect to server: {e}")
        log("💡", "Make sure backend is running: uvicorn app:app --host 0.0.0.0 --port 8000")
        return
    
    # Step 2: Submit patient data
    log("📝", "Step 2: Submitting patient data...")
    patient_data = {
        "name": "Debug Test User",
        "age": 35,
        "gender": "male",
        "symptoms": "fever and headache for 2 days",
        "weight": 75,
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
    
    log("📤", f"Payload: {json.dumps(patient_data, indent=2)}")
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{API_BASE}/symptom",
                json=patient_data
            )
            
            if response.status_code == 200:
                data = response.json()
                session_id = data.get("session_id")
                log("✅", f"Patient data submitted successfully")
                log("🆔", f"Session ID: {session_id}")
            else:
                log("❌", f"Failed to submit patient data: {response.status_code}")
                log("📄", f"Response: {response.text}")
                return
    except Exception as e:
        log("❌", f"Error submitting patient data: {e}")
        return
    
    # Step 3: Connect to WebSocket
    log("🔌", "Step 3: Connecting to WebSocket for follow-up questions...")
    ws_url = f"{WS_BASE}/followup/{session_id}"
    log("🌐", f"WebSocket URL: {ws_url}")
    
    try:
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as websocket:
            log("✅", "WebSocket connected successfully!")
            
            # Wait for initial message
            log("⏳", "Waiting for initial message...")
            initial_msg = await asyncio.wait_for(websocket.recv(), timeout=30.0)
            initial_data = json.loads(initial_msg)
            
            if initial_data.get("status") == "connected":
                log("✅", "Received 'connected' status from server")
            else:
                log("⚠️", f"Unexpected initial message: {initial_data}")
            
            # Wait for first question
            log("⏳", "Waiting for first follow-up question...")
            question_msg = await asyncio.wait_for(websocket.recv(), timeout=45.0)
            question_data = json.loads(question_msg)
            
            if question_data.get("question"):
                question = question_data["question"]
                options = question_data.get("options", [])
                
                log("✅", "Received first follow-up question!")
                log("❓", f"Question: {question}")
                log("📋", f"Options ({len(options)}):")
                for opt in options:
                    print(f"      {opt['key']}: {opt['value']}")
                
                # Validate question format
                if len(options) >= 2:
                    log("✅", "Question has valid options")
                else:
                    log("⚠️", f"Question has insufficient options: {len(options)}")
                
                # Send answer (select first option)
                if options:
                    answer = options[0]["value"]
                    log("📤", f"Sending answer: {answer}")
                    await websocket.send(answer)
                    log("✅", "Answer sent successfully")
                    
                    # Wait for next question or completion
                    log("⏳", "Waiting for server response...")
                    try:
                        next_msg = await asyncio.wait_for(websocket.recv(), timeout=45.0)
                        next_data = json.loads(next_msg)
                        
                        if next_data.get("question"):
                            log("✅", f"Received next question: {next_data['question'][:60]}...")
                        elif next_data.get("status") == "ready_for_diagnosis":
                            log("✅", "Diagnosis ready!")
                        else:
                            log("ℹ️", f"Received: {next_data}")
                            
                    except asyncio.TimeoutError:
                        log("⏰", "Timeout waiting for response (this might be OK)")
                        
            elif question_data.get("error"):
                log("❌", f"Server error: {question_data['error']}")
            elif question_data.get("warning"):
                log("⚠️", f"Server warning: {question_data['warning']}")
            else:
                log("❌", f"Unexpected message format: {question_data}")
                
    except asyncio.TimeoutError:
        log("❌", "Timeout waiting for messages from server")
        log("💡", "Check backend logs for errors")
    except websockets.exceptions.WebSocketException as e:
        log("❌", f"WebSocket error: {e}")
        log("💡", "Common causes:")
        log("   ", "1. Backend not running")
        log("   ", "2. Wrong WebSocket URL")
        log("   ", "3. CORS issues")
        log("   ", "4. Session ID not found in backend")
    except Exception as e:
        log("❌", f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    log("✅", "Test completed - check logs above for any issues")
    print()

if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════════════════════╗
    ║                  VADG WEBSOCKET FLOW DEBUG SCRIPT                          ║
    ║                                                                            ║
    ║  This script tests:                                                        ║
    ║  1. Server health check                                                    ║
    ║  2. Patient data submission (with enhanced fields)                         ║
    ║  3. WebSocket connection                                                   ║
    ║  4. Follow-up question generation                                          ║
    ║  5. Answer submission and response handling                                ║
    ║                                                                            ║
    ║  Prerequisites:                                                            ║
    ║  - Backend running on http://127.0.0.1:8000                                ║
    ║  - GEMINI_API_KEY set in .env file                                         ║
    ║                                                                            ║
    ╚════════════════════════════════════════════════════════════════════════════╝
    """)
    
    try:
        asyncio.run(test_complete_flow())
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test crashed: {e}")
        import traceback
        traceback.print_exc()

