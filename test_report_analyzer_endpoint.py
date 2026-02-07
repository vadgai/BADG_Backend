"""
Test script to verify the report-analyzer-submissions endpoint exists and works
Run this BEFORE deploying to confirm the endpoint is properly configured
"""

import sys
import requests
import json

# Test configuration
BASE_URL = "http://localhost:8000"
ENDPOINT = "/api/admin/report-analyzer-submissions"

# Test credentials (from admin.py)
ADMIN_EMAIL = "m87.krishna@gmail.com"
ADMIN_PASSWORD = "Vadg@44"

def test_endpoint():
    """Test if the report-analyzer-submissions endpoint exists and works"""
    
    print("=" * 60)
    print("Testing Report Analyzer Submissions Endpoint")
    print("=" * 60)
    print()
    
    # Step 1: Login to get token
    print("Step 1: Getting admin token...")
    try:
        login_url = f"{BASE_URL}/api/admin/login"
        login_data = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }
        
        response = requests.post(login_url, json=login_data, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Login failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
        
        token = response.json().get("token")
        if not token:
            print("❌ No token received from login")
            return False
        
        print(f"✅ Login successful, token received")
        print()
        
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to {BASE_URL}")
        print("   Make sure your backend is running:")
        print("   cd Backend && start_local.bat")
        return False
    except Exception as e:
        print(f"❌ Login error: {e}")
        return False
    
    # Step 2: Test the report-analyzer-submissions endpoint
    print("Step 2: Testing report-analyzer-submissions endpoint...")
    try:
        test_url = f"{BASE_URL}{ENDPOINT}?skip=0&limit=20"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.get(test_url, headers=headers, timeout=10)
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 404:
            print("❌ 404 Not Found - Endpoint does not exist!")
            print("   This is the issue you're experiencing in production.")
            return False
        
        if response.status_code != 200:
            print(f"❌ Request failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
        
        data = response.json()
        print(f"✅ Endpoint works!")
        print(f"   Total submissions: {data.get('total', 0)}")
        print(f"   Skip: {data.get('skip', 0)}")
        print(f"   Limit: {data.get('limit', 0)}")
        print(f"   Submissions count: {len(data.get('submissions', []))}")
        
        # Print first submission if available
        submissions = data.get('submissions', [])
        if submissions:
            print()
            print("Sample submission:")
            print(json.dumps(submissions[0], indent=2))
        else:
            print()
            print("   (No submissions in database yet - this is OK)")
        
        print()
        return True
        
    except Exception as e:
        print(f"❌ Endpoint test error: {e}")
        return False
    
    # Step 3: Check API docs
    print("Step 3: Checking API documentation...")
    try:
        docs_url = f"{BASE_URL}/docs"
        print(f"✅ You can view API docs at: {docs_url}")
        print("   Look for: GET /api/admin/report-analyzer-submissions")
        print()
    except:
        pass
    
    print("=" * 60)
    return True


def main():
    """Main test runner"""
    print()
    print("🧪 Report Analyzer Endpoint Test")
    print()
    print(f"Testing against: {BASE_URL}")
    print()
    
    success = test_endpoint()
    
    if success:
        print("=" * 60)
        print("✅ SUCCESS!")
        print("=" * 60)
        print()
        print("The endpoint works locally. Now you can deploy to production:")
        print()
        print("cd Backend")
        print("./deploy.sh YOUR_GOOGLE_API_KEY")
        print()
        print("After deployment, the endpoint will work in production too.")
        print()
        return 0
    else:
        print("=" * 60)
        print("❌ FAILED!")
        print("=" * 60)
        print()
        print("The endpoint is not working. Please check:")
        print("1. Is the backend running? (cd Backend && start_local.bat)")
        print("2. Is it running on port 8000?")
        print("3. Check the backend logs for errors")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())

