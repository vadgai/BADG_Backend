"""
Test Hindi PDF generation end-to-end
"""
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def test_full_flow():
    print("🧪 Testing Hindi PDF Generation End-to-End\n")
    
    # 1. Create session with patient data
    print("1️⃣ Creating patient session...")
    patient_data = {
        "name": "परीक्षण रोगी",
        "age": 30,
        "gender": "male",
        "symptoms": ["सिरदर्द", "बुखार", "थकान"],
        "weight": 70,
        "height": 170,
        "occupation": "Desk Job",
        "location": {
            "city": "Delhi",
            "state": "Delhi"
        },
        "physical_activity": "moderate",
        "diet_type": "vegetarian",
        "language": "hi"
    }
    
    response = requests.post(f"{BASE_URL}/patient", json=patient_data)
    if response.status_code != 200:
        print(f"❌ Failed to create session: {response.text}")
        return False
    
    session_id = response.json().get("session_id")
    print(f"✅ Session created: {session_id}\n")
    
    # 2. Simulate follow-up (skip for testing)
    print("2️⃣ Skipping follow-up questions (testing PDF only)\n")
    
    # 3. Generate report
    print("3️⃣ Generating Hindi report...")
    response = requests.get(f"{BASE_URL}/generate_report/{session_id}?lang=hi")
    if response.status_code != 200:
        print(f"❌ Failed to generate report: {response.text}")
        return False
    
    report_data = response.json()
    print(f"✅ Report generated")
    print(f"   Patient: {report_data.get('patient_details', {}).get('name')}")
    print(f"   Language: {report_data.get('language')}\n")
    
    # 4. Download PDF
    print("4️⃣ Downloading Hindi PDF...")
    response = requests.get(f"{BASE_URL}/download_pdf/{session_id}?lang=hi")
    if response.status_code != 200:
        print(f"❌ Failed to download PDF: {response.text}")
        return False
    
    pdf_bytes = response.content
    print(f"✅ PDF downloaded: {len(pdf_bytes)} bytes")
    
    # Save PDF
    filename = f"test_hindi_{session_id[:8]}.pdf"
    with open(filename, 'wb') as f:
        f.write(pdf_bytes)
    
    print(f"✅ Saved to: {filename}\n")
    
    # 5. Verify PDF
    print("5️⃣ Verifying PDF...")
    if len(pdf_bytes) > 5000:
        print(f"✅ PDF size OK: {len(pdf_bytes)} bytes")
    else:
        print(f"⚠️ PDF seems small: {len(pdf_bytes)} bytes")
    
    # Check if it's a valid PDF
    if pdf_bytes[:4] == b'%PDF':
        print("✅ Valid PDF header")
    else:
        print("❌ Invalid PDF header")
        return False
    
    print(f"\n🎉 SUCCESS! Hindi PDF generated successfully!")
    print(f"📄 Open {filename} to verify Hindi text is readable")
    
    return True

if __name__ == '__main__':
    try:
        success = test_full_flow()
        if success:
            print("\n✅ All tests passed!")
        else:
            print("\n❌ Tests failed!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()













