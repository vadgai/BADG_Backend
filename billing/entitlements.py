"""
Report entitlements & usage — the enforcement core.

Rules:
  - Admins get unlimited reports.
  - Each registered user gets FREE_REPORTS_PER_DAY free reports per calendar day.
  - Beyond the free allowance, each report consumes 1 non-expiring credit.
  - Consumption is IDEMPOTENT per session_id: a diagnosis is charged once when
    its report is first generated; re-fetching/exporting/translating the same
    session's report is free (report_usage is keyed by session_id).

Usage is logged to the report_usage collection for admin activity monitoring.
Entitlement state lives on the auth_users document:
  report_credits, free_report_date, free_report_count, total_reports, subscription.
"""

import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from database.connection import get_database
except Exception:
    def get_database():
        return None

from auth import user_service

def _safe_int(name: str, default: int) -> int:
    """Parse an int env var, falling back to default on a malformed value.
    (A bad env var must never crash module import / container startup.)"""
    try:
        return int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        logger.warning("Invalid %s env value; using default %s", name, default)
        return default


FREE_REPORTS_PER_DAY = _safe_int("FREE_REPORTS_PER_DAY", 1)
PAY_PER_REPORT_INR = _safe_int("PAY_PER_REPORT_PRICE_INR", 29)

USAGE_COLLECTION = "report_usage"

# In-memory fallback: list of usage records.
_mem_usage: List[Dict[str, Any]] = []


def _usage_collection():
    db = get_database()
    return db[USAGE_COLLECTION] if db is not None else None


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Usage records
# ---------------------------------------------------------------------------
async def _usage_by_session(session_id: str) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    col = _usage_collection()
    if col is not None:
        return await col.find_one({"session_id": session_id})
    for r in _mem_usage:
        if r.get("session_id") == session_id:
            return r
    return None


async def _record_usage(user: Dict[str, Any], session_id: str, source: str, disease: Optional[str]) -> bool:
    """
    Atomically claim `session_id` for a usage record.

    Backed by a unique index on report_usage.session_id, so under a race
    (double-click, retry, two tabs hitting /generate_report for the same
    session at once) exactly one caller's upsert actually inserts — every
    other caller sees the doc already exists and gets False back. Callers
    must only decrement a balance when this returns True, which is what makes
    "consume after success" safe against duplicate deductions.
    """
    doc = {
        "user_id": str(user["_id"]),
        "user_email": user.get("email"),
        "session_id": session_id,
        "source": source,
        "disease": disease,
        "created_at": datetime.utcnow(),
    }
    col = _usage_collection()
    if col is not None:
        try:
            result = await col.update_one({"session_id": session_id}, {"$setOnInsert": doc}, upsert=True)
            return result.upserted_id is not None
        except Exception as e:
            # Duplicate-key (lost the race) or any other DB error — fail safe
            # by treating it as "not claimed" rather than risk double-charging.
            logger.error("Failed to record report usage: %s", e)
            return False
    if any(r.get("session_id") == session_id for r in _mem_usage):
        return False
    doc["_id"] = uuid.uuid4().hex
    _mem_usage.append(doc)
    return True


async def enrich_usage(
    session_id: str, disease: Optional[str] = None,
    symptoms: Optional[List[str]] = None, summary: Optional[str] = None,
    age: Optional[Any] = None, gender: Optional[str] = None,
    diseases: Optional[List[str]] = None,
) -> None:
    """
    Attach the diagnosis outcome (likely disease, symptoms, short summary, and
    basic patient info) to an existing report_usage record so the user can review
    it in their profile. Best-effort — never raises.
    """
    updates: Dict[str, Any] = {}
    if disease:
        updates["disease"] = str(disease)[:160]
    if diseases:
        clean_d = []
        seen_d = set()
        for d in diseases:
            d = str(d).strip()
            if d and d.lower() not in seen_d:
                seen_d.add(d.lower())
                clean_d.append(d)
            if len(clean_d) >= 5:
                break
        if clean_d:
            updates["diseases"] = clean_d
    if symptoms:
        # Store a capped, de-duplicated list of symptom strings.
        clean = []
        seen = set()
        for s in symptoms:
            s = str(s).strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                clean.append(s)
            if len(clean) >= 15:
                break
        if clean:
            updates["symptoms"] = clean
    if summary:
        updates["summary"] = str(summary)[:600]
    if age not in (None, ""):
        updates["age"] = age
    if gender:
        updates["gender"] = str(gender)[:20]
    if not updates:
        return
    try:
        col = _usage_collection()
        if col is not None:
            await col.update_one({"session_id": session_id}, {"$set": updates})
        else:
            for r in _mem_usage:
                if r.get("session_id") == session_id:
                    r.update(updates)
                    break
    except Exception as e:
        logger.error("Failed to enrich report usage: %s", e)


