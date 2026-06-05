"""
Analytics API Routes
Event tracking and analytics endpoints
"""

import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics import (
    EventRequest,
    EventResponse,
    EventType,
    log_event,
    get_session,
    update_session_heartbeat,
    create_session,
    get_client_ip,
    should_filter_request
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/event", response_model=EventResponse)
async def track_event(
    event_data: EventRequest,
    request: Request
):
    """
    Track an analytics event.
    
    Events:
    - visit_home: User visits home page
    - start_symptom_entry: User starts filling symptom form
    - symptom_entry_completed: User completes symptom form
    - model_request_sent: AI model request initiated
    - model_request_completed: AI model request completed
    - follow_up_started: Follow-up questions started
    - follow_up_completed: Follow-up questions completed
    - diagnosis_completed: Diagnosis report generated
    - pdf_generated: PDF report generated
    - session_closed: Session ended
    """
    try:
        # Filter bots
        user_agent = request.headers.get("user-agent", "")
        client_ip = get_client_ip(request)
        
        if should_filter_request(user_agent, client_ip):
            return EventResponse(
                success=True,
                message="Event filtered (bot traffic)"
            )
        
        # Get or use provided session ID
        session_id = event_data.session_id
        
        # If no session ID, try to get from request headers or create new
        if not session_id:
            session_id = request.headers.get("X-Session-ID")
        
        # Log the event
        event = await log_event(
            event_name=event_data.event_name,
            session_id=session_id,
            request=request,
            metadata=event_data.metadata,
            page=event_data.page
        )
        
        # Update session heartbeat if session exists
        if session_id:
            await update_session_heartbeat(session_id)
        
        return EventResponse(
            success=True,
            event_id=event.event_id,
            session_id=event.session_id or session_id
        )
        
    except Exception as e:
        # Do not break the app if analytics fails
        logger.warning(f"Analytics tracking failed (non-fatal): {str(e)}", exc_info=True)
        return EventResponse(
            success=False,
            message="Analytics tracking failed (non-fatal)."
        )


@router.get("/session/{session_id}")
async def get_session_info(session_id: str):
    """
    Get session information.
    """
    try:
        session = await get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "success": True,
            "session": session.dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")


@router.post("/session/heartbeat")
async def session_heartbeat(request: Request):
    """
    Update session heartbeat.
    Called every 20 seconds to keep session active.
    """
    try:
        # Get session ID from request body or header
        session_id = request.headers.get("X-Session-ID")
        
        # Try to get from request body if not in header
        if not session_id:
            try:
                body = await request.json()
                session_id = body.get("session_id")
            except Exception:
                pass
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id required")
        
        updated = await update_session_heartbeat(session_id)
        
        if not updated:
            # Non-fatal: allow frontend to continue without a hard failure
            return {
                "success": False,
                "session_id": session_id,
                "message": "Session not found"
            }
        
        return {
            "success": True,
            "session_id": session_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Heartbeat update failed (non-fatal): {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": "Heartbeat update failed (non-fatal)."
        }


# Ad-blockers often block URLs containing "analytics". Mirror routes under /api/telemetry.
telemetry_router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])
telemetry_router.add_api_route(
    "/event",
    track_event,
    methods=["POST"],
    response_model=EventResponse,
)
telemetry_router.add_api_route(
    "/session/{session_id}",
    get_session_info,
    methods=["GET"],
)
telemetry_router.add_api_route(
    "/session/heartbeat",
    session_heartbeat,
    methods=["POST"],
)

