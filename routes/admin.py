"""
Admin Routes
Handles admin authentication, analytics, and data management
"""

import logging
from datetime import datetime, timedelta
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timedelta

# Try to import database models, but make them optional
try:
    from database.models import (
        AdminLogin,
        AdminResponse,
        Token,
        AnalyticsResponse,
        FormSubmission
    )
    MODELS_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Database models not available - creating dummy models")
    MODELS_AVAILABLE = False
    # Create dummy Pydantic models
    class AdminLogin(BaseModel):
        username: str
        password: str
    class AdminResponse(BaseModel):
        username: str
        email: Optional[str] = None
    class Token(BaseModel):
        access_token: str
        token_type: str
    class AnalyticsResponse(BaseModel):
        pass
    class FormSubmission(BaseModel):
        pass

# Try to import database connection functions
try:
    from database.connection import (
        get_admin_collection,
        get_form_submissions_collection,
        get_visit_logs_collection,
        get_users_collection,
        is_database_available,
        get_reports_collection,
        get_visits_collection,
        get_contact_submissions_collection,
        get_report_analyzer_submissions_collection,
    )
    DB_CONNECTION_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Database connection not available")
    DB_CONNECTION_AVAILABLE = False
    # Dummy functions
    def get_admin_collection():
        return None
    def get_form_submissions_collection():
        return None
    def get_visit_logs_collection():
        return None
    def get_users_collection():
        return None
    def is_database_available():
        return False
    def get_reports_collection():
        return None
    def get_visits_collection():
        return None
    def get_contact_submissions_collection():
        return None
    def get_report_analyzer_submissions_collection():
        return None

# Try to import auth modules, but make them optional
try:
    from auth.security import (
        authenticate_admin,
        create_access_token,
        get_current_admin,
        get_current_superadmin,
        JWT_EXPIRY_HOURS
    )
    AUTH_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Auth modules not available - admin features will be disabled")
    AUTH_AVAILABLE = False
    # Create dummy functions for type hints
    def authenticate_admin(username: str, password: str):
        return None
    def create_access_token(data: dict):
        return ""
    def get_current_admin():
        return None
    def get_current_superadmin():
        return None
    JWT_EXPIRY_HOURS = 24

# Try to import JWT auth
try:
    from auth.jwt_auth import get_current_admin as get_jwt_admin
    JWT_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("JWT auth not available")
    JWT_AVAILABLE = False
    def get_jwt_admin():
        return None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])
public_router = APIRouter(prefix="/api", tags=["analytics"])

# Import shared in-memory storage
from in_memory_storage import (
    store_visit_in_memory,
    store_report_in_memory,
    store_contact_in_memory,
    get_visits_from_memory,
    get_reports_from_memory,
    get_contacts_from_memory,
    get_dashboard_stats_from_memory,
    get_report_analyzer_submissions_from_memory,
    delete_report_analyzer_submission_from_memory,
    in_memory_visits,
    in_memory_reports,
    in_memory_contacts
)

# Static admin credentials and token (per requirements)
ADMIN_EMAIL = "m87.krishna@gmail.com"
ADMIN_PASSWORD = "Vadg@44"
ADMIN_TOKEN = "admin-session-token"

