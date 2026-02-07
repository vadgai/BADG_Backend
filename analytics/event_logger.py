"""
Event Logging Utility
Handles logging of analytics events
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import Request

from .models import EventDocument, EventType
from .ip_utils import get_client_ip, hash_ip
from .session_tracker import get_session, increment_session_event_count
from database.connection import get_database, is_database_available


# In-memory event store for fallback
_in_memory_events: List[Dict[str, Any]] = []


async def log_event(
    event_name: EventType,
    session_id: Optional[str] = None,
    request: Optional[Request] = None,
    metadata: Optional[Dict[str, Any]] = None,
    page: Optional[str] = None,
    user_id: Optional[str] = None
) -> EventDocument:
    """
    Log an analytics event.
    
    Args:
        event_name: Event type
        session_id: Optional session ID
        request: Optional FastAPI Request object
        metadata: Optional event metadata
        page: Optional page path
        user_id: Optional authenticated user ID
        
    Returns:
        EventDocument
    """
    # Generate event ID
    event_id = str(uuid.uuid4())
    
    # Get session if available
    visitor_id = None
    ip_hash = None
    
    if session_id:
        session = await get_session(session_id)
        if session:
            visitor_id = session.visitor_id
            if not user_id and session.user_id:
                user_id = session.user_id
    
    # Get IP hash from request if available
    if request:
        client_ip = get_client_ip(request)
        ip_hash = hash_ip(client_ip)
        if not page:
            page = request.url.path
    
    # Create event document
    event = EventDocument(
        event_id=event_id,
        session_id=session_id or "",
        visitor_id=visitor_id,
        user_id=user_id,
        timestamp=datetime.utcnow(),
        event_name=event_name,
        metadata=metadata or {},
        page=page,
        ip_hash=ip_hash
    )
    
    # Store event
    await store_event(event)
    
    # Increment session event count
    if session_id:
        await increment_session_event_count(session_id)
    
    return event


async def store_event(event: EventDocument) -> None:
    """
    Store event in database or in-memory fallback.
    
    Args:
        event: EventDocument to store
    """
    if is_database_available():
        db = get_database()
        if db is not None:
            events_collection = db.events
            event_dict = event.dict()
            await events_collection.insert_one(event_dict)
            return
    
    # Fallback to in-memory storage
    _in_memory_events.append(event.dict())
    
    # Limit in-memory events to prevent memory issues
    if len(_in_memory_events) > 10000:
        _in_memory_events.pop(0)


async def get_events_by_session(session_id: str, limit: int = 100) -> List[EventDocument]:
    """
    Get events for a session.
    
    Args:
        session_id: Session ID
        limit: Maximum number of events to return
        
    Returns:
        List of EventDocument
    """
    if is_database_available():
        db = get_database()
        if db is not None:
            events_collection = db.events
            cursor = events_collection.find(
                {"session_id": session_id}
            ).sort("timestamp", -1).limit(limit)
            
            events = []
            async for event_dict in cursor:
                events.append(EventDocument(**event_dict))
            return events
    
    # Check in-memory
    events = [
        EventDocument(**event)
        for event in _in_memory_events
        if event.get("session_id") == session_id
    ]
    events.sort(key=lambda x: x.timestamp, reverse=True)
    return events[:limit]

