"""
WebSocket Failure Logging
Tracks WebSocket disconnects, errors, and timeouts
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from .models import WebSocketFailureDocument
from database.connection import get_database, is_database_available


# In-memory WebSocket failure logs for fallback
_in_memory_ws_failures: List[Dict[str, Any]] = []


async def log_websocket_failure(
    failure_type: str,
    session_id: Optional[str] = None,
    error_code: Optional[int] = None,
    error_message: Optional[str] = None,
    close_code: Optional[int] = None,
    close_reason: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Log a WebSocket failure.
    
    Args:
        failure_type: Failure type (disconnect, error, timeout)
        session_id: Optional session ID
        error_code: Optional WebSocket error code
        error_message: Optional error message
        close_code: Optional WebSocket close code
        close_reason: Optional close reason
        duration_seconds: Connection duration before failure
        metadata: Optional additional metadata
        
    Returns:
        WebSocket failure log ID
    """
    ws_failure_id = str(uuid.uuid4())
    
    ws_failure = WebSocketFailureDocument(
        ws_failure_id=ws_failure_id,
        session_id=session_id,
        failure_type=failure_type,
        error_code=error_code,
        error_message=error_message,
        close_code=close_code,
        close_reason=close_reason,
        duration_seconds=duration_seconds,
        metadata=metadata or {}
    )
    
    await store_websocket_failure(ws_failure)
    return ws_failure_id


async def store_websocket_failure(ws_failure: WebSocketFailureDocument) -> None:
    """
    Store WebSocket failure log in database or in-memory fallback.
    
    Args:
        ws_failure: WebSocketFailureDocument to store
    """
    try:
        if is_database_available():
            db = get_database()
            if db is not None:
                ws_failures_collection = db.websocket_failures
                await ws_failures_collection.insert_one(ws_failure.dict())
                return
        
        # Fallback to in-memory storage
        _in_memory_ws_failures.append(ws_failure.dict())
        
        # Limit in-memory logs
        if len(_in_memory_ws_failures) > 10000:
            _in_memory_ws_failures.pop(0)
            
    except Exception as e:
        # Silently fail
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error storing WebSocket failure: {str(e)}")

