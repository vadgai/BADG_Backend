#!/usr/bin/env python3
"""
Quick test to verify WebSocket endpoint is working
"""
import asyncio
import websockets
import json
import sys

async def test_websocket():
    """Test WebSocket connection to localhost"""
    
    # Use a dummy session ID
    session_id = "test-session-123"
    uri = f"ws://localhost:8000/followup/{session_id}"
    
    print(f"🔌 Testing WebSocket connection to: {uri}")
    print()
    
    try:
        async with websockets.connect(uri, ping_interval=None) as websocket:
            print("✅ WebSocket connected!")
            
            # Wait for initial message
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)
                print(f"📨 Received: {data}")
            except asyncio.TimeoutError:
                print("⚠️  No message received within 10 seconds")
            
            # Send a test message
            test_msg = "A"
            print(f"\n📤 Sending test message: {test_msg}")
            await websocket.send(test_msg)
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(response)
                print(f"📨 Response: {data}")
            except asyncio.TimeoutError:
                print("⚠️  No response received within 10 seconds")
            
            print("\n✅ WebSocket test completed successfully!")
            
    except websockets.exceptions.ConnectionRefused:
        print("❌ Connection refused - Backend not running on port 8000")
        sys.exit(1)
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ Invalid status code: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_websocket())









