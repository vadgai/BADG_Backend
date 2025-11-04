"""
Custom middleware for VADG API.
Provides request/response processing, security, and monitoring.
"""

import time
import uuid
from typing import Callable, Dict, Any
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Try relative imports first, fallback to absolute
try:
    from .logging_config import get_logger, log_api_request
    from .config import get_settings
    from .exceptions import VADGException, create_http_exception
except ImportError:
    # Fallback to absolute imports for local development
    try:
        from logging_config import get_logger, log_api_request
        from config import get_settings
        from exceptions import VADGException, create_http_exception
    except ImportError:
        # Create dummy functions if modules don't exist
        import logging
        def get_logger(name):
            return logging.getLogger(name)
        def log_api_request(request, response, duration):
            pass
        def get_settings():
            return None
        class VADGException(Exception):
            pass
        def create_http_exception(status_code, detail):
            return HTTPException(status_code=status_code, detail=detail)

logger = get_logger("middleware")
settings = get_settings()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add unique request ID to each request."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add request ID to request and response headers."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to responses."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Content Security Policy for healthcare data
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://generativelanguage.googleapis.com; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log API requests and responses."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response information."""
        start_time = time.time()
        
        # Log request
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "client_ip": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("user-agent", "unknown"),
                "request_id": getattr(request.state, "request_id", None)
            }
        )
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Log successful response
            log_api_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                response_time=process_time,
                request_id=getattr(request.state, "request_id", None)
            )
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            
            # Log error
            logger.error(
                f"Request failed: {request.method} {request.url.path} - {str(e)}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "response_time": process_time,
                    "request_id": getattr(request.state, "request_id", None)
                },
                exc_info=True
            )
            
            # Return error response
            if isinstance(e, VADGException):
                http_exception = create_http_exception(e)
                return JSONResponse(
                    status_code=http_exception.status_code,
                    content=http_exception.detail
                )
            else:
                return JSONResponse(
                    status_code=500,
                    content={"error": "Internal server error", "detail": str(e)}
                )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.requests: Dict[str, list] = {}
        self.cleanup_interval = 60  # Clean up old entries every 60 seconds
        self.last_cleanup = time.time()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check rate limit for request."""
        # Clean up old entries periodically
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_entries(current_time)
            self.last_cleanup = current_time
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Check rate limit
        if self._is_rate_limited(client_ip, current_time):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": "Too many requests. Please try again later."
                }
            )
        
        # Record request
        self._record_request(client_ip, current_time)
        
        return await call_next(request)
    
    def _is_rate_limited(self, client_ip: str, current_time: float) -> bool:
        """Check if client is rate limited."""
        if client_ip not in self.requests:
            return False
        
        # Remove requests older than the window
        window_start = current_time - settings.rate_limit_window
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip] 
            if req_time > window_start
        ]
        
        # Check if limit exceeded
        return len(self.requests[client_ip]) >= settings.rate_limit_requests
    
    def _record_request(self, client_ip: str, current_time: float) -> None:
        """Record a request for rate limiting."""
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        self.requests[client_ip].append(current_time)
    
    def _cleanup_old_entries(self, current_time: float) -> None:
        """Clean up old rate limit entries."""
        window_start = current_time - settings.rate_limit_window
        for client_ip in list(self.requests.keys()):
            self.requests[client_ip] = [
                req_time for req_time in self.requests[client_ip] 
                if req_time > window_start
            ]
            if not self.requests[client_ip]:
                del self.requests[client_ip]


class HealthCheckMiddleware(BaseHTTPMiddleware):
    """Middleware to handle health check requests."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Handle health check requests."""
        if request.url.path == "/health":
            return JSONResponse(
                status_code=200,
                content={
                    "status": "healthy",
                    "timestamp": time.time(),
                    "version": settings.app_version,
                    "environment": "development" if settings.debug else "production"
                }
            )
        
        return await call_next(request)


class CORSSecurityMiddleware(BaseHTTPMiddleware):
    """Enhanced CORS middleware with security considerations."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Handle CORS with security enhancements."""
        response = await call_next(request)
        
        # Add CORS headers
        origin = request.headers.get("origin")
        if origin in settings.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        
        # Add CORS headers for preflight requests
        if request.method == "OPTIONS":
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Request-ID"
            response.headers["Access-Control-Max-Age"] = "86400"  # 24 hours
        
        return response
