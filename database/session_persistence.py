"""
Persist diagnosis sessions to MongoDB.

Cloud Run runs multiple instances and restarts them freely, so the in-memory
session_store alone loses sessions between requests (the request that created
the session may land on a different instance than the one fetching the symptom
card or opening the follow-up websocket). Every session write is mirrored to
MongoDB, and any session_store miss falls back to a MongoDB restore before
returning 404. If MongoDB is unavailable the app degrades to memory-only,
matching the previous behavior.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

from database.connection import get_database, wait_if_connecting

logger = logging.getLogger(__name__)

COLLECTION_NAME = "diagnosis_sessions"

# Sessions auto-expire in MongoDB after this many seconds of inactivity.
# Kept above SESSION_TIMEOUT (in-memory TTL) so MongoDB is never the stricter store.
PERSISTED_SESSION_TTL_SECONDS = 86400

_indexes_created = False


def _collection():
    db = get_database()
    if db is None:
        return None
    return db[COLLECTION_NAME]


async def ensure_indexes() -> None:
    """Create session_id lookup + TTL indexes (idempotent, called lazily)."""
    global _indexes_created
    if _indexes_created:
        return
    col = _collection()
    if col is None:
        return
    try:
        await col.create_index("session_id", unique=True)
        await col.create_index(
            "updated_at", expireAfterSeconds=PERSISTED_SESSION_TTL_SECONDS
        )
        _indexes_created = True
    except Exception as exc:
        logger.warning("Could not create diagnosis_sessions indexes: %s", exc)


def _json_safe(value):
    """Deep-copy a session into BSON-storable primitives."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


async def save_session(session_id: str, session: dict) -> None:
    """Upsert a session snapshot to MongoDB. Failures are logged, never raised.

    A freshly cold-started Cloud Run instance starts serving traffic before
    its background MongoDB connect finishes (see app.py's _background_init).
    A session created during that window would otherwise only ever exist in
    THIS instance's in-memory session_store — Cloud Run doesn't guarantee a
    later request for the same session_id (a symptom-card fetch, the
    follow-up websocket) lands on the same instance, so it would come back
    as a 404 for a session the user just created. Wait out that specific
    window (bounded) before giving up, rather than silently dropping the
    write the moment `col is None`.
    """
    col = _collection()
    if col is None:
        await wait_if_connecting()
        col = _collection()
    if col is None or not isinstance(session, dict):
        return
    try:
        await ensure_indexes()
        doc = _json_safe(session)
        doc["session_id"] = session_id
        doc["updated_at"] = datetime.utcnow()
        await col.replace_one({"session_id": session_id}, doc, upsert=True)
    except Exception as exc:
        logger.warning("Failed to persist session %s to MongoDB: %s", session_id, exc)


async def load_session(session_id: str) -> Optional[dict]:
    """Fetch a persisted session, or None if absent/unavailable.

    Same cold-start race as save_session: if THIS instance is the one
    handling the restore attempt and its own MongoDB connection is still
    coming up, wait that out rather than reporting "not found" for a session
    that may well be sitting in MongoDB already.
    """
    col = _collection()
    if col is None:
        await wait_if_connecting()
        col = _collection()
    if col is None:
        return None
    try:
        doc = await col.find_one(
            {"session_id": session_id},
            {"_id": 0, "session_id": 0, "updated_at": 0},
        )
        return doc if isinstance(doc, dict) else None
    except Exception as exc:
        logger.warning("Failed to load session %s from MongoDB: %s", session_id, exc)
        return None


async def get_or_restore_session(
    session_id: str, session_store: Dict[str, dict]
) -> Optional[dict]:
    """Return the in-memory session; on a miss, restore it from MongoDB."""
    session = session_store.get(session_id)
    if session is not None:
        return session
    session = await load_session(session_id)
    if session is not None:
        session["last_activity"] = datetime.utcnow().isoformat()
        session_store[session_id] = session
        logger.info("Restored session %s from MongoDB", session_id)
    return session


async def delete_session(session_id: str) -> None:
    """Remove a persisted session (best-effort)."""
    col = _collection()
    if col is None:
        return
    try:
        await col.delete_one({"session_id": session_id})
    except Exception as exc:
        logger.warning("Failed to delete persisted session %s: %s", session_id, exc)
