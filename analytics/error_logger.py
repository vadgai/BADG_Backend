"""
Error and API Failure Logging
Logs errors, API failures, and exceptions with stack traces
"""

import uuid
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import Request

from .models import ErrorLogDocument, ApiFailureDocument
from .ip_utils import get_client_ip, hash_ip
from database.connection import get_database, is_database_available


# In-memory error logs for fallback
_in_memory_error_logs: List[Dict[str, Any]] = []
_in_memory_api_failures: List[Dict[str, Any]] = []


def get_in_memory_error_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    severity: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get in-memory error logs with optional date and severity filtering.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        limit: Maximum number of errors to return
        severity: Optional severity filter (critical, error, warning)
        
    Returns:
        List of error log dictionaries
    """
    from datetime import timedelta
    
    errors = _in_memory_error_logs.copy()
    
    # Filter by severity if provided
    if severity:
        errors = [e for e in errors if e.get("severity") == severity]
    
    # Filter by date if provided
    if start_date or end_date:
        filtered_errors = []
        start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_dt = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)) if end_date else None
        
        for error in errors:
            error_timestamp = error.get("timestamp")
            if error_timestamp:
                # Handle both datetime objects and strings
                if isinstance(error_timestamp, str):
                    try:
                        # Try ISO format first
                        if 'T' in error_timestamp or '+' in error_timestamp or 'Z' in error_timestamp:
                            error_dt = datetime.fromisoformat(error_timestamp.replace('Z', '+00:00'))
                        else:
                            # Try date-only format
                            error_dt = datetime.strptime(error_timestamp, "%Y-%m-%d")
                    except (ValueError, AttributeError):
                        continue
                elif isinstance(error_timestamp, datetime):
                    error_dt = error_timestamp
                else:
                    continue
                
                # Normalize to naive datetime for comparison
                if error_dt.tzinfo is not None:
                    error_dt = error_dt.replace(tzinfo=None)
                
                if start_dt and error_dt < start_dt:
                    continue
                if end_dt and error_dt >= end_dt:
                    continue
                
                filtered_errors.append(error)
        errors = filtered_errors
    
    # Sort by timestamp (newest first) and limit
    def get_timestamp(error_entry):
        ts = error_entry.get("timestamp")
        if isinstance(ts, datetime):
            return ts
        elif isinstance(ts, str):
            try:
                if 'T' in ts or '+' in ts or 'Z' in ts:
                    return datetime.fromisoformat(ts.replace('Z', '+00:00'))
                else:
                    return datetime.strptime(ts, "%Y-%m-%d")
            except:
                return datetime.min
        return datetime.min
    
    errors.sort(key=get_timestamp, reverse=True)
    return errors[:limit]


def get_in_memory_api_failures(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get in-memory API failures with optional date filtering.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        limit: Maximum number of failures to return
        
    Returns:
        List of API failure dictionaries
    """
    from datetime import timedelta
    
    failures = _in_memory_api_failures.copy()
    
    # Filter by date if provided
    if start_date or end_date:
        filtered_failures = []
        start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_dt = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)) if end_date else None
        
        for failure in failures:
            failure_timestamp = failure.get("timestamp")
            if failure_timestamp:
                # Handle both datetime objects and strings
                if isinstance(failure_timestamp, str):
                    try:
                        # Try ISO format first
                        if 'T' in failure_timestamp or '+' in failure_timestamp or 'Z' in failure_timestamp:
                            failure_dt = datetime.fromisoformat(failure_timestamp.replace('Z', '+00:00'))
                        else:
                            # Try date-only format
                            failure_dt = datetime.strptime(failure_timestamp, "%Y-%m-%d")
                    except (ValueError, AttributeError):
                        continue
                elif isinstance(failure_timestamp, datetime):
                    failure_dt = failure_timestamp
                else:
                    continue
                
                # Normalize to naive datetime for comparison
                if failure_dt.tzinfo is not None:
                    failure_dt = failure_dt.replace(tzinfo=None)
                
                if start_dt and failure_dt < start_dt:
                    continue
                if end_dt and failure_dt >= end_dt:
                    continue
                
                filtered_failures.append(failure)
        failures = filtered_failures
    
    # Sort by timestamp (newest first) and limit
    def get_timestamp(failure_entry):
        ts = failure_entry.get("timestamp")
        if isinstance(ts, datetime):
            return ts
        elif isinstance(ts, str):
            try:
                if 'T' in ts or '+' in ts or 'Z' in ts:
                    return datetime.fromisoformat(ts.replace('Z', '+00:00'))
                else:
                    return datetime.strptime(ts, "%Y-%m-%d")
            except:
                return datetime.min
        return datetime.min
    
    failures.sort(key=get_timestamp, reverse=True)
    return failures[:limit]