async def list_user_reports(user_id: str, page: int = 1, limit: int = 10) -> Tuple[List[Dict[str, Any]], int]:
    """Return (reports, total) for a user's own history, newest first."""
    page = max(1, page)
    limit = max(1, min(limit, 50))
    skip = (page - 1) * limit
    col = _usage_collection()
    query = {"user_id": str(user_id)}
    if col is not None:
        total = await col.count_documents(query)
        cursor = col.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        return items, total
    items = [r for r in _mem_usage if str(r.get("user_id")) == str(user_id)]
    items.sort(key=lambda r: r.get("created_at") or datetime.min, reverse=True)
    return items[skip:skip + limit], len(items)


async def user_report_summary(user_id: str) -> Dict[str, Any]:
    """Small aggregate for the profile header: totals + most common disease."""
    items, total = await list_user_reports(user_id, page=1, limit=50)
    disease_counts: Dict[str, int] = {}
    for r in items:
        d = (r.get("disease") or "").strip()
        if d:
            disease_counts[d] = disease_counts.get(d, 0) + 1
    top_disease = max(disease_counts, key=disease_counts.get) if disease_counts else None
    return {"total": total, "top_disease": top_disease, "distinct_conditions": len(disease_counts)}


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------
def get_balance(user: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the user's current entitlement snapshot (no DB writes)."""
    is_admin = user.get("role") == "admin"
    today = _today()
    free_used = user.get("free_report_count", 0) if user.get("free_report_date") == today else 0
    free_available = max(0, FREE_REPORTS_PER_DAY - free_used)
    credits = int(user.get("report_credits", 0) or 0)
    return {
        "unlimited": is_admin,
        "free_per_day": FREE_REPORTS_PER_DAY,
        "free_used_today": free_used,
        "free_available_today": free_available,
        "credits": credits,
        "reports_available": is_admin or free_available > 0 or credits > 0,
        "price_per_report_inr": PAY_PER_REPORT_INR,
        "total_reports_used": int(user.get("total_reports", 0) or 0),
        "plan": user.get("subscription"),
    }


# ---------------------------------------------------------------------------
# Consume (enforcement)
# ---------------------------------------------------------------------------
async def check_and_consume(
    user: Dict[str, Any], session_id: str, disease: Optional[str] = None
) -> Dict[str, Any]:
    """
    Attempt to unlock a report for `session_id` — call this ONLY after the
    report has actually been generated, never before, so a failed/interrupted
    generation never costs a credit.

    Returns {"allowed": bool, "source": str, "reason": str, "balance": {...}}.
    Idempotent and race-safe: an already-unlocked session is always allowed
    without charge, and concurrent calls for the same session_id (double
    submit, retry, two tabs) can only ever decrement the balance once — the
    balance is only touched after this session_id is atomically claimed via
    _record_usage, which is backed by a unique index.
    """
    uid = str(user["_id"])

    existing = await _usage_by_session(session_id)
    if existing:
        return {"allowed": True, "source": existing.get("source", "credit"), "already_unlocked": True,
                "balance": get_balance(user)}

    # Admins: unlimited (still logged for activity monitoring). No balance to
    # protect, so a lost claim race here is harmless — just skip the duplicate.
    if user.get("role") == "admin":
        await _record_usage(user, session_id, "admin", disease)
        return {"allowed": True, "source": "admin", "balance": get_balance(user)}

    today = _today()
    free_used = user.get("free_report_count", 0) if user.get("free_report_date") == today else 0
    total = int(user.get("total_reports", 0) or 0)

    # 1) Daily free allowance
    if free_used < FREE_REPORTS_PER_DAY:
        # Claim the session BEFORE touching the balance — only the winner of
        # this atomic insert may decrement it.
        if not await _record_usage(user, session_id, "free", disease):
            return {"allowed": True, "already_unlocked": True, "balance": get_balance(user)}
        await user_service.update_user(uid, {
            "free_report_date": today,
            "free_report_count": free_used + 1,
            "total_reports": total + 1,
        })
        user["free_report_date"] = today
        user["free_report_count"] = free_used + 1
        user["total_reports"] = total + 1
        return {"allowed": True, "source": "free", "balance": get_balance(user)}

    # 2) Paid credits
    credits = int(user.get("report_credits", 0) or 0)
    if credits > 0:
        if not await _record_usage(user, session_id, "credit", disease):
            return {"allowed": True, "already_unlocked": True, "balance": get_balance(user)}
        await user_service.update_user(uid, {
            "report_credits": credits - 1,
            "total_reports": total + 1,
        })
        user["report_credits"] = credits - 1
        user["total_reports"] = total + 1
        return {"allowed": True, "source": "credit", "balance": get_balance(user)}

    # 3) Out of entitlements
    return {
        "allowed": False,
        "reason": "no_reports_remaining",
        "balance": get_balance(user),
    }


# ---------------------------------------------------------------------------
# Grant credits (after a successful purchase or an admin adjustment)
# ---------------------------------------------------------------------------
async def grant_credits(
    user_id: str, credits: int, *, plan_code: Optional[str] = None,
    plan_name: Optional[str] = None, set_subscription: bool = True,
) -> Optional[int]:
    """Add credits to a user; optionally record the plan as their current pack."""
    user = await user_service.get_user_by_id(user_id)
    if not user:
        return None
    new_balance = int(user.get("report_credits", 0) or 0) + int(credits)
    updates: Dict[str, Any] = {"report_credits": new_balance}
    if set_subscription and plan_name:
        updates["subscription"] = {
            "plan_code": plan_code,
            "plan_name": plan_name,
            "credits": credits,
            "purchased_at": datetime.utcnow(),
        }
        updates["credits_purchased_total"] = int(user.get("credits_purchased_total", 0) or 0) + int(max(0, credits))
    await user_service.update_user(user_id, updates)
    return new_balance


# ---------------------------------------------------------------------------
# Admin analytics
# ---------------------------------------------------------------------------
async def recent_activity(limit: int = 50) -> List[Dict[str, Any]]:
    col = _usage_collection()
    if col is not None:
        cursor = col.find({}).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)
    return sorted(_mem_usage, key=lambda r: r.get("created_at") or datetime.min, reverse=True)[:limit]


