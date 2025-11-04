#!/usr/bin/env python3
"""
Test admin API endpoints
"""
import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://localhost:8000"

def wait_for_server(max_retries=10):
    """Wait for server to be ready"""
    print("⏳ Waiting for server to start...")
    for i in range(max_retries):
        try:
            urllib.request.urlopen(f"{BASE_URL}/docs", timeout=2)
            print("✅ Server is ready!")
            return True
        except:
            time.sleep(2)
            print(f"   Retry {i+1}/{max_retries}...")
    print("❌ Server did not start in time")
    return False

def get_admin_token():
    """Login and get admin token"""
    print("\n🔑 Getting admin token...")
    try:
        data = json.dumps({"email": "m87.krishna@gmail.com", "password": "Vadg@44"}).encode('utf-8')
        req = urllib.request.Request(
            f"{BASE_URL}/api/admin/login",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            token = result.get('token')
            print(f"✅ Got token: {token[:50]}...")
            return token
    except Exception as e:
        print(f"❌ Failed to get token: {e}")
        return None

def test_endpoint(name, url, token):
    """Test an API endpoint"""
    print(f"\n🧪 Testing {name}: {url}")
    try:
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        
        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            data = json.loads(response.read().decode('utf-8'))
            
            print(f"✅ Status: {status}")
            
            # Show data summary based on endpoint
            if 'totalVisits' in data:
                print(f"   Total Visits: {data.get('totalVisits')}")
                print(f"   Total Reports: {data.get('totalReports')}")
                if 'topDiseases' in data:
                    print(f"   Top Diseases: {len(data.get('topDiseases', []))}")
            elif 'visits' in data:
                print(f"   Visits: {len(data.get('visits', []))}")
                print(f"   Total: {data.get('total', 0)}")
                if data.get('visits'):
                    print(f"   Sample: {data['visits'][0].get('page', 'N/A')}")
            elif 'reports' in data:
                print(f"   Reports: {len(data.get('reports', []))}")
                print(f"   Total: {data.get('total', 0)}")
                if data.get('reports'):
                    print(f"   Sample: {data['reports'][0].get('name', 'N/A')} - {data['reports'][0].get('predictedDisease', 'N/A')}")
            elif 'uniqueVisitors' in data:
                print(f"   Unique Visitors: {data.get('uniqueVisitors')}")
                print(f"   Total Visits: {data.get('totalVisits')}")
                print(f"   New Users: {data.get('newUsers')}")
                print(f"   Returning Users: {data.get('returningUsers')}")
            
            return True
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error {e.code}: {e.read().decode('utf-8')}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    # Wait for server
    if not wait_for_server():
        return False
    
    # Get token
    token = get_admin_token()
    if not token:
        return False
    
    # Test endpoints
    results = []
    
    print("\n" + "="*60)
    print("Testing Admin API Endpoints")
    print("="*60)
    
    results.append(test_endpoint(
        "Dashboard", 
        f"{BASE_URL}/api/dashboard", 
        token
    ))
    
    results.append(test_endpoint(
        "Visitors Analytics", 
        f"{BASE_URL}/api/analytics/visitors", 
        token
    ))
    
    results.append(test_endpoint(
        "Visits List", 
        f"{BASE_URL}/api/visit?page=1&limit=10", 
        token
    ))
    
    results.append(test_endpoint(
        "Reports List", 
        f"{BASE_URL}/api/reports?page=1&limit=10", 
        token
    ))
    
    print("\n" + "="*60)
    print(f"📊 RESULTS: {sum(results)}/{len(results)} endpoints working")
    print("="*60)
    
    if sum(results) == len(results):
        print("✅ ALL TESTS PASSED!")
        return True
    else:
        print("❌ SOME TESTS FAILED")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