def sanitize_payload(payload: Any, max_length: int = 1000) -> Optional[Dict[str, Any]]:
    """
    Sanitize payload for logging (remove sensitive data, truncate).
    
    Args:
        payload: Payload to sanitize
        max_length: Maximum length for string values
        
    Returns:
        Sanitized payload dictionary
    """
    if payload is None:
        return None
    
    # Convert to dict if needed
    if isinstance(payload, dict):
        sanitized = {}
        sensitive_keys = ['password', 'token', 'api_key', 'secret', 'authorization', 'auth']
        
        for key, value in payload.items():
            key_lower = str(key).lower()
            
            # Skip sensitive keys
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
                continue
            
            # Truncate long strings
            if isinstance(value, str) and len(value) > max_length:
                sanitized[key] = value[:max_length] + "... [TRUNCATED]"
            elif isinstance(value, (dict, list)):
                # Recursively sanitize nested structures (limit depth)
                sanitized[key] = str(value)[:max_length] + "... [TRUNCATED]" if len(str(value)) > max_length else value
            else:
                sanitized[key] = value
        
        return sanitized
    
    # For non-dict payloads, convert to string and truncate
    payload_str = str(payload)
    if len(payload_str) > max_length:
        return {"payload": payload_str[:max_length] + "... [TRUNCATED]"}
    
    return {"payload": payload_str}


async def log_error(
    error: Exception,
    session_id: Optional[str] = None,
    request: Optional[Request] = None,
    endpoint: Optional[str] = None,
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    payload: Optional[Any] = None,
    severity: str = "error",
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Log an error with full stack trace.
    
    Args:
        error: Exception object
        session_id: Optional session ID
        request: Optional FastAPI Request object
        endpoint: Optional endpoint where error occurred
        method: Optional HTTP method
        status_code: Optional HTTP status code
        payload: Optional request payload
        severity: Error severity (error, warning, critical)
        metadata: Optional additional metadata
        
    Returns:
        Error log ID
    """
    error_id = str(uuid.uuid4())
    
    # Extract request info if available
    user_agent = None
    ip_hash = None
    
    if request:
        user_agent = request.headers.get("user-agent")
        client_ip = get_client_ip(request)
        ip_hash = hash_ip(client_ip)
        if not endpoint:
            endpoint = request.url.path
        if not method:
            method = request.method
    
    # Get stack trace
    stack_trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    
    # Sanitize payload
    payload_snapshot = sanitize_payload(payload)
    
    error_log = ErrorLogDocument(
        error_id=error_id,
        session_id=session_id,
        error_type=type(error).__name__,
        error_message=str(error),
        stack_trace=stack_trace,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        payload_snapshot=payload_snapshot,
        user_agent=user_agent,
        ip_hash=ip_hash,
        severity=severity,
        metadata=metadata or {}
    )
    
    await store_error_log(error_log)
    return error_id


async def log_api_failure(
    endpoint: str,
    method: str,
    status_code: int,
    error_message: str,
    session_id: Optional[str] = None,
    error_type: Optional[str] = None,
    timeout: bool = False,
    retry_count: int = 0,
    payload: Optional[Any] = None,
    response_body: Optional[str] = None,
    duration_ms: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Log an API failure.
    
    Args:
        endpoint: API endpoint
        method: HTTP method
        status_code: HTTP status code
        error_message: Error message
        session_id: Optional session ID
        error_type: Optional error type
        timeout: Whether failure was due to timeout
        retry_count: Number of retries attempted
        payload: Optional request payload
        response_body: Optional response body (truncated)
        duration_ms: Optional request duration in milliseconds
        metadata: Optional additional metadata
        
    Returns:
        Failure log ID
    """
    failure_id = str(uuid.uuid4())
    
    # Sanitize payload and response
    payload_snapshot = sanitize_payload(payload)
    
    if response_body and len(response_body) > 1000:
        response_body = response_body[:1000] + "... [TRUNCATED]"
    
    api_failure = ApiFailureDocument(
        failure_id=failure_id,
        session_id=session_id,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        error_type=error_type or "APIError",
        error_message=error_message,
        timeout=timeout,
        retry_count=retry_count,
        payload_snapshot=payload_snapshot,
        response_body=response_body,
        duration_ms=duration_ms,
        metadata=metadata or {}
    )
    
    await store_api_failure(api_failure)
    return failure_id


async def store_error_log(error_log: ErrorLogDocument) -> None:
    """
    Store error log in database or in-memory fallback.
    
    Args:
        error_log: ErrorLogDocument to store
    """
    try:
        if is_database_available():
            db = get_database()
            if db is not None:
                errors_collection = db.errors
                await errors_collection.insert_one(error_log.dict())
                return
        
        # Fallback to in-memory storage
        _in_memory_error_logs.append(error_log.dict())
        
        # Limit in-memory logs
        if len(_in_memory_error_logs) > 10000:
            _in_memory_error_logs.pop(0)
            
    except Exception as e:
        # Silently fail
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error storing error log: {str(e)}")


async def store_api_failure(api_failure: ApiFailureDocument) -> None:
    """
    Store API failure log in database or in-memory fallback.
    
    Args:
        api_failure: ApiFailureDocument to store
    """
    try:
        if is_database_available():
            db = get_database()
            if db is not None:
                api_failures_collection = db.api_failures
                await api_failures_collection.insert_one(api_failure.dict())
                return
        
        # Fallback to in-memory storage
        _in_memory_api_failures.append(api_failure.dict())
        
        # Limit in-memory logs
        if len(_in_memory_api_failures) > 10000:
            _in_memory_api_failures.pop(0)
            
    except Exception as e:
        # Silently fail
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error storing API failure: {str(e)}")

