"""
PDF Generation Logging
Tracks PDF generation performance and errors
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from .models import PdfLogDocument
from database.connection import get_database, is_database_available


# In-memory PDF logs for fallback
_in_memory_pdf_logs: List[Dict[str, Any]] = []


async def log_pdf_generation(
    session_id: Optional[str] = None,
    render_start: Optional[datetime] = None,
    render_end: Optional[datetime] = None,
    render_time_ms: Optional[float] = None,
    success: bool = False,
    error: Optional[Exception] = None,
    pdf_size_bytes: Optional[int] = None,
    language: Optional[str] = None,
    page_count: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Log PDF generation event.
    
    Args:
        session_id: Optional session ID
        render_start: PDF render start timestamp
        render_end: PDF render end timestamp
        render_time_ms: Render time in milliseconds
        success: Whether PDF generation succeeded
        error: Optional exception if failed
        pdf_size_bytes: Generated PDF size in bytes
        language: PDF language
        page_count: Number of pages in PDF
        metadata: Optional additional metadata
        
    Returns:
        PDF log ID
    """
    pdf_log_id = str(uuid.uuid4())
    
    if render_start is None:
        render_start = datetime.utcnow()
    
    pdf_log = PdfLogDocument(
        pdf_log_id=pdf_log_id,
        session_id=session_id,
        render_start=render_start,
        render_end=render_end,
        render_time_ms=render_time_ms,
        success=success,
        error_message=str(error) if error else None,
        error_type=type(error).__name__ if error else None,
        pdf_size_bytes=pdf_size_bytes,
        language=language,
        page_count=page_count,
        metadata=metadata or {}
    )
    
    await store_pdf_log(pdf_log)
    return pdf_log_id


async def store_pdf_log(pdf_log: PdfLogDocument) -> None:
    """
    Store PDF log in database or in-memory fallback.
    
    Args:
        pdf_log: PdfLogDocument to store
    """
    try:
        if is_database_available():
            db = get_database()
            if db is not None:
                pdf_logs_collection = db.pdf_logs
                await pdf_logs_collection.insert_one(pdf_log.dict())
                return
        
        # Fallback to in-memory storage
        _in_memory_pdf_logs.append(pdf_log.dict())
        
        # Limit in-memory logs
        if len(_in_memory_pdf_logs) > 10000:
            _in_memory_pdf_logs.pop(0)
            
    except Exception as e:
        # Silently fail
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error storing PDF log: {str(e)}")

