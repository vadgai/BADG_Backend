"""
Model Accuracy Tracking
Tracks predicted vs confirmed diseases for accuracy analysis
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from .models import AccuracyLogDocument
from database.connection import get_database, is_database_available


# In-memory accuracy logs for fallback
_in_memory_accuracy_logs: List[Dict[str, Any]] = []


def calculate_accuracy_bucket(
    predicted: str,
    confirmed: Optional[str],
    confidence: Optional[float] = None
) -> Optional[str]:
    """
    Calculate accuracy bucket based on prediction and confirmation.
    
    Args:
        predicted: Predicted disease name
        confirmed: Confirmed disease name (if available)
        confidence: Model confidence score (0-1)
        
    Returns:
        Accuracy bucket: "exact_match", "partial_match", "incorrect", or None
    """
    if not confirmed:
        return None
    
    predicted_lower = predicted.lower().strip()
    confirmed_lower = confirmed.lower().strip()
    
    # Exact match
    if predicted_lower == confirmed_lower:
        return "exact_match"
    
    # Partial match (predicted contains confirmed or vice versa)
    if predicted_lower in confirmed_lower or confirmed_lower in predicted_lower:
        return "partial_match"
    
    # Check for similar terms (basic fuzzy matching)
    predicted_words = set(predicted_lower.split())
    confirmed_words = set(confirmed_lower.split())
    
    # If significant overlap, consider partial match
    if predicted_words and confirmed_words:
        overlap = len(predicted_words & confirmed_words)
        total_unique = len(predicted_words | confirmed_words)
        similarity = overlap / total_unique if total_unique > 0 else 0
        
        if similarity >= 0.5:
            return "partial_match"
    
    return "incorrect"


async def log_accuracy(
    predicted_disease: str,
    session_id: Optional[str] = None,
    model_log_id: Optional[str] = None,
    confirmed_disease: Optional[str] = None,
    confidence_score: Optional[float] = None,
    confirmed_by: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    Log model accuracy data.
    
    Args:
        predicted_disease: Disease predicted by model
        session_id: Optional session ID
        model_log_id: Optional reference to model log
        confirmed_disease: Optional confirmed disease
        confidence_score: Optional model confidence score (0-1)
        confirmed_by: Optional who confirmed (user, doctor, etc.)
        notes: Optional additional notes
        
    Returns:
        Accuracy log ID
    """
    accuracy_id = str(uuid.uuid4())
    
    # Calculate accuracy bucket if confirmed
    accuracy_bucket = None
    is_correct = None
    
    if confirmed_disease:
        accuracy_bucket = calculate_accuracy_bucket(predicted_disease, confirmed_disease, confidence_score)
        is_correct = accuracy_bucket == "exact_match"
    
    accuracy_log = AccuracyLogDocument(
        accuracy_id=accuracy_id,
        session_id=session_id,
        model_log_id=model_log_id,
        predicted_disease=predicted_disease,
        confirmed_disease=confirmed_disease,
        confidence_score=confidence_score,
        is_correct=is_correct,
        accuracy_bucket=accuracy_bucket,
        confirmed_at=datetime.utcnow() if confirmed_disease else None,
        confirmed_by=confirmed_by,
        notes=notes
    )
    
    await store_accuracy_log(accuracy_log)
    return accuracy_id


async def store_accuracy_log(accuracy_log: AccuracyLogDocument) -> None:
    """
    Store accuracy log in database or in-memory fallback.
    
    Args:
        accuracy_log: AccuracyLogDocument to store
    """
    try:
        if is_database_available():
            db = get_database()
            if db is not None:
                accuracy_logs_collection = db.accuracy_logs
                await accuracy_logs_collection.insert_one(accuracy_log.dict())
                return
        
        # Fallback to in-memory storage
        _in_memory_accuracy_logs.append(accuracy_log.dict())
        
        # Limit in-memory logs
        if len(_in_memory_accuracy_logs) > 10000:
            _in_memory_accuracy_logs.pop(0)
            
    except Exception as e:
        # Silently fail
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error storing accuracy log: {str(e)}")

