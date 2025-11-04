"""
Admin Analytics Routes for VADG
Advanced analytics with JWT authentication and MongoDB aggregations
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status

from auth.jwt_auth import get_current_admin
from database.connection import (
    get_visits_collection,
    get_reports_collection,
    get_partial_reports_collection,
    is_database_available
)
from in_memory_storage import (
    get_visits_from_memory,
    get_reports_from_memory,
    get_dashboard_stats_from_memory,
    in_memory_visits,
    in_memory_reports
)
from models.admin_models import (
    AdminLoginRequest,
    AdminToken,
    AnalyticsSummary,
    VisitorAnalytics,
    FunnelAnalytics,
    DiseaseAnalytics,
    LanguageAnalytics,
    Visit,
    VisitType,
    PartialReport
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin-analytics"])


def _get_thirty_days_ago() -> datetime:
    """Get datetime 30 days ago."""
    return datetime.utcnow() - timedelta(days=30)


@router.post("/login", response_model=AdminToken)
async def admin_login(credentials: AdminLoginRequest):
    """JWT-based admin login."""
    from auth.jwt_auth import authenticate_admin, create_access_token

    admin_data = authenticate_admin(credentials.email, credentials.password)
    if not admin_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    token = create_access_token(admin_data)
    return AdminToken(token=token)


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(current_admin=Depends(get_current_admin)):
    """Get analytics summary for dashboard cards."""
    if not is_database_available():
        # Return mock data for local development
        return AnalyticsSummary(
            dau=25,
            wau=125,
            mau=450,
            totalVisits=1250,
            completedDiagnoses=380,
            completionRate=30.4,
            newUsers=85,
            returningUsers=165
        )

    visits_coll = get_visits_collection()
    reports_coll = get_reports_collection()

    thirty_days_ago = _get_thirty_days_ago()
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    one_day_ago = datetime.utcnow() - timedelta(days=1)

    try:
        # DAU, WAU, MAU based on unique sessions
        dau_pipeline = [
            {"$match": {"timestamp": {"$gte": one_day_ago}}},
            {"$group": {"_id": "$sessionId"}},
            {"$count": "unique"}
        ]
        wau_pipeline = [
            {"$match": {"timestamp": {"$gte": seven_days_ago}}},
            {"$group": {"_id": "$sessionId"}},
            {"$count": "unique"}
        ]
        mau_pipeline = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
            {"$group": {"_id": "$sessionId"}},
            {"$count": "unique"}
        ]

        dau_result = await visits_coll.aggregate(dau_pipeline).to_list(1)
        wau_result = await visits_coll.aggregate(wau_pipeline).to_list(1)
        mau_result = await visits_coll.aggregate(mau_pipeline).to_list(1)

        dau = (dau_result[0]["unique"] if dau_result else 0)
        wau = (wau_result[0]["unique"] if wau_result else 0)
        mau = (mau_result[0]["unique"] if mau_result else 0)

        # Total visits (30 days)
        total_visits = await visits_coll.count_documents({"timestamp": {"$gte": thirty_days_ago}})

        # Completed diagnoses (30 days)
        completed_diagnoses = await visits_coll.count_documents({
            "timestamp": {"$gte": thirty_days_ago},
            "type": VisitType.COMPLETED_DIAGNOSIS
        })

        # Completion rate
        completion_rate = (completed_diagnoses / total_visits * 100) if total_visits > 0 else 0.0

        # New vs returning users (30 days)
        user_type_pipeline = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
            {"$group": {"_id": "$isReturningUser", "count": {"$sum": 1}}}
        ]
        user_type_result = await visits_coll.aggregate(user_type_pipeline).to_list(2)

        new_users = next((item["count"] for item in user_type_result if item["_id"] is False), 0)
        returning_users = next((item["count"] for item in user_type_result if item["_id"] is True), 0)

        return AnalyticsSummary(
            dau=dau,
            wau=wau,
            mau=mau,
            totalVisits=total_visits,
            completedDiagnoses=completed_diagnoses,
            completionRate=round(completion_rate, 2),
            newUsers=new_users,
            returningUsers=returning_users
        )

    except Exception as e:
        logger.error(f"Error fetching analytics summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching analytics data"
        )


@router.get("/visitors", response_model=VisitorAnalytics)
async def get_visitor_analytics(current_admin=Depends(get_current_admin)):
    """Get visitor analytics data."""
    if not is_database_available():
        # Use in-memory data if database is not available
        logger.info("Using in-memory data for visitor analytics")
        
        # Calculate analytics from in-memory visits
        total_visits = len(in_memory_visits)

        # Unique visitors via coalesced key: sessionId or ip|ua
        unique_keys = set()
        for visit in in_memory_visits:
            session_id = visit.get("sessionId")
            ip = visit.get("ipAddress", "unknown")
            ua = visit.get("userAgent", "unknown")
            key = session_id if session_id else f"{ip}|{ua}"
            unique_keys.add(key)
        unique_visitors = len(unique_keys)

        # New vs returning
        new_users = sum(1 for v in in_memory_visits if not v.get("isReturningUser", False))
        returning_users = sum(1 for v in in_memory_visits if v.get("isReturningUser", False))

        # Visits per day (last 30 days)
        thirty_days_ago = _get_thirty_days_ago()
        visits_by_date = {}
        for visit in in_memory_visits:
            if visit.get("timestamp", datetime.min) >= thirty_days_ago:
                date_str = visit["timestamp"].strftime("%Y-%m-%d")
                visits_by_date[date_str] = visits_by_date.get(date_str, 0) + 1
        visits_per_day = [{"date": k, "count": v} for k, v in sorted(visits_by_date.items())]

        # Top pages
        pages_count = {}
        for visit in in_memory_visits:
            page = visit.get("page")
            if page:
                pages_count[page] = pages_count.get(page, 0) + 1
        top_pages = [{"page": k, "count": v} for k, v in sorted(pages_count.items(), key=lambda x: x[1], reverse=True)[:10]]

        # Referrers
        referrer_count = {}
        for visit in in_memory_visits:
            referrer = visit.get("referrer", "direct")
            referrer_count[referrer] = referrer_count.get(referrer, 0) + 1
        referrers = [{"source": k, "count": v} for k, v in sorted(referrer_count.items(), key=lambda x: x[1], reverse=True)[:10]]

        # Devices (simple UA parse)
        def to_browser(ua: str) -> str:
            s = (ua or "").lower()
            if "edg" in s:
                return "Edge"
            if "chrome" in s and "edg" not in s and "chromium" not in s:
                return "Chrome"
            if "safari" in s and "chrome" not in s:
                return "Safari"
            if "firefox" in s:
                return "Firefox"
            if "android webview" in s or "wv" in s:
                return "Android WebView"
            return "Other"

        browser_counts = {}
        for visit in in_memory_visits:
            browser = to_browser(visit.get("userAgent", ""))
            browser_counts[browser] = browser_counts.get(browser, 0) + 1
        devices = [{"browser": k, "count": v} for k, v in browser_counts.items()]

        return VisitorAnalytics(
            visitsPerDay=visits_per_day,
            topPages=top_pages,
            referrers=referrers,
            devices=devices,
            uniqueVisitors=unique_visitors,
            newUsers=new_users,
            returningUsers=returning_users
        )
    
    # Use database for visitor analytics
    visits_coll = get_visits_collection()
    thirty_days_ago = _get_thirty_days_ago()

    try:
        # Total visits
        total_visits = await visits_coll.count_documents({})

        # Unique visitors via coalesced key: sessionId or ip|ua
        pipeline_unique = [
            {
                "$group": {
                    "_id": {
                        "$ifNull": [
                            "$sessionId",
                            {"$concat": [
                                {"$ifNull": ["$ipAddress", "unknown"]},
                                "|",
                                {"$ifNull": ["$userAgent", "unknown"]}
                            ]}
                        ]
                    }
                }
            },
            {"$count": "unique"}
        ]
        res_unique = await visits_coll.aggregate(pipeline_unique).to_list(1)
        unique_visitors = (res_unique[0]["unique"] if res_unique else 0)

        # New vs returning
        pipeline_ret = [
            {"$group": {"_id": "$isReturningUser", "count": {"$sum": 1}}}
        ]
        ret_data = await visits_coll.aggregate(pipeline_ret).to_list(5)
        returning_users = next((x["count"] for x in ret_data if x.get("_id") is True), 0)
        new_users = next((x["count"] for x in ret_data if x.get("_id") in (False, None)), 0)

        # Visits per day (last 30 days)
        pipeline_per_day = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}}, "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        per_day_raw = await visits_coll.aggregate(pipeline_per_day).to_list(length=100)
        visits_per_day = [{"date": d["_id"], "count": d["count"]} for d in per_day_raw]

        # Top pages
        pipeline_pages = [
            {"$group": {"_id": "$page", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        pages_raw = await visits_coll.aggregate(pipeline_pages).to_list(length=10)
        top_pages = [{"page": p["_id"], "count": p["count"]} for p in pages_raw if p.get("_id")]

        # Referrers
        pipeline_ref = [
            {"$group": {"_id": "$referrer", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        ref_raw = await visits_coll.aggregate(pipeline_ref).to_list(length=10)
        referrers = [{"source": (r["_id"] or "direct"), "count": r["count"]} for r in ref_raw]

        # Devices (simple UA parse)
        pipeline_ua = [
            {"$group": {"_id": "$userAgent", "count": {"$sum": 1}}}
        ]
        ua_raw = await visits_coll.aggregate(pipeline_ua).to_list(length=1000)
        
        def to_browser(ua: str) -> str:
            s = (ua or "").lower()
            if "edg" in s:
                return "Edge"
            if "chrome" in s and "edg" not in s and "chromium" not in s:
                return "Chrome"
            if "safari" in s and "chrome" not in s:
                return "Safari"
            if "firefox" in s:
                return "Firefox"
            if "android webview" in s or "wv" in s:
                return "Android WebView"
            return "Other"
        
        browser_counts: dict[str, int] = {}
        for item in ua_raw:
            browser = to_browser(item.get("_id", ""))
            browser_counts[browser] = browser_counts.get(browser, 0) + int(item.get("count", 0))
        devices = [{"browser": k, "count": v} for k, v in browser_counts.items()]

        return VisitorAnalytics(
            visitsPerDay=visits_per_day,
            topPages=top_pages,
            referrers=referrers,
            devices=devices,
            uniqueVisitors=unique_visitors,
            newUsers=new_users,
            returningUsers=returning_users
        )

    except Exception as e:
        logger.error(f"Error fetching visitor analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching visitor analytics"
        )


@router.get("/funnel", response_model=FunnelAnalytics)
async def get_funnel_analytics(current_admin=Depends(get_current_admin)):
    """Get funnel analytics data."""
    if not is_database_available():
        # Return mock data for local development
        return FunnelAnalytics(
            pageHits=1250,
            started=780,
            lastStagePartials=95,
            completed=380,
            conversion=30.4
        )

    visits_coll = get_visits_collection()
    partial_coll = get_partial_reports_collection()
    thirty_days_ago = _get_thirty_days_ago()

    try:
        # Page hits on diagnosis pages
        page_hits = await visits_coll.count_documents({
            "timestamp": {"$gte": thirty_days_ago},
            "page": {"$regex": "diagnosis", "$options": "i"}
        })

        # Started diagnoses (estimate by unique sessions with diagnosis visits)
        started_pipeline = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}, "page": {"$regex": "diagnosis"}}},
            {"$group": {"_id": "$sessionId"}},
            {"$count": "unique"}
        ]
        started_result = await visits_coll.aggregate(started_pipeline).to_list(1)
        started = started_result[0]["unique"] if started_result else 0

        # Last stage partials
        last_stage_partials = await partial_coll.count_documents({
            "createdAt": {"$gte": thirty_days_ago}
        })

        # Completed diagnoses
        completed = await visits_coll.count_documents({
            "timestamp": {"$gte": thirty_days_ago},
            "type": VisitType.COMPLETED_DIAGNOSIS
        })

        # Conversion rate
        conversion = (completed / page_hits * 100) if page_hits > 0 else 0.0

        return FunnelAnalytics(
            pageHits=page_hits,
            started=started,
            lastStagePartials=last_stage_partials,
            completed=completed,
            conversion=round(conversion, 2)
        )

    except Exception as e:
        logger.error(f"Error fetching funnel analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching funnel analytics"
        )


@router.get("/diseases", response_model=DiseaseAnalytics)
async def get_disease_analytics(current_admin=Depends(get_current_admin)):
    """Get disease analytics data."""
    if not is_database_available():
        # Return mock data for local development
        return DiseaseAnalytics(
            topDiseases=[
                {"name": "Hypertension", "count": 85},
                {"name": "Diabetes", "count": 72},
                {"name": "Anxiety", "count": 58},
                {"name": "Depression", "count": 45},
                {"name": "Migraine", "count": 38}
            ],
            trend=[
                {"date": "2025-11-01", "count": 12},
                {"date": "2025-10-31", "count": 8},
                {"date": "2025-10-30", "count": 15}
            ]
        )

    reports_coll = get_reports_collection()
    thirty_days_ago = _get_thirty_days_ago()

    try:
        # Top diseases
        top_diseases_pipeline = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}, "predictedDisease": {"$ne": None}}},
            {"$group": {"_id": "$predictedDisease", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        top_diseases_raw = await reports_coll.aggregate(top_diseases_pipeline).to_list(10)
        top_diseases = [{"name": item["_id"], "count": item["count"]} for item in top_diseases_raw if item["_id"]]

        # Disease trend over last 30 days
        trend_pipeline = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}, "predictedDisease": {"$ne": None}}},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}
        ]
        trend_raw = await reports_coll.aggregate(trend_pipeline).to_list(100)
        trend = [{"date": item["_id"], "count": item["count"]} for item in trend_raw]

        return DiseaseAnalytics(
            topDiseases=top_diseases,
            trend=trend
        )

    except Exception as e:
        logger.error(f"Error fetching disease analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching disease analytics"
        )


@router.get("/languages", response_model=LanguageAnalytics)
async def get_language_analytics(current_admin=Depends(get_current_admin)):
    """Get language usage analytics."""
    if not is_database_available():
        # Return mock data for local development
        return LanguageAnalytics(
            byLanguage=[
                {"lang": "en", "count": 280},
                {"lang": "hi", "count": 145},
                {"lang": "ta", "count": 85},
                {"lang": "te", "count": 52},
                {"lang": "kn", "count": 38}
            ]
        )

    reports_coll = get_reports_collection()
    thirty_days_ago = _get_thirty_days_ago()

    try:
        # Language usage (from report language context if available)
        # For now, return empty as language tracking needs to be added to reports
        # This can be inferred from user session or added to reports schema later
        language_pipeline = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
            {"$group": {"_id": {"$ifNull": ["$language", "en"]}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        language_raw = await reports_coll.aggregate(language_pipeline).to_list(10)
        by_language = [{"lang": item["_id"], "count": item["count"]} for item in language_raw]

        return LanguageAnalytics(byLanguage=by_language)

    except Exception as e:
        logger.error(f"Error fetching language analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching language analytics"
        )
