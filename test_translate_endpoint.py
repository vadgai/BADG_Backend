"""
Quick test script for translation endpoint
Run this after starting the backend to verify translation works
"""

import requests
import json

# Test configuration
BASE_URL = "http://localhost:8000"
TRANSLATE_URL = f"{BASE_URL}/api/translate"

def test_single_translation():
    """Test single text translation"""
    print("=" * 60)
    print("Testing Single Text Translation (Hindi)")
    print("=" * 60)
    
    payload = {
        "text": "Do you have fever?",
        "targetLang": "hi"
    }
    
    try:
        response = requests.post(TRANSLATE_URL, json=payload, timeout=15)
        print(f"Status Code: {response.status_code}")
        
        if response.ok:
            data = response.json()
            print(f"✓ Success!")
            print(f"Original: {payload['text']}")
            print(f"Translated: {data.get('translated', 'N/A')}")
        else:
            print(f"✗ Failed: {response.text}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print()

def test_batch_translation():
    """Test batch translation"""
    print("=" * 60)
    print("Testing Batch Translation (Tamil)")
    print("=" * 60)
    
    payload = {
        "items": [
            "Do you have cough?",
            "When did symptoms start?",
            "Do you have any allergies?"
        ],
        "targetLang": "ta"
    }
    
    try:
        response = requests.post(TRANSLATE_URL, json=payload, timeout=15)
        print(f"Status Code: {response.status_code}")
        
        if response.ok:
            data = response.json()
            print(f"✓ Success!")
            translations = data.get('translated', [])
            for i, (orig, trans) in enumerate(zip(payload['items'], translations)):
                print(f"{i+1}. Original: {orig}")
                print(f"   Translated: {trans}")
        else:
            print(f"✗ Failed: {response.text}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print()

def test_health_check():
    """Test translation service health"""
    print("=" * 60)
    print("Testing Translation Service Health")
    print("=" * 60)
    
    try:
        response = requests.get(f"{TRANSLATE_URL}/health", timeout=5)
        print(f"Status Code: {response.status_code}")
        
        if response.ok:
            data = response.json()
            print(f"✓ Service is healthy!")
            print(f"Cache Size: {data.get('cache_size', 0)}")
            print(f"Supported Languages: {', '.join(data.get('supported_languages', []))}")
        else:
            print(f"✗ Failed: {response.text}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print()

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("VADG Translation Endpoint Test")
    print("=" * 60)
    print()
    
    # Test health first
    test_health_check()
    
    # Test single translation
    test_single_translation()
    
    # Test batch translation
    test_batch_translation()
    
    print("=" * 60)
    print("Tests Complete!")
    print("=" * 60)


