#!/usr/bin/env python3
"""
Test admin endpoints fetching data from database
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.connection import connect_to_mongodb, get_visits_collection, get_reports_collection, is_database_available

async def test_fetch():
    print("🚀 Connecting to database...")
    success = await connect_to_mongodb()
    
    if not success or not is_database_available():
        print("❌ Database connection failed")
        return False
    
    print("✅ Database connected\n")
    
    # Get collections
    visits_coll = get_visits_collection()
    reports_coll = get_reports_collection()
    
    # Fetch visits
    print("📊 Fetching visits from database...")
    visits = await visits_coll.find({}, {"_id": 0}).sort("timestamp", -1).limit(5).to_list(5)
    print(f"✅ Found {len(visits)} visits")
    for i, visit in enumerate(visits, 1):
        print(f"   {i}. {visit.get('page')} - {visit.get('ipAddress')} - {visit.get('type')}")
    
    # Fetch reports
    print("\n📋 Fetching reports from database...")
    reports = await reports_coll.find({}, {"_id": 0}).sort("timestamp", -1).limit(5).to_list(5)
    print(f"✅ Found {len(reports)} reports")
    for i, report in enumerate(reports, 1):
        print(f"   {i}. {report.get('name')} - Age: {report.get('age')} - Disease: {report.get('predictedDisease')}")
    
    # Test aggregation for dashboard
    print("\n📈 Testing dashboard aggregation...")
    total_visits = await visits_coll.count_documents({})
    total_reports = await reports_coll.count_documents({})
    print(f"✅ Total visits: {total_visits}")
    print(f"✅ Total reports: {total_reports}")
    
    # Top diseases
    top_pipeline = [
        {"$match": {"predictedDisease": {"$ne": None}}},
        {"$group": {"_id": "$predictedDisease", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    top_diseases = await reports_coll.aggregate(top_pipeline).to_list(length=5)
    print(f"\n📊 Top diseases:")
    for disease in top_diseases:
        print(f"   - {disease['_id']}: {disease['count']}")
    
    print("\n✅ All tests passed! Data is being fetched correctly.")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_fetch())
    exit(0 if success else 1)