# Lightweight token guard for admin-only routes
async def require_admin_token(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ", 1)[1].strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@router.post("/login")
async def admin_login(credentials: dict):
    """JWT-based admin login returning a JWT token."""
    from auth.jwt_auth import authenticate_admin, create_access_token

    email = str(credentials.get("email", "")).strip()
    password = str(credentials.get("password", "")).strip()

    admin_data = authenticate_admin(email, password)
    if not admin_data:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(admin_data)
    return {"success": True, "token": token}


# --- Public ingestion endpoints (no admin token) ---
@public_router.post("/visit")
async def log_visit(payload: dict, request: Request):
    """Logs a site/page visit (hybrid: page hits + completed diagnosis)."""
    page = str(payload.get("page", "")).strip() or None
    visit_type = str(payload.get("type", "page_hit")).strip()  # Hybrid flag
    client_ip = str(payload.get("ipAddress") or (request.client.host if request and request.client else "")) or None

    # Exclusions: do not log admin pages or local dev IPs
    excluded_ips = {"127.0.0.1", "::1"}
    if (page and page.startswith("/admin")) or (client_ip and client_ip in excluded_ips):
        return {"success": True, "skipped": True}

    # Session ID from payload
    session_id = str(payload.get("sessionId") or "").strip() or None
    user_agent = request.headers.get("user-agent") or ""
    referer = request.headers.get("referer") or ""
    # normalize referrer domain
    try:
        ref_domain = re.sub(r"^https?://", "", referer).split("/")[0] if referer else "direct"
    except Exception:
        ref_domain = "direct"

    # Use in-memory storage if DB not available
    if not is_database_available():
        logger.info("Using in-memory storage for visit logging")
        # Check for returning user in memory
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        is_returning = False
        if session_id:
            # Check if sessionId exists in recent visits
            recent_visits = [v for v in in_memory_visits if v.get("sessionId") == session_id and v.get("timestamp", datetime.min) >= thirty_days_ago]
            is_returning = len(recent_visits) > 0
        else:
            # Check by IP + User Agent
            recent_visits = [v for v in in_memory_visits
                           if v.get("ipAddress") == client_ip and v.get("userAgent") == user_agent
                           and v.get("timestamp", datetime.min) >= thirty_days_ago]
            is_returning = len(recent_visits) > 0

        doc = {
            "timestamp": datetime.utcnow(),
            "ipAddress": client_ip,
            "page": page,
            "referrer": ref_domain,
            "userAgent": user_agent,
            "sessionId": session_id,
            "isReturningUser": is_returning,
            "type": visit_type  # Hybrid flag: "page_hit" or "completed_diagnosis"
        }
        await store_visit_in_memory(doc)
        return {"success": True}

    visits = get_visits_collection()

    # Determine returning user by sessionId or ip+ua (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    is_returning = False
    if session_id:
        exists = await visits.find_one({"sessionId": session_id, "timestamp": {"$gte": thirty_days_ago}})
    else:
        exists = await visits.find_one({
            "ipAddress": client_ip,
            "userAgent": user_agent,
            "timestamp": {"$gte": thirty_days_ago}
        })
    is_returning = bool(exists)

    doc = {
        "timestamp": datetime.utcnow(),
        "ipAddress": client_ip,
        "page": page,
        "referrer": ref_domain,
        "userAgent": user_agent,
        "sessionId": session_id,
        "isReturningUser": is_returning,
        "type": visit_type  # Hybrid flag: "page_hit" or "completed_diagnosis"
    }
    await visits.insert_one(doc)
    return {"success": True}


@public_router.post("/report")
async def save_report(payload: dict):
    """Saves a diagnosis report document with user info and prediction."""
    doc = {
        "name": payload.get("name"),
        "age": payload.get("age"),
        "gender": payload.get("gender"),
        "height": payload.get("height"),
        "weight": payload.get("weight"),
        "symptoms": payload.get("symptoms", []),
        "predictedDisease": payload.get("predictedDisease"),
        "severity": payload.get("severity"),
        "timestamp": datetime.utcnow(),
    }

    # Use in-memory storage if DB not available
    if not is_database_available():
        logger.info("Using in-memory storage for report saving")
        await store_report_in_memory(doc)
        logger.info("Report saved (in-memory): name=%s, disease=%s", doc.get("name"), doc.get("predictedDisease"))
        return {"success": True}

    reports = get_reports_collection()
    await reports.insert_one(doc)
    logger.info("Report saved: name=%s, disease=%s", doc.get("name"), doc.get("predictedDisease"))
    return {"success": True}


@public_router.post("/partial-report")
async def save_partial_report(payload: dict):
    """Saves partial report at last stage before final submit (TTL 30d)."""
    if not is_database_available():
        raise HTTPException(status_code=503, detail="Database service unavailable")

    partial_reports = get_partial_reports_collection()
    doc = {
        "createdAt": datetime.utcnow(),
        "sessionId": payload.get("sessionId"),
        "formSnapshot": payload.get("formSnapshot", {}),
        "progress": payload.get("progress", {})
    }
    await partial_reports.insert_one(doc)
    logger.info("Partial report saved: sessionId=%s, stage=%s",
                doc.get("sessionId"), doc.get("progress", {}).get("stage"))
    return {"success": True}


# --- Admin-protected analytics ---
@public_router.get("/reports")
async def get_reports(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), current_admin=Depends(get_current_admin)):
    # Use in-memory data if DB not available
    if not is_database_available():
        logger.info("Using in-memory data for reports")
        return await get_reports_from_memory(page, limit)

    reports = get_reports_collection()
    skip = (page - 1) * limit
    total = await reports.count_documents({})
    cursor = reports.find({}, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"total": total, "page": page, "limit": limit, "reports": items}


