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
    from database.connection import get_database, is_database_available
except Exception:  # pragma: no cover - fallback for unusual import paths
    def get_database():
        return None
    def is_database_available():
        return False

from auth.tokens import hash_refresh_token

COLLECTION = "auth_users"

# In-memory fallback store: { id: user_dict }
_mem_users: Dict[str, Dict[str, Any]] = {}


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
async def list_users(
    page: int = 1, limit: int = 20, search: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Return (users, total) for the admin dashboard, newest first."""
    page = max(1, page)
    limit = max(1, min(limit, 100))
    skip = (page - 1) * limit
    col = _collection()

    query: Dict[str, Any] = {}
    if search:
        s = search.strip()
        query = {"$or": [
            {"email": {"$regex": s, "$options": "i"}},
            {"name": {"$regex": s, "$options": "i"}},
        ]}

    if col is not None:
        total = await col.count_documents(query)
        cursor = col.find(query).sort("created_at", -1).skip(skip).limit(limit)
        users = await cursor.to_list(length=limit)
        return users, total

    # In-memory fallback
    items = list(_mem_users.values())
    if search:
        s = search.strip().lower()
        items = [u for u in items if s in u.get("email", "").lower() or s in u.get("name", "").lower()]
    items.sort(key=lambda u: u.get("created_at") or datetime.min, reverse=True)
    total = len(items)
    return items[skip:skip + limit], total
