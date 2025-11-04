#!/usr/bin/env python3
"""
Add dummy data to MongoDB for testing admin pages
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta
import random

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.connection import connect_to_mongodb, get_visits_collection, get_reports_collection, is_database_available

async def add_dummy_data():
    print("🚀 Connecting to database...")
    success = await connect_to_mongodb()
    
    if not success or not is_database_available():
        print("❌ Database connection failed")
        return False
    
    print("✅ Database connected")
    
    # Get collections
    visits_coll = get_visits_collection()
    reports_coll = get_reports_collection()
    
    # Add dummy visit data
    print("\n📊 Adding dummy visit data...")
    visit_data = [
        {
            "timestamp": datetime.utcnow() - timedelta(hours=1),
            "ipAddress": "192.168.1.100",
            "page": "/",
            "referrer": "google.com",
            "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0",
            "sessionId": "session-123-abc",
            "isReturningUser": False,
            "type": "page_hit"
        },
        {
            "timestamp": datetime.utcnow() - timedelta(minutes=30),
            "ipAddress": "192.168.1.101",
            "page": "/diagnosis",
            "referrer": "direct",
            "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/119.0",
            "sessionId": "session-456-def",
            "isReturningUser": False,
            "type": "page_hit"
        },
        {
            "timestamp": datetime.utcnow() - timedelta(minutes=15),
            "ipAddress": "192.168.1.102",
            "page": "/diagnosis",
            "referrer": "facebook.com",
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
            "sessionId": "session-789-ghi",
            "isReturningUser": True,
            "type": "completed_diagnosis"
        },
        {
            "timestamp": datetime.utcnow() - timedelta(hours=2),
            "ipAddress": "192.168.1.103",
            "page": "/about",
            "referrer": "twitter.com",
            "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) Safari/604.1",
            "sessionId": "session-101-jkl",
            "isReturningUser": False,
            "type": "page_hit"
        },
        {
            "timestamp": datetime.utcnow() - timedelta(days=1),
            "ipAddress": "192.168.1.104",
            "page": "/contact",
            "referrer": "linkedin.com",
            "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/119.0.0.0",
            "sessionId": "session-202-mno",
            "isReturningUser": True,
            "type": "page_hit"
        }
    ]
    
    # Insert visits
    result = await visits_coll.insert_many(visit_data)
    print(f"✅ Inserted {len(result.inserted_ids)} visit records")
    
    # Add dummy report data
    print("\n📋 Adding dummy report data...")
    report_data = [
        {
            "name": "John Doe",
            "age": 35,
            "gender": "Male",
            "height": 175,
            "weight": 70,
            "symptoms": ["fever", "headache", "cough"],
            "predictedDisease": "Common Cold",
            "severity": "mild",
            "timestamp": datetime.utcnow() - timedelta(hours=2)
        },
        {
            "name": "Jane Smith",
            "age": 28,
            "gender": "Female",
            "height": 165,
            "weight": 60,
            "symptoms": ["fatigue", "dizziness", "nausea"],
            "predictedDisease": "Anemia",
            "severity": "moderate",
            "timestamp": datetime.utcnow() - timedelta(hours=5)
        },
        {
            "name": "Bob Johnson",
            "age": 45,
            "gender": "Male",
            "height": 180,
            "weight": 85,
            "symptoms": ["chest pain", "shortness of breath", "fatigue"],
            "predictedDisease": "Hypertension",
            "severity": "moderate",
            "timestamp": datetime.utcnow() - timedelta(days=1)
        },
        {
            "name": "Alice Williams",
            "age": 32,
            "gender": "Female",
            "height": 160,
            "weight": 55,
            "symptoms": ["back pain", "stiffness", "muscle pain"],
            "predictedDisease": "Arthritis",
            "severity": "mild",
            "timestamp": datetime.utcnow() - timedelta(days=2)
        },
        {
            "name": "Charlie Brown",
            "age": 50,
            "gender": "Male",
            "height": 178,
            "weight": 90,
            "symptoms": ["frequent urination", "excessive thirst", "weight loss"],
            "predictedDisease": "Diabetes",
            "severity": "moderate",
            "timestamp": datetime.utcnow() - timedelta(days=3)
        }
    ]
    
    # Insert reports
    result = await reports_coll.insert_many(report_data)
    print(f"✅ Inserted {len(result.inserted_ids)} report records")
    
    # Verify data
    print("\n🔍 Verifying data...")
    visit_count = await visits_coll.count_documents({})
    report_count = await reports_coll.count_documents({})
    
    print(f"📊 Total visits in database: {visit_count}")
    print(f"📋 Total reports in database: {report_count}")
    
    print("\n✅ Dummy data added successfully!")
    return True

if __name__ == "__main__":
    success = asyncio.run(add_dummy_data())
    exit(0 if success else 1)

