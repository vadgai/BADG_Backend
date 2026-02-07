"""
Analytics Middleware
Automatic session creation and tracking for requests
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import status

from .session_tracker import create_session, get_session, update_session_heartbeat
from .bot_filter import should_filter_request
from .ip_utils import get_client_ip

logger = logging.getLogger(__name__)


class AnalyticsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically create and track sessions.
    """
    
    def __init__(self, app, excluded_paths=None):
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico",
            "/analytics/",  # Analytics endpoints themselves
            "/admin/",  # Admin endpoints
        ]
    
    async def dispatch(self, request: Request, call_next):
        # Skip excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)
        
        # Filter bots early
        user_agent = request.headers.get("user-agent", "")
        client_ip = get_client_ip(request)
        
        if should_filter_request(user_agent, client_ip):
            return await call_next(request)
        
        # Get or create session
        session_id = request.headers.get("X-Session-ID")
        session = None
        
        if session_id:
            session = await get_session(session_id)
        
        # Create new session if needed
        if not session:
            try:
                referrer = request.headers.get("referer")
                landing_page = request.url.path
                
                session = await create_session(
                    request=request,
                    landing_page=landing_page,
                    referrer=referrer
                )
                session_id = session.session_id
            except Exception as e:
                logger.error(f"Error creating session: {str(e)}", exc_info=True)
                # Continue without session tracking
        
        # Process request
        response = await call_next(request)
        
        # Add session ID to response headers if session was created
        if session_id and session:
            response.headers["X-Session-ID"] = session_id
        
        return response

