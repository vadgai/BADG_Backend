"""
Location Analytics
Tracks geographic usage patterns and statistics
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict

from .models import LocationAnalyticsDocument
from database.connection import get_database, is_database_available


async def aggregate_location_stats(
    country: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Aggregate location statistics for a specific location and date.
    
    Args:
        country: Country code
        state: State/Province
        city: City name
        date: Date in YYYY-MM-DD format (defaults to today)
        
    Returns:
        Aggregated location statistics
    """
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    
    if not is_database_available():
        return {"error": "Database not available"}
    
    db = get_database()
    if db is None:
        return {"error": "Database not available"}
    
    # Build location filter
    location_filter = {}
    if country:
        location_filter["country"] = country
    if state:
        location_filter["state"] = state
    if city:
        location_filter["city"] = city
    
    # Get sessions for this location
    sessions_collection = db.sessions
    date_start = datetime.strptime(date, "%Y-%m-%d")
    date_end = date_start + timedelta(days=1)
    
    location_filter["started_at"] = {
        "$gte": date_start,
        "$lt": date_end
    }
    
    sessions = []
    async for session in sessions_collection.find(location_filter):
        sessions.append(session)
    
    # Calculate metrics
    session_count = len(sessions)
    unique_visitors = len(set(s.get("visitor_id") for s in sessions if s.get("visitor_id")))
    
    # Get diagnoses for these sessions
    session_ids = [s.get("session_id") for s in sessions]
    reports_collection = db.reports
    
    diagnosis_count = 0
    async for report in reports_collection.find({
        "sessionId": {"$in": session_ids},
        "timestamp": {
            "$gte": date_start,
            "$lt": date_end
        }
    }):
        diagnosis_count += 1
    
    # Calculate drop-off rate (sessions that didn't complete)
    completed_sessions = len([s for s in sessions if s.get("ended_at")])
    drop_off_rate = (session_count - completed_sessions) / session_count if session_count > 0 else 0
    
    # Calculate average session duration
    durations = [s.get("duration_seconds") for s in sessions if s.get("duration_seconds")]
    avg_session_duration = sum(durations) / len(durations) if durations else None
    
    # Get top diseases for this location
    top_diseases = await get_top_diseases_for_location(country, state, city, date)
    
    # Create or update location analytics document
    location_id = f"{country or 'unknown'}_{state or 'unknown'}_{city or 'unknown'}_{date}"
    location_analytics_collection = db.location_analytics
    
    existing = await location_analytics_collection.find_one({
        "country": country,
        "state": state,
        "city": city,
        "date": date
    })
    
    location_analytics = LocationAnalyticsDocument(
        location_id=location_id,
        country=country,
        state=state,
        city=city,
        date=date,
        session_count=session_count,
        unique_visitors=unique_visitors,
        diagnosis_count=diagnosis_count,
        drop_off_rate=drop_off_rate,
        avg_session_duration=avg_session_duration,
        top_diseases=top_diseases
    )
    
    if existing:
        await location_analytics_collection.update_one(
            {"country": country, "state": state, "city": city, "date": date},
            {"$set": location_analytics.dict()}
        )
    else:
        await location_analytics_collection.insert_one(location_analytics.dict())
    
    return location_analytics.dict()


async def get_top_diseases_for_location(
    country: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    date: Optional[str] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Get top diseases for a specific location.
    
    Args:
        country: Country code
        state: State/Province
        city: City name
        date: Date in YYYY-MM-DD format
        limit: Number of top diseases to return
        
    Returns:
        List of top diseases
    """
    if not is_database_available():
        return []
    
    db = get_database()
    if db is None:
        return []
    
    # Get sessions for this location
    location_filter = {}
    if country:
        location_filter["country"] = country
    if state:
        location_filter["state"] = state
    if city:
        location_filter["city"] = city
    
    if date:
        date_start = datetime.strptime(date, "%Y-%m-%d")
        date_end = date_start + timedelta(days=1)
        location_filter["started_at"] = {
            "$gte": date_start,
            "$lt": date_end
        }
    
    sessions_collection = db.sessions
    session_ids = []
    async for session in sessions_collection.find(location_filter):
        session_ids.append(session.get("session_id"))
    
    if not session_ids:
        return []
    
    # Get reports for these sessions
    reports_collection = db.reports
    disease_counts = defaultdict(int)
    
    async for report in reports_collection.find({
        "sessionId": {"$in": session_ids}
    }):
        disease = report.get("predictedDisease")
        if disease:
            disease_counts[disease] += 1
    
    # Sort and return top diseases
    top_diseases = sorted(
        [{"disease": k, "count": v} for k, v in disease_counts.items()],
        key=lambda x: x["count"],
        reverse=True
    )[:limit]
    
    return top_diseases


async def get_location_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = "country"  # country, state, city
) -> Dict[str, Any]:
    """
    Get location statistics aggregated by country/state/city.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        group_by: Grouping level (country, state, city)
        
    Returns:
        Location statistics grouped by specified level
    """
    if not is_database_available():
        return {"error": "Database not available"}
    
    db = get_database()
    if db is None:
        return {"error": "Database not available"}
    
    if start_date is None:
        start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
    
    location_analytics_collection = db.location_analytics
    
    # Build aggregation pipeline
    group_field = group_by
    if group_by == "country":
        group_field = "$country"
    elif group_by == "state":
        group_field = {"country": "$country", "state": "$state"}
    elif group_by == "city":
        group_field = {"country": "$country", "state": "$state", "city": "$city"}
    
    pipeline = [
        {
            "$match": {
                "date": {"$gte": start_date, "$lte": end_date}
            }
        },
        {
            "$group": {
                "_id": group_field,
                "total_sessions": {"$sum": "$session_count"},
                "total_visitors": {"$sum": "$unique_visitors"},
                "total_diagnoses": {"$sum": "$diagnosis_count"},
                "avg_drop_off_rate": {"$avg": "$drop_off_rate"},
                "avg_session_duration": {"$avg": "$avg_session_duration"},
            }
        },
        {
            "$sort": {"total_sessions": -1}
        }
    ]
    
    results = []
    async for result in location_analytics_collection.aggregate(pipeline):
        results.append({
            "location": result["_id"],
            "total_sessions": result.get("total_sessions", 0),
            "total_visitors": result.get("total_visitors", 0),
            "total_diagnoses": result.get("total_diagnoses", 0),
            "avg_drop_off_rate": result.get("avg_drop_off_rate"),
            "avg_session_duration": result.get("avg_session_duration"),
        })
    
    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date,
            "group_by": group_by
        },
        "locations": results,
    }

