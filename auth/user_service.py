"""
User data-access layer for VADG authentication.

Primary store is the MongoDB `auth_users` collection (async Motor). When the
database is unavailable the module transparently falls back to an in-process
dictionary so local/dev auth flows keep working — mirroring the rest of the app,
which already degrades to in-memory storage.

Document shape (auth_users):
{
  _id, name, email(lowercased, unique), password_hash, role, is_active,
  is_verified, is_permanent_admin, phone, avatar_url,
  created_at, updated_at, last_login,
  reset_jti,                       # single-use guard for the active reset link
  sessions: [                      # active refresh tokens (hashed)
    { token_hash, expires_at, created_at, user_agent, ip }
  ]
}
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from bson import ObjectId
    _BSON = True
except Exception:  # bson ships with pymongo; guard just in case
    _BSON = False
    class ObjectId:  # type: ignore
        pass

try:
    from pymongo import ReturnDocument
except Exception:  # pragma: no cover - pymongo always ships with motor
    ReturnDocument = None

try:
    from database.connection import (
        get_database,
        is_database_available,
        is_database_configured,
        wait_if_connecting,
    )
except Exception:  # pragma: no cover - fallback for unusual import paths
    def get_database():
        return None
    def is_database_available():
        return False
    def is_database_configured():
        return False
    async def wait_if_connecting(timeout: float = 8.0):
        return None

from auth.tokens import hash_refresh_token

COLLECTION = "auth_users"

# In-memory fallback store: { id: user_dict }
_mem_users: Dict[str, Dict[str, Any]] = {}


class DatabaseUnavailable(RuntimeError):
    """Raised when the user store is configured (MONGO_URI set) but the database
    is not currently reachable. Callers should translate this into a retryable
    503 rather than treating it as "no users" — otherwise a transient DB outage
    would render as an empty admin user list (looks like every account vanished).
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _collection():
    """Return the auth_users collection, or None when DB is unavailable."""
    db = get_database()
    if db is None:
        return None
    return db[COLLECTION]


def _norm_email(email: str) -> str:
    return str(email or "").strip().lower()


def _to_object_id(user_id: str):
    if _BSON:
        try:
            return ObjectId(user_id)
        except Exception:
            return None
    return None


