"""
Funnel Analytics Tracker
Tracks user journey through diagnosis funnel steps
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum

from .models import FunnelStepDocument
from database.connection import get_database, is_database_available


class FunnelStep(str, Enum):
    """Funnel step names"""
    FORM_START = "form_start"
    FORM_COMPLETE = "form_complete"
    FOLLOWUP_START = "followup_start"
    FOLLOWUP_COMPLETE = "followup_complete"
    REPORT_GENERATED = "report_generated"
    PDF_GENERATED = "pdf_generated"


# Step numbers for ordering
STEP_NUMBERS = {
    FunnelStep.FORM_START: 1,
    FunnelStep.FORM_COMPLETE: 2,
    FunnelStep.FOLLOWUP_START: 3,
    FunnelStep.FOLLOWUP_COMPLETE: 4,
    FunnelStep.REPORT_GENERATED: 5,
    FunnelStep.PDF_GENERATED: 6,
}


async def track_funnel_step(
    session_id: str,
    step_name: FunnelStep,
    entered_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    dropped_off: bool = False,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Track a funnel step entry/completion.
    
    Args:
        session_id: Session ID
        step_name: Funnel step name
        entered_at: When user entered this step
        completed_at: When user completed this step
        dropped_off: Whether user dropped off
        metadata: Optional metadata
        
    Returns:
        Step ID
    """
    step_id = str(uuid.uuid4())
    
    if entered_at is None:
        entered_at = datetime.utcnow()
    
    # Calculate time spent if completed
    time_spent_seconds = None
    if completed_at and entered_at:
        time_spent_seconds = (completed_at - entered_at).total_seconds()
    
    funnel_step = FunnelStepDocument(
        step_id=step_id,
        session_id=session_id,
        step_name=step_name.value if isinstance(step_name, FunnelStep) else step_name,
        step_number=STEP_NUMBERS.get(step_name, 0),
        entered_at=entered_at,
        completed_at=completed_at,
        time_spent_seconds=time_spent_seconds,
        dropped_off=dropped_off,
        metadata=metadata or {}
    )
    
    await store_funnel_step(funnel_step)
    return step_id


async def store_funnel_step(funnel_step: FunnelStepDocument) -> None:
    """Store funnel step in database"""
    try:
        if is_database_available():
            db = get_database()
            if db is not None:
                funnel_steps_collection = db.funnel_steps
                await funnel_steps_collection.insert_one(funnel_step.dict())
                return
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error storing funnel step: {str(e)}")


async def calculate_funnel_metrics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Calculate funnel metrics including drop-off rates and conversion rates.
    
    Args:
        start_date: Start date for analysis
        end_date: End date for analysis
        
    Returns:
        Dictionary with funnel metrics
    """
    if not is_database_available():
        # Return empty metrics structure when database is not available
        return {
            "total_sessions": 0,
            "total_completions": 0,
            "overall_conversion_rate": 0,
            "step_metrics": {},
            "conversions": {}
        }
    
    db = get_database()
    if db is None:
        # Return empty metrics structure when database is not available
        return {
            "total_sessions": 0,
            "total_completions": 0,
            "overall_conversion_rate": 0,
            "step_metrics": {},
            "conversions": {}
        }
    
    funnel_steps_collection = db.funnel_steps
    
    # Build date filter
    date_filter = {}
    if start_date or end_date:
        date_filter["entered_at"] = {}
        if start_date:
            date_filter["entered_at"]["$gte"] = start_date
        if end_date:
            date_filter["entered_at"]["$lte"] = end_date
    
    # Get all steps
    steps = []
    async for step in funnel_steps_collection.find(date_filter):
        steps.append(step)
    
    # Calculate metrics per step
    step_metrics = {}
    for step_name in FunnelStep:
        step_data = [s for s in steps if s.get("step_name") == step_name.value]
        
        entered_count = len(step_data)
        completed_count = len([s for s in step_data if s.get("completed_at")])
        dropped_off_count = len([s for s in step_data if s.get("dropped_off", False)])
        
        # Calculate average time spent
        time_spent_values = [s.get("time_spent_seconds") for s in step_data if s.get("time_spent_seconds")]
        avg_time_spent = sum(time_spent_values) / len(time_spent_values) if time_spent_values else None
        
        step_metrics[step_name.value] = {
            "entered_count": entered_count,
            "completed_count": completed_count,
            "dropped_off_count": dropped_off_count,
            "drop_off_rate": dropped_off_count / entered_count if entered_count > 0 else 0,
            "avg_time_spent_seconds": avg_time_spent,
        }
    
    # Calculate conversion rates between steps
    conversions = {}
    step_list = list(FunnelStep)
    for i in range(len(step_list) - 1):
        current_step = step_list[i]
        next_step = step_list[i + 1]
        
        current_entered = step_metrics.get(current_step.value, {}).get("entered_count", 0)
        next_entered = step_metrics.get(next_step.value, {}).get("entered_count", 0)
        
        conversion_rate = next_entered / current_entered if current_entered > 0 else 0
        
        conversions[f"{current_step.value} -> {next_step.value}"] = {
            "from_count": current_entered,
            "to_count": next_entered,
            "conversion_rate": conversion_rate,
            "drop_off_count": current_entered - next_entered,
        }
    
    return {
        "period": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        "step_metrics": step_metrics,
        "conversions": conversions,
        "total_sessions": step_metrics.get(FunnelStep.FORM_START.value, {}).get("entered_count", 0),
        "total_completions": step_metrics.get(FunnelStep.REPORT_GENERATED.value, {}).get("completed_count", 0),
        "overall_conversion_rate": (
            step_metrics.get(FunnelStep.REPORT_GENERATED.value, {}).get("completed_count", 0) /
            step_metrics.get(FunnelStep.FORM_START.value, {}).get("entered_count", 1)
        ) if step_metrics.get(FunnelStep.FORM_START.value, {}).get("entered_count", 0) > 0 else 0,
    }

