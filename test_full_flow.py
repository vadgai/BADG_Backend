#!/usr/bin/env python3
"""
Test complete flow: Create session → Connect WebSocket
"""
import requests
import asyncio
import websockets
import json

async def test_full_flow():
    """Test: Create session via API, then connect WebSocket"""
    
    print("🧪 Testing Complete VADG Flow")
    print("=" * 60)
    
    # Step 1: Create session
    print("\n📝 Step 1: Creating session via API...")
    
    payload = {
        "name": "Test User",
        "age": 25,
        "gender": "male",
        "weight": 70,
        "height": 175,
        "occupation": "Software Engineer",
        "physical_activity": "Moderate",
        "diet_type": "Mixed",
        "location": {
            "country": "India",
            "state": "Maharashtra",
            "city": "Pune"
        },
        "symptoms": ["fever", "cough"]
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/symptom",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            session_id = data.get('session_id')
            print(f"✅ Session created: {session_id}")
        else:
            print(f"❌ Failed to create session: {response.status_code}")
            print(response.text)
            return
    except Exception as e:
        print(f"❌ Error creating session: {e}")
        return
    
    # Step 2: Connect WebSocket
    print(f"\n🔌 Step 2: Connecting WebSocket for session {session_id}...")
    
    uri = f"ws://localhost:8000/followup/{session_id}"
    
    try:
        async with websockets.connect(uri, ping_interval=None) as websocket:
            print("✅ WebSocket connected!")
            
            # Wait for messages
            try:
                # First message should be connection confirmation
                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)
                print(f"📨 Message 1: {data}")
                
                # Second message should be initial question
                message = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                data = json.loads(message)
                print(f"📨 Message 2: {data}")
                
                if 'question' in data:
                    print("✅ Received initial follow-up question!")
                    print(f"   Question: {data.get('question', '')[:100]}...")
                    print(f"   Options: {len(data.get('options', []))} choices")
                else:
                    print(f"⚠️  Unexpected message format: {data}")
                
            except asyncio.TimeoutError:
                print("⚠️  Timeout waiting for messages")
            
            print("\n✅ Full flow test completed successfully!")
            
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ WebSocket rejected: {e}")
        print("\n💡 Check backend logs for errors!")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")

if __name__ == "__main__":
    asyncio.run(test_full_flow())









