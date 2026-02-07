"""
Visitor Deduplication Logic
24-hour unique visitor tracking with deduplication
"""

import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from database.connection import get_database, is_database_available


def generate_visitor_id(ip_hash: str, user_agent: str) -> str:
    """
    Generate a unique visitor ID from IP hash and user agent.
    This creates a consistent identifier for the same visitor.
    
    Args:
        ip_hash: Hashed IP address
        user_agent: User agent string
        
    Returns:
        Visitor ID (SHA-256 hash)
    """
    combined = f"{ip_hash}{user_agent}".encode('utf-8')
    visitor_id = hashlib.sha256(combined).hexdigest()
    return visitor_id


async def is_unique_visitor_24h(
    visitor_id: str,
    session_id: Optional[str] = None,
    ip_hash: Optional[str] = None
) -> bool:
    """
    Check if visitor is unique within the last 24 hours.
    
    Args:
        visitor_id: Visitor ID
        session_id: Optional session ID for additional check
        ip_hash: Optional IP hash for fallback check
        
    Returns:
        True if unique visitor (first visit in 24h), False otherwise
    """
    if not visitor_id:
        return False
    
    # 24 hours ago timestamp
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    
    # Check database if available
    if is_database_available():
        db = get_database()
        if db is not None:
            # Check visits collection
            visits_collection = db.visits
            existing_visit = await visits_collection.find_one({
                "$or": [
                    {"visitor_id": visitor_id},
                    *([{"session_id": session_id}] if session_id else []),
                    *([{"ip_hash": ip_hash}] if ip_hash else [])
                ],
                "timestamp": {"$gte": twenty_four_hours_ago}
            })
            
            if existing_visit:
                return False
            
            # Check sessions collection
            sessions_collection = db.sessions
            existing_session = await sessions_collection.find_one({
                "$or": [
                    {"visitor_id": visitor_id},
                    *([{"session_id": session_id}] if session_id else [])
                ],
                "started_at": {"$gte": twenty_four_hours_ago}
            })
            
            if existing_session:
                return False
    
    return True


async def get_or_create_visitor_id(
    ip_hash: str,
    user_agent: str,
    session_id: Optional[str] = None
) -> Tuple[str, bool]:
    """
    Get or create visitor ID and check if it's a unique visitor.
    
    Args:
        ip_hash: Hashed IP address
        user_agent: User agent string
        session_id: Optional session ID
        
    Returns:
        Tuple of (visitor_id, is_unique_visitor)
    """
    visitor_id = generate_visitor_id(ip_hash, user_agent)
    is_unique = await is_unique_visitor_24h(visitor_id, session_id, ip_hash)
    
    return visitor_id, is_unique