async def usage_stats(days: int = 14) -> Dict[str, Any]:
    """Aggregate report-usage stats for the admin dashboard."""
    col = _usage_collection()
    today = _today()
    since = datetime.utcnow() - timedelta(days=days)

    if col is not None:
        total = await col.count_documents({})
        reports_today = await col.count_documents({
            "created_at": {"$gte": datetime.strptime(today, "%Y-%m-%d")}
        })
        by_source_cursor = col.aggregate([
            {"$group": {"_id": "$source", "count": {"$sum": 1}}}
        ])
        by_source = {d["_id"]: d["count"] async for d in by_source_cursor}
        daily_cursor = col.aggregate([
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
        ])
        daily = [{"date": d["_id"], "count": d["count"]} async for d in daily_cursor]
        return {"total": total, "today": reports_today, "by_source": by_source, "daily": daily}

    # In-memory fallback
    total = len(_mem_usage)
    reports_today = sum(1 for r in _mem_usage if (r.get("created_at") or datetime.min).strftime("%Y-%m-%d") == today)
    by_source: Dict[str, int] = {}
    for r in _mem_usage:
        by_source[r.get("source", "?")] = by_source.get(r.get("source", "?"), 0) + 1
    daily_map: Dict[str, int] = {}
    for r in _mem_usage:
        d = (r.get("created_at") or datetime.min).strftime("%Y-%m-%d")
        daily_map[d] = daily_map.get(d, 0) + 1
    daily = [{"date": k, "count": v} for k, v in sorted(daily_map.items())]
    return {"total": total, "today": reports_today, "by_source": by_source, "daily": daily}