def _prune_sessions(sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    now = datetime.utcnow()
    return [s for s in (sessions or []) if s.get("expires_at") and s["expires_at"] > now]


# ---------------------------------------------------------------------------
# Create / read
# ---------------------------------------------------------------------------
async def create_user(
    *,
    name: str,
    email: str,
    password_hash: str,
    role: str = "user",
    is_verified: bool = False,
    is_permanent_admin: bool = False,
) -> Dict[str, Any]:
    """Insert a new user. Caller must ensure the email is not already taken."""
    now = datetime.utcnow()
    doc: Dict[str, Any] = {
        "name": name,
        "email": _norm_email(email),
        "password_hash": password_hash,
        "role": role,
        "is_active": True,
        "is_verified": is_verified,
        "is_permanent_admin": is_permanent_admin,
        "phone": None,
        "avatar_url": None,
        "created_at": now,
        "updated_at": now,
        "last_login": None,
        "reset_jti": None,
        "sessions": [],
    }
    col = _collection()
    if col is not None:
        result = await col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
    # In-memory fallback
    doc["_id"] = uuid.uuid4().hex
    _mem_users[doc["_id"]] = doc
    return doc


async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    col = _collection()
    norm = _norm_email(email)
    if col is not None:
        return await col.find_one({"email": norm})
    for u in _mem_users.values():
        if u.get("email") == norm:
            return u
    return None


async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    col = _collection()
    if col is not None:
        oid = _to_object_id(user_id)
        if oid is None:
            return None
        return await col.find_one({"_id": oid})
    return _mem_users.get(str(user_id))


async def email_exists(email: str) -> bool:
    return (await get_user_by_email(email)) is not None


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
async def update_user(user_id: str, fields: Dict[str, Any]) -> bool:
    fields = {**fields, "updated_at": datetime.utcnow()}
    col = _collection()
    if col is not None:
        oid = _to_object_id(user_id)
        if oid is None:
            return False
        res = await col.update_one({"_id": oid}, {"$set": fields})
        return res.matched_count > 0
    u = _mem_users.get(str(user_id))
    if not u:
        return False
    u.update(fields)
    return True


# ---------------------------------------------------------------------------
# Atomic balance mutations
#
# These exist because `update_user` is a blind `$set` of a caller-computed
# value. Callers that read a balance, compute `balance - 1`, then `$set` it
# race: two concurrent requests for the same user (e.g. two browser tabs each
# generating a different report) can both read the same starting balance and
# both write the same decremented result, letting a single credit / daily free
# report be spent twice. Each function below is a single conditional DB write
# for the MongoDB backend (the filter re-checks the balance against the
# document's CURRENT state, not a stale snapshot — MongoDB serializes writes
# to one document, so a second concurrent caller's filter is evaluated after
# the first caller's write lands and correctly fails to match). The in-memory
# fallback performs the check-and-mutate synchronously with no `await` between
# the read and the write, so no other asyncio task can interleave.
# ---------------------------------------------------------------------------
async def try_consume_free_report(user_id: str, today: str, limit: int) -> Optional[Dict[str, Any]]:
    """Atomically claim one daily free-report slot. Returns the updated user
    document on success, or None if today's allowance is already exhausted."""
    col = _collection()
    if col is not None:
        oid = _to_object_id(user_id)
        if oid is None:
            return None
        now = datetime.utcnow()
        doc = await col.find_one_and_update(
            {"_id": oid, "free_report_date": today, "free_report_count": {"$lt": limit}},
            {"$inc": {"free_report_count": 1, "total_reports": 1}, "$set": {"updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is not None:
            return doc
        # Not yet rolled over to today (or never used) — only matches if no
        # other concurrent caller has already rolled it over for today.
        return await col.find_one_and_update(
            {"_id": oid, "free_report_date": {"$ne": today}},
            {"$set": {"free_report_date": today, "free_report_count": 1, "updated_at": now},
             "$inc": {"total_reports": 1}},
            return_document=ReturnDocument.AFTER,
        )

    u = _mem_users.get(str(user_id))
    if not u:
        return None
    free_used = u.get("free_report_count", 0) if u.get("free_report_date") == today else 0
    if free_used >= limit:
        return None
    u["free_report_date"] = today
    u["free_report_count"] = free_used + 1
    u["total_reports"] = int(u.get("total_reports", 0) or 0) + 1
    u["updated_at"] = datetime.utcnow()
    return u


async def try_consume_credit(user_id: str) -> Optional[Dict[str, Any]]:
    """Atomically deduct one report credit. Returns the updated user document
    on success, or None if the balance is already zero."""
    col = _collection()
    if col is not None:
        oid = _to_object_id(user_id)
        if oid is None:
            return None
        return await col.find_one_and_update(
            {"_id": oid, "report_credits": {"$gte": 1}},
            {"$inc": {"report_credits": -1, "total_reports": 1}, "$set": {"updated_at": datetime.utcnow()}},
            return_document=ReturnDocument.AFTER,
        )

    u = _mem_users.get(str(user_id))
    if not u:
        return None
    credits = int(u.get("report_credits", 0) or 0)
    if credits < 1:
        return None
    u["report_credits"] = credits - 1
    u["total_reports"] = int(u.get("total_reports", 0) or 0) + 1
    u["updated_at"] = datetime.utcnow()
    return u


async def add_credits_atomic(user_id: str, credits: int) -> Optional[Dict[str, Any]]:
    """Atomically add (non-negative) credits, e.g. after a purchase. Returns
    the updated user document, or None if the user doesn't exist."""
    col = _collection()
    if col is not None:
        oid = _to_object_id(user_id)
        if oid is None:
            return None
        return await col.find_one_and_update(
            {"_id": oid},
            {"$inc": {"report_credits": int(credits)}, "$set": {"updated_at": datetime.utcnow()}},
            return_document=ReturnDocument.AFTER,
        )

    u = _mem_users.get(str(user_id))
    if not u:
        return None
    u["report_credits"] = int(u.get("report_credits", 0) or 0) + int(credits)
    u["updated_at"] = datetime.utcnow()
    return u


async def adjust_credits_atomic(user_id: str, delta: int) -> Optional[Dict[str, Any]]:
    """Atomically add/subtract credits (admin adjustment), floored at 0.
    Uses an aggregation-pipeline update so the floor is applied in the same
    atomic write as the increment (no separate read-then-clamp race)."""
    col = _collection()
    if col is not None:
        oid = _to_object_id(user_id)
        if oid is None:
            return None
        return await col.find_one_and_update(
            {"_id": oid},
            [{"$set": {
                "report_credits": {"$max": [0, {"$add": [{"$ifNull": ["$report_credits", 0]}, int(delta)]}]},
                "updated_at": datetime.utcnow(),
            }}],
            return_document=ReturnDocument.AFTER,
        )

    u = _mem_users.get(str(user_id))
    if not u:
        return None
    u["report_credits"] = max(0, int(u.get("report_credits", 0) or 0) + int(delta))
    u["updated_at"] = datetime.utcnow()
    return u


async def set_last_login(user_id: str) -> None:
    await update_user(user_id, {"last_login": datetime.utcnow()})


async def mark_verified(user_id: str) -> bool:
    return await update_user(user_id, {"is_verified": True})


async def set_password(user_id: str, password_hash: str) -> bool:
    """Set a new password hash and revoke all sessions + any pending reset."""
    col = _collection()
    fields = {
        "password_hash": password_hash,
        "reset_jti": None,
        "sessions": [],
        "updated_at": datetime.utcnow(),
    }
    if col is not None:
        oid = _to_object_id(user_id)
        if oid is None:
            return False
        res = await col.update_one({"_id": oid}, {"$set": fields})
        return res.matched_count > 0
    u = _mem_users.get(str(user_id))
    if not u:
        return False
    u.update(fields)
    return True


# ---------------------------------------------------------------------------
# Reset-token single-use guard
# ---------------------------------------------------------------------------
async def set_reset_jti(user_id: str, jti: str) -> bool:
    return await update_user(user_id, {"reset_jti": jti})


async def consume_reset_jti(user_id: str, jti: str) -> bool:
    """Return True only if `jti` matches the stored value (then it's cleared)."""
    user = await get_user_by_id(user_id)
    if not user or user.get("reset_jti") != jti:
        return False
    await update_user(user_id, {"reset_jti": None})
    return True


# ---------------------------------------------------------------------------
# Refresh-token / session management
# ---------------------------------------------------------------------------
async def add_session(
    user_id: str, refresh_token: str, expires_at: datetime,
    user_agent: Optional[str] = None, ip: Optional[str] = None,
) -> bool:
    """Store a hashed refresh token as an active session (prunes expired ones)."""
    user = await get_user_by_id(user_id)
    if not user:
        return False
    sessions = _prune_sessions(user.get("sessions", []))
    sessions.append({
        "token_hash": hash_refresh_token(refresh_token),
        "expires_at": expires_at,
        "created_at": datetime.utcnow(),
        "user_agent": (user_agent or "")[:300],
        "ip": ip,
    })
    # Cap concurrent sessions to a sane maximum (keep most recent 10).
    sessions = sessions[-10:]
    return await update_user(user_id, {"sessions": sessions})


async def verify_session(user_id: str, refresh_token: str) -> bool:
    """Whether the given refresh token corresponds to an active session."""
    user = await get_user_by_id(user_id)
    if not user:
        return False
    token_hash = hash_refresh_token(refresh_token)
    for s in _prune_sessions(user.get("sessions", [])):
        if s.get("token_hash") == token_hash:
            return True
    return False


async def rotate_session(user_id: str, old_token: str, new_token: str, expires_at: datetime) -> bool:
    """Replace an existing refresh token with a rotated one (refresh flow)."""
    user = await get_user_by_id(user_id)
    if not user:
        return False
    old_hash = hash_refresh_token(old_token)
    sessions = _prune_sessions(user.get("sessions", []))
    meta = next((s for s in sessions if s.get("token_hash") == old_hash), None)
    sessions = [s for s in sessions if s.get("token_hash") != old_hash]
    sessions.append({
        "token_hash": hash_refresh_token(new_token),
        "expires_at": expires_at,
        "created_at": datetime.utcnow(),
        "user_agent": (meta or {}).get("user_agent", ""),
        "ip": (meta or {}).get("ip"),
    })
    return await update_user(user_id, {"sessions": sessions[-10:]})


async def revoke_session(user_id: str, refresh_token: str) -> bool:
    user = await get_user_by_id(user_id)
    if not user:
        return False
    token_hash = hash_refresh_token(refresh_token)
    sessions = [s for s in _prune_sessions(user.get("sessions", [])) if s.get("token_hash") != token_hash]
    return await update_user(user_id, {"sessions": sessions})


async def revoke_all_sessions(user_id: str) -> bool:
    return await update_user(user_id, {"sessions": []})


# ---------------------------------------------------------------------------
# Admin listing
# ---------------------------------------------------------------------------
def _build_search_query(search: Optional[str]) -> Dict[str, Any]:
    """Case-insensitive name/email search filter. The user input is escaped so
    regex metacharacters (`.`, `*`, `(`, …) are matched literally rather than
    interpreted — both a correctness fix (a search for "a.b" shouldn't match
    "axb") and a guard against a pathological/ReDoS-y pattern reaching MongoDB."""
    if not search or not search.strip():
        return {}
    s = re.escape(search.strip())
    return {"$or": [
        {"email": {"$regex": s, "$options": "i"}},
        {"name": {"$regex": s, "$options": "i"}},
    ]}


async def list_users(
    page: int = 1, limit: int = 20, search: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Return (users, total) for the admin dashboard, newest first.

    Raises DatabaseUnavailable when a database is configured but currently
    unreachable, so the caller can report a retryable error instead of an
    empty list.
    """
    page = max(1, page)
    limit = max(1, min(limit, 100))
    skip = (page - 1) * limit

    # Ride out the cold-start window: on Cloud Run the app serves traffic before
    # the background MongoDB connect finishes, so the first admin request could
    # otherwise fall through to the (empty) in-memory store and show "no users".
    await wait_if_connecting()

    col = _collection()
    query = _build_search_query(search)

    if col is not None:
        total = await col.count_documents(query)
        cursor = col.find(query).sort("created_at", -1).skip(skip).limit(limit)
        users = await cursor.to_list(length=limit)
        return users, total

    # No live collection. A configured-but-unreachable DB is an outage, not an
    # empty user base — surface it rather than silently returning in-memory data.
    if is_database_configured():
        raise DatabaseUnavailable("User store is temporarily unavailable")

    # Genuine no-database dev mode → in-memory fallback.
    items = list(_mem_users.values())
    if search and search.strip():
        s = search.strip().lower()
        items = [u for u in items if s in u.get("email", "").lower() or s in u.get("name", "").lower()]
    items.sort(key=lambda u: u.get("created_at") or datetime.min, reverse=True)
    total = len(items)
    return items[skip:skip + limit], total


async def count_users(*, with_credits: bool = False) -> int:
    """Count users (optionally only those holding report credits).

    A single indexed count query — far cheaper than paging a sample of documents
    into the app just to tally them. Raises DatabaseUnavailable on a configured
    but unreachable database.
    """
    await wait_if_connecting()
    col = _collection()
    if col is not None:
        query = {"report_credits": {"$gt": 0}} if with_credits else {}
        return await col.count_documents(query)

    if is_database_configured():
        raise DatabaseUnavailable("User store is temporarily unavailable")

    if with_credits:
        return sum(1 for u in _mem_users.values() if int(u.get("report_credits", 0) or 0) > 0)
    return len(_mem_users)
