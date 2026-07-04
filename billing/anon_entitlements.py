"""
Anonymous (pre-signup) free-report entitlement.

Every new anonymous visitor gets exactly ONE free diagnosis report, tracked by
a client-generated device id (the "X-Anon-Id" header, persisted in the
browser's localStorage). Once consumed, that device id must sign in or
register to start another diagnosis — enforced at both the start of the flow
(/symptom) and at generation time (/generate_report), so a second diagnosis
never gets past the patient-details step, and the first one is never
interrupted once started.

This is a soft, best-effort gate: an anonymous id has no cryptographic
identity to bind to, so clearing localStorage resets it — the same tradeoff
every consumer free-trial-per-browser gate makes. It only governs anonymous
visitors; logged-in users are governed by billing/entitlements.py, which is
unaffected by this module.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from database.connection import get_database
except Exception:
    def get_database():
        return None

COLLECTION = "anon_report_usage"

# In-memory fallback keyed by anon_id (mirrors billing/entitlements.py's pattern).
_mem_usage: Dict[str, Dict[str, Any]] = {}


def _collection():
    db = get_database()
    return db[COLLECTION] if db is not None else None


async def has_used_free_report(anon_id: Optional[str]) -> bool:
    """True if this device has already consumed its free report (or has no id
    at all — a missing id is treated as ineligible, so the frontend forgetting
    to send it fails closed rather than granting unlimited free reports)."""
    if not anon_id:
        return True
    col = _collection()
    if col is not None:
        doc = await col.find_one({"anon_id": anon_id})
        return bool(doc and doc.get("used"))
    doc = _mem_usage.get(anon_id)
    return bool(doc and doc.get("used"))


async def try_consume(anon_id: Optional[str], session_id: str) -> bool:
    """
    Atomically claim this device's single free report for `session_id`.

    Returns True if the report is allowed (first use, or an idempotent
    re-fetch of the SAME session already unlocked), False if this device
    already used its free report on a different diagnosis.
    """
    if not anon_id or not session_id:
        return False

    col = _collection()
    now = datetime.utcnow()

    if col is not None:
        existing = await col.find_one({"anon_id": anon_id})
        if existing:
            return existing.get("session_id") == session_id
        try:
            # $setOnInsert + upsert is atomic: under a race, exactly one caller
            # inserts and the other sees matched_count == 1 (already existed).
            result = await col.update_one(
                {"anon_id": anon_id},
                {"$setOnInsert": {
                    "anon_id": anon_id,
                    "used": True,
                    "session_id": session_id,
                    "used_at": now,
                }},
                upsert=True,
            )
            return result.upserted_id is not None
        except Exception as e:
            logger.error("anon_entitlements: try_consume failed: %s", e)
            return False

    existing = _mem_usage.get(anon_id)
    if existing:
        return existing.get("session_id") == session_id
    _mem_usage[anon_id] = {
        "anon_id": anon_id, "used": True, "session_id": session_id, "used_at": now,
    }
    return True
