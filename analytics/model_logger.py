"""
Model Performance and Latency Tracking
Logs model calls with latency, token counts, and errors
"""

import uuid
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager

from .models import ModelLogDocument
from database.connection import get_database, is_database_available


# In-memory model logs for fallback
_in_memory_model_logs: List[Dict[str, Any]] = []


def get_in_memory_model_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get in-memory model logs with optional date filtering.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        limit: Maximum number of logs to return
        
    Returns:
        List of model log dictionaries
    """
    logs = _in_memory_model_logs.copy()
    
    # Filter by date if provided
    if start_date or end_date:
        filtered_logs = []
        start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_dt = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)) if end_date else None
        
        for log in logs:
            log_timestamp = log.get("input_timestamp")
            if log_timestamp:
                # Handle both datetime objects and strings
                if isinstance(log_timestamp, str):
                    try:
                        # Try ISO format first
                        if 'T' in log_timestamp or '+' in log_timestamp or 'Z' in log_timestamp:
                            log_dt = datetime.fromisoformat(log_timestamp.replace('Z', '+00:00'))
                        else:
                            # Try date-only format
                            log_dt = datetime.strptime(log_timestamp, "%Y-%m-%d")
                    except (ValueError, AttributeError):
                        continue
                elif isinstance(log_timestamp, datetime):
                    log_dt = log_timestamp
                else:
                    continue
                
                # Normalize to naive datetime for comparison
                if log_dt.tzinfo is not None:
                    log_dt = log_dt.replace(tzinfo=None)
                
                if start_dt and log_dt < start_dt:
                    continue
                if end_dt and log_dt >= end_dt:
                    continue
                
                filtered_logs.append(log)
        logs = filtered_logs
    
    # Sort by timestamp (newest first) and limit
    def get_timestamp(log_entry):
        ts = log_entry.get("input_timestamp")
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
    
    logs.sort(key=get_timestamp, reverse=True)
    return logs[:limit]


@contextmanager
def log_model_call(
    model_name: str,
    session_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    prompt: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Context manager to automatically log model calls with latency tracking.
    
    Usage:
        with log_model_call("gemini-2.5-flash", session_id="abc123") as log:
            response = model.generate_content(prompt)
            log.set_response(response, prompt_length=len(prompt))
    """
    log_id = str(uuid.uuid4())
    input_timestamp = datetime.utcnow()
    start_time = time.time()
    
    log_entry = {
        "log_id": log_id,
        "session_id": session_id,
        "model_name": model_name,
        "input_timestamp": input_timestamp,
        "endpoint": endpoint,
        "prompt_length": len(prompt) if prompt else None,
        "metadata": metadata or {},
        "success": False,
    }
    
    try:
        yield log_entry
        
        # Calculate latency
        output_timestamp = datetime.utcnow()
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000
        
        log_entry.update({
            "output_timestamp": output_timestamp,
            "total_latency_ms": latency_ms,
            "success": True,
        })
        
    except Exception as e:
        # Log error
        output_timestamp = datetime.utcnow()
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000
        
        log_entry.update({
            "output_timestamp": output_timestamp,
            "total_latency_ms": latency_ms,
            "success": False,
            "error_message": str(e),
            "error_type": type(e).__name__,
        })
        raise
    
    finally:
        # Store log (note: context manager doesn't support async, so we'll store synchronously)
        # For async storage, use log_model_call_async instead
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule the coroutine
                asyncio.create_task(store_model_log(log_entry))
            else:
                loop.run_until_complete(store_model_log(log_entry))
        except RuntimeError:
            # No event loop, create a new one
            asyncio.run(store_model_log(log_entry))


async def store_model_log(log_data: Dict[str, Any]) -> None:
    """
    Store model log in database or in-memory fallback.
    
    Args:
        log_data: Dictionary with log data
    """
    try:
        # Create ModelLogDocument
        model_log = ModelLogDocument(**log_data)
        
        if is_database_available():
            db = get_database()
            if db is not None:
                model_logs_collection = db.model_logs
                await model_logs_collection.insert_one(model_log.dict())
                return
        
        # Fallback to in-memory storage
        _in_memory_model_logs.append(model_log.dict())
        
        # Limit in-memory logs to prevent memory issues
        if len(_in_memory_model_logs) > 10000:
            _in_memory_model_logs.pop(0)
            
    except Exception as e:
        # Silently fail - logging should not break the app
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error storing model log: {str(e)}")


async def log_model_call_async(
    model_name: str,
    session_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    prompt: Optional[str] = None,
    response: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    success: bool = True,
    error: Optional[Exception] = None,
    latency_ms: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Log a model call asynchronously.
    
    Args:
        model_name: Name of the model
        session_id: Optional session ID
        endpoint: Optional endpoint that triggered the call
        prompt: Optional prompt text
        response: Optional response text
        input_tokens: Optional input token count
        output_tokens: Optional output token count
        success: Whether call succeeded
        error: Optional exception if failed
        latency_ms: Optional latency in milliseconds (if not provided, will be calculated)
        metadata: Optional additional metadata
        
    Returns:
        Log ID
    """
    log_id = str(uuid.uuid4())
    input_timestamp = datetime.utcnow()
    output_timestamp = datetime.utcnow() if success or error else None
    
    log_data = {
        "log_id": log_id,
        "session_id": session_id,
        "model_name": model_name,
        "input_timestamp": input_timestamp,
        "output_timestamp": output_timestamp,
        "total_latency_ms": latency_ms,
        "input_token_count": input_tokens,
        "output_token_count": output_tokens,
        "total_token_count": (input_tokens + output_tokens) if (input_tokens and output_tokens) else None,
        "success": success,
        "endpoint": endpoint,
        "prompt_length": len(prompt) if prompt else None,
        "response_length": len(response) if response else None,
        "metadata": metadata or {},
    }
    
    if error:
        log_data.update({
            "error_message": str(error),
            "error_type": type(error).__name__,
        })
    
    await store_model_log(log_data)
    return log_id


def extract_token_count(response) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract token counts from model response if available.
    
    Args:
        response: Model response object
        
    Returns:
        Tuple of (input_tokens, output_tokens) or (None, None)
    """
    try:
        # Try to get usage metadata from response
        if hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            input_tokens = getattr(usage, 'prompt_token_count', None)
            output_tokens = getattr(usage, 'candidates_token_count', None)
            return input_tokens, output_tokens
        
        # Try alternative attribute names
        if hasattr(response, 'usage'):
            usage = response.usage
            input_tokens = getattr(usage, 'prompt_tokens', None) or getattr(usage, 'input_tokens', None)
            output_tokens = getattr(usage, 'completion_tokens', None) or getattr(usage, 'output_tokens', None)
            return input_tokens, output_tokens
        
    except Exception:
        pass
    
    return None, None

