"""
Session Tracking Utility
Manages session creation, heartbeat, and lifecycle
"""

import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Request

from .models import SessionDocument, DeviceType
from .device_detection import parse_user_agent
from .ip_utils import get_client_ip, hash_ip
from .visitor_dedup import get_or_create_visitor_id
from .bot_filter import should_filter_request
from database.connection import get_database, is_database_available


# In-memory session store for fallback
_in_memory_sessions: Dict[str, Dict[str, Any]] = {}


async def create_session(
    request: Request,
    landing_page: str = "/",
    referrer: Optional[str] = None,
    user_id: Optional[str] = None
) -> SessionDocument:
    """
    Create a new session.
    
    Args:
        request: FastAPI Request object
        landing_page: First page visited
        referrer: Referrer URL
        user_id: Optional authenticated user ID
        
    Returns:
        SessionDocument
    """
    # Extract request information
    user_agent = request.headers.get("user-agent", "")
    client_ip = get_client_ip(request)
    ip_hash = hash_ip(client_ip)
    
    # Filter bots
    if should_filter_request(user_agent, client_ip):
        # Still create session but mark it somehow if needed
        pass
    
    # Parse user agent
    device_info = parse_user_agent(user_agent)
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    
    # Get or create visitor ID
    visitor_id, is_unique = await get_or_create_visitor_id(ip_hash, user_agent, session_id)
    
    # Create session document
    session = SessionDocument(
        session_id=session_id,
        visitor_id=visitor_id,
        started_at=datetime.utcnow(),
        last_heartbeat=datetime.utcnow(),
        is_active=True,
        ip_hash=ip_hash,
        user_agent=user_agent,
        device_type=device_info['device_type'],
        browser=device_info['browser'],
        browser_version=device_info['browser_version'],
        os=device_info['os'],
        os_version=device_info['os_version'],
        user_id=user_id,
        referrer=referrer,
        landing_page=landing_page,
        page_count=1,
        event_count=0
    )
    
    # Store session
    await store_session(session)
    
    return session


async def store_session(session: SessionDocument) -> None:
    """
    Store session in database or in-memory fallback.
    
    Args:
        session: SessionDocument to store
    """
    if is_database_available():
        db = get_database()
        if db is not None:
            sessions_collection = db.sessions
            session_dict = session.dict()
            await sessions_collection.insert_one(session_dict)
            return
    
    # Fallback to in-memory storage
    _in_memory_sessions[session.session_id] = session.dict()


async def get_session(session_id: str) -> Optional[SessionDocument]:
    """
    Get session by ID.
    
    Args:
        session_id: Session ID
        
    Returns:
        SessionDocument or None
    """
    if is_database_available():
        db = get_database()
        if db is not None:
            sessions_collection = db.sessions
            session_dict = await sessions_collection.find_one({"session_id": session_id})
            if session_dict:
                return SessionDocument(**session_dict)
    
    # Check in-memory
    if session_id in _in_memory_sessions:
        return SessionDocument(**_in_memory_sessions[session_id])
    
    return None


async def update_session_heartbeat(session_id: str) -> bool:
    """
    Update session heartbeat timestamp.
    
    Args:
        session_id: Session ID
        
    Returns:
        True if updated, False if session not found
    """
    now = datetime.utcnow()
    
    if is_database_available():
        db = get_database()
        if db is not None:
            sessions_collection = db.sessions
            result = await sessions_collection.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "last_heartbeat": now,
                        "is_active": True
                    }
                }
            )
            return result.modified_count > 0
    
    # Update in-memory
    if session_id in _in_memory_sessions:
        _in_memory_sessions[session_id]["last_heartbeat"] = now
        _in_memory_sessions[session_id]["is_active"] = True
        return True
    
    return False


async def increment_session_page_count(session_id: str) -> None:
    """
    Increment page count for session.
    
    Args:
        session_id: Session ID
    """
    if is_database_available():
        db = get_database()
        if db is not None:
            sessions_collection = db.sessions
            await sessions_collection.update_one(
                {"session_id": session_id},
                {"$inc": {"page_count": 1}}
            )
            return
    
    # Update in-memory
    if session_id in _in_memory_sessions:
        _in_memory_sessions[session_id]["page_count"] = \
            _in_memory_sessions[session_id].get("page_count", 0) + 1


async def increment_session_event_count(session_id: str) -> None:
    """
    Increment event count for session.
    
    Args:
        session_id: Session ID
    """
    if is_database_available():
        db = get_database()
        if db is not None:
            sessions_collection = db.sessions
            await sessions_collection.update_one(
                {"session_id": session_id},
                {"$inc": {"event_count": 1}}
            )
            return
    
    # Update in-memory
    if session_id in _in_memory_sessions:
        _in_memory_sessions[session_id]["event_count"] = \
            _in_memory_sessions[session_id].get("event_count", 0) + 1


async def end_session(session_id: str) -> None:
    """
    End a session by setting ended_at and is_active=False.
    
    Args:
        session_id: Session ID
    """
    now = datetime.utcnow()
    
    if is_database_available():
        db = get_database()
        if db is not None:
            sessions_collection = db.sessions
            # Get session to calculate duration
            session = await sessions_collection.find_one({"session_id": session_id})
            if session:
                started_at = session.get("started_at", now)
                if isinstance(started_at, datetime):
                    duration = int((now - started_at).total_seconds())
                else:
                    duration = None
                
                await sessions_collection.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "ended_at": now,
                            "is_active": False,
                            "duration_seconds": duration
                        }
                    }
                )
            return
    
    # Update in-memory
    if session_id in _in_memory_sessions:
        session = _in_memory_sessions[session_id]
        started_at = session.get("started_at", now)
        if isinstance(started_at, datetime):
            duration = int((now - started_at).total_seconds())
        else:
            duration = None
        
        _in_memory_sessions[session_id]["ended_at"] = now
        _in_memory_sessions[session_id]["is_active"] = False
        _in_memory_sessions[session_id]["duration_seconds"] = duration


async def cleanup_inactive_sessions() -> None:
    """
    Clean up sessions that haven't had a heartbeat in 30 minutes.
    This should be called periodically (e.g., every 5 minutes).
    """
    thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
    
    if is_database_available():
        db = get_database()
        if db is not None:
            sessions_collection = db.sessions
            await sessions_collection.update_many(
                {
                    "is_active": True,
                    "last_heartbeat": {"$lt": thirty_minutes_ago}
                },
                {
                    "$set": {
                        "is_active": False,
                        "ended_at": datetime.utcnow()
                    }
                }
            )
            return
    
    # Cleanup in-memory
    for session_id, session in list(_in_memory_sessions.items()):
        last_heartbeat = session.get("last_heartbeat")
        if isinstance(last_heartbeat, datetime) and last_heartbeat < thirty_minutes_ago:
            session["is_active"] = False
            session["ended_at"] = datetime.utcnow()