@public_router.get("/visit")
async def get_visits(page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200), current_admin=Depends(get_jwt_admin)):
    # Use in-memory data if DB not available
    if not is_database_available():
        logger.info("Using in-memory data for visits")
        return await get_visits_from_memory(page, limit)

    visits = get_visits_collection()
    skip = (page - 1) * limit
    total = await visits.count_documents({})
    cursor = visits.find({}, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"total": total, "page": page, "limit": limit, "visits": items}


@public_router.get("/dashboard")
async def get_dashboard(current_admin=Depends(get_jwt_admin)):
    # Use in-memory data if DB not available
    if not is_database_available():
        logger.info("Using in-memory data for dashboard")
        stats = await get_dashboard_stats_from_memory()

        # Generate some sample data for dashboard
        top_diseases = [
            {"name": "Hypertension", "count": 15},
            {"name": "Diabetes", "count": 12},
            {"name": "Anxiety", "count": 8}
        ]

        reports_over_time = [
            {"date": "2025-11-01", "count": 5},
            {"date": "2025-10-31", "count": 3},
            {"date": "2025-10-30", "count": 7}
        ]

        return {
            **stats,
            "topDiseases": top_diseases,
            "reportsOverTime": reports_over_time,
        }

    reports = get_reports_collection()
    visits = get_visits_collection()

    total_reports = await reports.count_documents({})
    total_visits = await visits.count_documents({})

    # Top diseases aggregation
    top_pipeline = [
        {"$match": {"predictedDisease": {"$ne": None}}},
        {"$group": {"_id": "$predictedDisease", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    top_raw = await reports.aggregate(top_pipeline).to_list(length=5)
    top_diseases = [{"name": d["_id"], "count": d["count"]} for d in top_raw if d.get("_id")]

    # Reports over time (daily for last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    over_time_pipeline = [
        {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    over_time_raw = await reports.aggregate(over_time_pipeline).to_list(length=100)
    reports_over_time = [{"date": r["_id"], "count": r["count"]} for r in over_time_raw]

    return {
        "totalVisits": total_visits,
        "totalReports": total_reports,
        "topDiseases": top_diseases[:3],
        "reportsOverTime": reports_over_time,
    }


@public_router.get("/analytics/visitors")
async def get_visitor_analytics(current_admin=Depends(get_jwt_admin)):
    """Advanced visitor analytics summary."""
    # Use in-memory data if DB not available
    if not is_database_available():
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
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
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

        # User flow
        user_flow = []  # Simplified for in-memory

        return {
            "totalVisits": total_visits,
            "uniqueVisitors": unique_visitors,
            "newUsers": new_users,
            "returningUsers": returning_users,
            "visitsPerDay": visits_per_day,
            "userFlow": user_flow,
            "topPages": top_pages,
            "referrers": referrers,
            "devices": devices
        }

    if True:  # keep indent for easier replace
        visits = get_visits_collection()

        # totalVisits
        total_visits = await visits.count_documents({})

        # uniqueVisitors via coalesced key: sessionId or ip|ua
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
        res_unique = await visits.aggregate(pipeline_unique).to_list(1)
        unique_visitors = (res_unique[0]["unique"] if res_unique else 0)

        # new vs returning
        pipeline_ret = [
            {"$group": {"_id": "$isReturningUser", "count": {"$sum": 1}}}
        ]
        ret_data = await visits.aggregate(pipeline_ret).to_list(5)
        returning_users = next((x["count"] for x in ret_data if x.get("_id") is True), 0)
        new_users = next((x["count"] for x in ret_data if x.get("_id") in (False, None)), 0)

        # visits per day (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        pipeline_per_day = [
            {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}}, "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        per_day_raw = await visits.aggregate(pipeline_per_day).to_list(length=100)
        visits_per_day = [{"date": d["_id"], "count": d["count"]} for d in per_day_raw]

        # top pages
        pipeline_pages = [
            {"$group": {"_id": "$page", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        pages_raw = await visits.aggregate(pipeline_pages).to_list(length=10)
        top_pages = [{"page": p["_id"], "count": p["count"]} for p in pages_raw if p.get("_id")]

        # referrers
        pipeline_ref = [
            {"$group": {"_id": "$referrer", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        ref_raw = await visits.aggregate(pipeline_ref).to_list(length=10)
        referrers = [{"source": (r["_id"] or "direct"), "count": r["count"]} for r in ref_raw]

        # devices (simple UA parse)
        # Aggregate by UA then map to browser buckets in Python
        pipeline_ua = [
            {"$group": {"_id": "$userAgent", "count": {"$sum": 1}}}
        ]
        ua_raw = await visits.aggregate(pipeline_ua).to_list(length=1000)
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

        # user flow (from referrer path to page)
        pipeline_flow = [
            {"$match": {"referrer": {"$ne": None}}},
            {"$group": {"_id": {"from": "$referrer", "to": "$page"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 50}
        ]
        flow_raw = await visits.aggregate(pipeline_flow).to_list(length=50)
        user_flow = [
            {"from": f["_id"]["from"] or "direct", "to": f["_id"]["to"], "count": f["count"]}
            for f in flow_raw if f.get("_id") and f["_id"].get("to")
        ]

        return {
            "totalVisits": total_visits,
            "uniqueVisitors": unique_visitors,
            "newUsers": new_users,
            "returningUsers": returning_users,
            "visitsPerDay": visits_per_day,
            "userFlow": user_flow,
            "topPages": top_pages,
            "referrers": referrers,
            "devices": devices
    }


@router.get("/me", response_model=AdminResponse)
async def get_current_admin_info(current_admin=Depends(get_current_admin)):
    """
    Get current admin information
    
    Returns:
        Admin details (without password)
    """
    return AdminResponse(
        id=current_admin.id,
        username=current_admin.username,
        role=current_admin.role,
        created_at=current_admin.created_at,
        last_login=current_admin.last_login
    )


@router.get("/analytics")
async def get_analytics(current_admin=Depends(get_current_admin)):
    """
    Get analytics dashboard data
    
    Returns:
        Analytics statistics
    """
    if not is_database_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable"
        )
    
    form_collection = get_form_submissions_collection()
    visit_collection = get_visit_logs_collection()
    users_collection = get_users_collection()
    contact_collection = get_contact_submissions_collection()
    
    try:
        # Get basic counts
        total_submissions = await form_collection.count_documents({})
        total_visits = await visit_collection.count_documents({})
        unique_sessions = await users_collection.count_documents({})
        completed_diagnoses = await form_collection.count_documents({"diagnosis_completed": True})

        # Get contact submissions count
        total_contacts = await contact_collection.count_documents({}) if contact_collection is not None else 0
        
        # Calculate average age
        pipeline = [
            {"$group": {"_id": None, "avg_age": {"$avg": "$age"}}}
        ]
        avg_age_result = await form_collection.aggregate(pipeline).to_list(1)
        avg_age = avg_age_result[0]["avg_age"] if avg_age_result else None
        
        # Gender distribution
        gender_pipeline = [
            {"$group": {"_id": "$gender", "count": {"$sum": 1}}}
        ]
        gender_results = await form_collection.aggregate(gender_pipeline).to_list(10)
        gender_distribution = {item["_id"]: item["count"] for item in gender_results}
        
        # Top symptoms (flatten symptom arrays and count)
        symptom_pipeline = [
            {"$unwind": "$symptoms"},
            {"$group": {"_id": "$symptoms", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        symptom_results = await form_collection.aggregate(symptom_pipeline).to_list(10)
        top_symptoms = [
            {"symptom": item["_id"], "count": item["count"]}
            for item in symptom_results
        ]
        
        # Daily visits for last 7 days
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        daily_pipeline = [
            {"$match": {"timestamp": {"$gte": seven_days_ago}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        daily_results = await visit_collection.aggregate(daily_pipeline).to_list(7)
        daily_visits = [
            {"date": item["_id"], "visits": item["count"]}
            for item in daily_results
        ]
        
        # Recent submissions (last 10)
        recent_subs = await form_collection.find(
            {},
            {"_id": 0, "session_id": 1, "age": 1, "gender": 1, "timestamp": 1, "diagnosis_completed": 1}
        ).sort("timestamp", -1).limit(10).to_list(10)

        # Recent contact submissions (last 10)
        recent_contacts = []
        if contact_collection is not None:
            recent_contacts = await contact_collection.find(
                {},
                {"_id": 0, "name": 1, "email": 1, "organizationName": 1, "preferredModel": 1, "timestamp": 1, "form_type": 1}
        ).sort("timestamp", -1).limit(10).to_list(10)
        
        return {
            "total_submissions": total_submissions,
            "total_visits": total_visits,
            "unique_sessions": unique_sessions,
            "completed_diagnoses": completed_diagnoses,
            "total_contacts": total_contacts,
            "avg_age": round(avg_age, 1) if avg_age else None,
            "gender_distribution": gender_distribution,
            "top_symptoms": top_symptoms,
            "daily_visits": daily_visits,
            "recent_submissions": recent_subs,
            "recent_contacts": recent_contacts
        }
        
    except Exception as e:
        logger.error("Error fetching analytics: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching analytics data"
        )


@router.get("/forms")
async def get_all_forms(
    current_admin=Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    completed_only: bool = Query(False)
):
    """
    Get all form submissions (paginated)
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        completed_only: Filter for completed diagnoses only
    
    Returns:
        List of form submissions
    """
    if not is_database_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable"
        )
    
    form_collection = get_form_submissions_collection()
    
    try:
        # Build query
        query = {}
        if completed_only:
            query["diagnosis_completed"] = True
        
        # Get total count
        total = await form_collection.count_documents(query)
        
        # Get forms
        forms = await form_collection.find(
            query,
            {"_id": 0}  # Exclude MongoDB _id field
        ).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "forms": forms
        }
        
    except Exception as e:
        logger.error("Error fetching forms: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching form data"
        )


@router.get("/visits")
async def get_visit_logs(
    current_admin=Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    page_name: Optional[str] = None
):
    """
    Get visit logs
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        page_name: Filter by specific page name
    
    Returns:
        List of visit logs
    """
    if not is_database_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable"
        )
    
    visit_collection = get_visit_logs_collection()
    
    try:
        # Build query
        query = {}
        if page_name:
            query["page_name"] = page_name
        
        # Get total count
        total = await visit_collection.count_documents(query)
        
        # Get visits
        visits = await visit_collection.find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "visits": visits
        }
        
    except Exception as e:
        logger.error("Error fetching visits: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching visit logs"
        )


@router.get("/export")
async def export_data(
    current_admin=Depends(get_current_admin),
    data_type: str = Query("forms", regex="^(forms|visits)$"),
    format: str = Query("json", regex="^(json|csv)$")
):
    """
    Export data in JSON or CSV format
    
    Args:
        data_type: Type of data to export (forms or visits)
        format: Export format (json or csv)
    
    Returns:
        Exported data
    """
    if not is_database_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable"
        )
    
    try:
        if data_type == "forms":
            collection = get_form_submissions_collection()
        else:
            collection = get_visit_logs_collection()
        
        # Get all data (limit to 10,000 records for safety)
        data = await collection.find({}, {"_id": 0}).limit(10000).to_list(10000)
        
        if format == "json":
            return JSONResponse(content={"data": data})
        else:
            # CSV format (simplified, would need CSV library for better formatting)
            # For now, return JSON with instructions
            return JSONResponse(content={
                "message": "CSV export: Use frontend library to convert JSON to CSV",
                "data": data
            })
        
    except Exception as e:
        logger.error("Error exporting data: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error exporting data"
        )


@router.get("/contacts")
async def get_all_contacts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    form_type: Optional[str] = Query(None, regex="^(contact_page|pricing_page)$"),
    current_admin=Depends(get_current_admin)
):
    """
    Get all contact form submissions (paginated)

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        form_type: Filter by form type (contact_page or pricing_page)

    Returns:
        List of contact submissions
    """
    try:
        contact_collection = get_contact_submissions_collection()

        # Build query
        query = {}
        if form_type:
            query["form_type"] = form_type

        # Get total count
        total = await contact_collection.count_documents(query) if contact_collection is not None else 0

        # Get contacts
        if contact_collection is not None:
            contacts = await contact_collection.find(
                query,
                {"_id": 0}  # Exclude MongoDB _id field
            ).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
        else:
            contacts = []

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "form_type_filter": form_type,
            "contacts": contacts
        }

    except Exception as e:
        logger.error("Error fetching contacts: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching contact data: {str(e)}"
        )


@router.get("/contacts/{contact_id}")
async def get_contact_by_id(
    contact_id: str,
    current_admin=Depends(get_current_admin)
):
    """
    Get a specific contact submission by ID

    Args:
        contact_id: Contact submission ID

    Returns:
        Contact submission details
    """
    contact_collection = get_contact_submissions_collection()

    if contact_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Contact data service unavailable"
        )

    try:
        contact = await contact_collection.find_one(
            {"id": contact_id},
            {"_id": 0}  # Exclude MongoDB _id field
        )

        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact submission not found"
            )

        return contact

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching contact %s: %s", contact_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching contact data"
        )


@router.get("/report-analyzer-submissions")
async def get_report_analyzer_submissions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_admin=Depends(get_current_admin),
):
    """
    Get paginated medical report analyzer submissions for the admin dashboard.
    """
    try:
        collection = get_report_analyzer_submissions_collection()

        if is_database_available() and collection is not None:
            total = await collection.count_documents({})
            submissions = []
            async for doc in collection.find({}).sort("timestamp", -1).skip(skip).limit(limit):
                if doc.get("_id") is not None:
                    doc["_id"] = str(doc["_id"])
                submissions.append(doc)
            return {
                "total": total,
                "skip": skip,
                "limit": limit,
                "submissions": submissions,
            }

        memory_result = get_report_analyzer_submissions_from_memory(skip=skip, limit=limit)
        return memory_result

    except Exception as e:
        logger.error("Error fetching report analyzer submissions: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching report analyzer submissions",
        )


@router.delete("/report-analyzer-submissions/{submission_id}")
async def delete_report_analyzer_submission(
    submission_id: str,
    current_admin=Depends(get_current_admin),
):
    """Delete a report analyzer submission by ID."""
    try:
        collection = get_report_analyzer_submissions_collection()

        if is_database_available() and collection is not None:
            from bson import ObjectId
            from bson.errors import InvalidId

            query = {"_id": submission_id}
            try:
                query = {"_id": ObjectId(submission_id)}
            except (InvalidId, TypeError):
                query = {"_id": submission_id}

            result = await collection.delete_one(query)
            if result.deleted_count == 0:
                result = await collection.delete_one({"_id": submission_id})
            if result.deleted_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Submission not found",
                )
            return {"success": True, "message": "Submission deleted successfully"}

        deleted = delete_report_analyzer_submission_from_memory(submission_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found",
            )
        return {"success": True, "message": "Submission deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting report analyzer submission %s: %s", submission_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting submission",
        )


@router.post("/logout")
async def admin_logout(current_admin=Depends(get_current_admin)):
    """
    Admin logout (client should remove token)

    Returns:
        Success message
    """
    logger.info("Admin logout: %s", current_admin.username)

    return {"message": "Logged out successfully"}

