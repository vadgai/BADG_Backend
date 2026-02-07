"""
Error Logging Middleware
Automatically logs errors and API failures
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import status
from fastapi.responses import JSONResponse

from .error_logger import log_error, log_api_failure
from .ip_utils import get_client_ip

logger = logging.getLogger(__name__)


class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically log errors and API failures.
    """
    
    def __init__(self, app, excluded_paths=None):
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico",
        ]
    
    async def dispatch(self, request: Request, call_next):
        # Skip excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)
        
        start_time = time.time()
        session_id = request.headers.get("X-Session-ID")
        
        try:
            response = await call_next(request)
            
            # Log API failures (4xx, 5xx)
            if response.status_code >= 400:
                duration_ms = (time.time() - start_time) * 1000
                
                # Get response body if available
                response_body = None
                try:
                    if hasattr(response, 'body'):
                        body_bytes = response.body
                        if body_bytes:
                            response_body = body_bytes.decode('utf-8')[:1000]  # Truncate
                except Exception:
                    pass
                
                # Determine if timeout
                timeout = duration_ms > 30000  # 30 seconds
                
                # Get request payload
                payload = None
                try:
                    if request.method in ["POST", "PUT", "PATCH"]:
                        body = await request.body()
                        if body:
                            import json
                            payload = json.loads(body.decode('utf-8'))
                except Exception:
                    pass
                
                await log_api_failure(
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    error_message=f"HTTP {response.status_code}",
                    session_id=session_id,
                    error_type="HTTPError",
                    timeout=timeout,
                    payload=payload,
                    response_body=response_body,
                    duration_ms=duration_ms
                )
            
            return response
            
        except Exception as e:
            # Log exception
            duration_ms = (time.time() - start_time) * 1000
            
            # Determine status code
            status_code = 500
            if hasattr(e, 'status_code'):
                status_code = e.status_code
            elif hasattr(e, 'status'):
                status_code = e.status
            
            # Get request payload
            payload = None
            try:
                if request.method in ["POST", "PUT", "PATCH"]:
                    body = await request.body()
                    if body:
                        import json
                        payload = json.loads(body.decode('utf-8'))
            except Exception:
                pass
            
            # Log error
            await log_error(
                error=e,
                session_id=session_id,
                request=request,
                endpoint=request.url.path,
                method=request.method,
                status_code=status_code,
                payload=payload,
                severity="critical" if status_code >= 500 else "error"
            )
            
            # Return error response
            return JSONResponse(
                status_code=status_code,
                content={
                    "error": str(e),
                    "type": type(e).__name__
                }
            )

