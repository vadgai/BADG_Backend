"""
Device Analytics
Tracks device, browser, and OS performance metrics
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict

from .models import DeviceAnalyticsDocument, DeviceType
from database.connection import get_database, is_database_available


async def aggregate_device_stats(
    device_type: Optional[DeviceType] = None,
    browser: Optional[str] = None,
    os: Optional[str] = None,
    date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Aggregate device statistics for a specific device configuration and date.
    
    Args:
        device_type: Device type
        browser: Browser name
        os: Operating system
        date: Date in YYYY-MM-DD format (defaults to today)
        
    Returns:
        Aggregated device statistics
    """
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    
    if not is_database_available():
        return {"error": "Database not available"}
    
    db = get_database()
    if db is None:
        return {"error": "Database not available"}
    
    # Build device filter
    device_filter = {}
    if device_type:
        device_filter["device_type"] = device_type.value if isinstance(device_type, DeviceType) else device_type
    if browser:
        device_filter["browser"] = browser
    if os:
        device_filter["os"] = os
    
    # Get sessions for this device configuration
    sessions_collection = db.sessions
    date_start = datetime.strptime(date, "%Y-%m-%d")
    date_end = date_start + timedelta(days=1)
    
    device_filter["started_at"] = {
        "$gte": date_start,
        "$lt": date_end
    }
    
    sessions = []
    async for session in sessions_collection.find(device_filter):
        sessions.append(session)
    
    # Calculate metrics
    session_count = len(sessions)
    unique_visitors = len(set(s.get("visitor_id") for s in sessions if s.get("visitor_id")))
    
    # Calculate average session duration
    durations = [s.get("duration_seconds") for s in sessions if s.get("duration_seconds")]
    avg_session_duration = sum(durations) / len(durations) if durations else None
    
    # Get conversion rate (sessions that completed diagnosis)
    completed_sessions = len([s for s in sessions if s.get("ended_at")])
    conversion_rate = completed_sessions / session_count if session_count > 0 else 0
    
    # Get JavaScript errors from error logs
    session_ids = [s.get("session_id") for s in sessions]
    errors_collection = db.errors
    
    js_error_count = 0
    async for error in errors_collection.find({
        "session_id": {"$in": session_ids},
        "error_type": {"$regex": ".*[Jj]ava[Ss]cript.*|.*[Jj]S.*"},
        "timestamp": {
            "$gte": date_start,
            "$lt": date_end
        }
    }):
        js_error_count += 1
    
    # Get average load time from events (if available)
    events_collection = db.events
    load_times = []
    async for event in events_collection.find({
        "session_id": {"$in": session_ids},
        "event_name": "visit_home",
        "metadata.load_time": {"$exists": True}
    }):
        load_time = event.get("metadata", {}).get("load_time")
        if load_time:
            load_times.append(load_time)
    
    avg_load_time = sum(load_times) / len(load_times) if load_times else None
    
    # Create or update device analytics document
    device_id = f"{device_type or 'unknown'}_{browser or 'unknown'}_{os or 'unknown'}_{date}"
    device_analytics_collection = db.device_analytics
    
    existing = await device_analytics_collection.find_one({
        "device_type": device_type.value if isinstance(device_type, DeviceType) else device_type,
        "browser": browser,
        "os": os,
        "date": date
    })
    
    device_analytics = DeviceAnalyticsDocument(
        device_id=device_id,
        device_type=device_type or DeviceType.UNKNOWN,
        browser=browser,
        os=os,
        date=date,
        session_count=session_count,
        unique_visitors=unique_visitors,
        avg_load_time=avg_load_time,
        js_error_count=js_error_count,
        conversion_rate=conversion_rate,
        avg_session_duration=avg_session_duration
    )
    
    if existing:
        await device_analytics_collection.update_one(
            {
                "device_type": device_type.value if isinstance(device_type, DeviceType) else device_type,
                "browser": browser,
                "os": os,
                "date": date
            },
            {"$set": device_analytics.dict()}
        )
    else:
        await device_analytics_collection.insert_one(device_analytics.dict())
    
    return device_analytics.dict()


async def get_device_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = "device_type"  # device_type, browser, os
) -> Dict[str, Any]:
    """
    Get device statistics aggregated by device type, browser, or OS.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        group_by: Grouping level (device_type, browser, os)
        
    Returns:
        Device statistics grouped by specified level
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
    
    device_analytics_collection = db.device_analytics
    
    # Build aggregation pipeline
    group_field = f"${group_by}"
    
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
                "avg_load_time": {"$avg": "$avg_load_time"},
                "total_js_errors": {"$sum": "$js_error_count"},
                "avg_conversion_rate": {"$avg": "$conversion_rate"},
                "avg_session_duration": {"$avg": "$avg_session_duration"},
            }
        },
        {
            "$sort": {"total_sessions": -1}
        }
    ]
    
    results = []
    async for result in device_analytics_collection.aggregate(pipeline):
        results.append({
            "device": result["_id"],
            "total_sessions": result.get("total_sessions", 0),
            "total_visitors": result.get("total_visitors", 0),
            "avg_load_time": result.get("avg_load_time"),
            "total_js_errors": result.get("total_js_errors", 0),
            "avg_conversion_rate": result.get("avg_conversion_rate"),
            "avg_session_duration": result.get("avg_session_duration"),
        })
    
    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date,
            "group_by": group_by
        },
        "devices": results,
    }

