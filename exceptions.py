"""
Custom exception classes for VADG API.
Provides structured error handling and consistent error responses.
"""

from fastapi import HTTPException
from typing import Optional, Dict, Any


class VADGException(Exception):
    """Base exception class for VADG application."""
    
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class SessionNotFoundError(VADGException):
    """Raised when a session is not found."""
    
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Session {session_id} not found",
            status_code=404,
            details={"session_id": session_id}
        )


class InvalidPatientDataError(VADGException):
    """Raised when patient data is invalid."""
    
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=400,
            details={"field": field} if field else {}
        )


class AIProcessingError(VADGException):
    """Raised when AI processing fails."""
    
    def __init__(self, message: str, component: str):
        super().__init__(
            message=f"AI processing error in {component}: {message}",
            status_code=500,
            details={"component": component}
        )


class ExternalServiceError(VADGException):
    """Raised when external service (e.g., Google AI) fails."""
    
    def __init__(self, service: str, message: str):
        super().__init__(
            message=f"External service {service} error: {message}",
            status_code=503,
            details={"service": service}
        )


class ReportGenerationError(VADGException):
    """Raised when report generation fails."""
    
    def __init__(self, message: str, session_id: str):
        super().__init__(
            message=f"Report generation failed: {message}",
            status_code=500,
            details={"session_id": session_id}
        )


class WebSocketConnectionError(VADGException):
    """Raised when WebSocket connection fails."""
    
    def __init__(self, message: str, session_id: str):
        super().__init__(
            message=f"WebSocket connection error: {message}",
            status_code=1011,
            details={"session_id": session_id}
        )


def create_http_exception(exception: VADGException) -> HTTPException:
    """Convert VADGException to FastAPI HTTPException."""
    return HTTPException(
        status_code=exception.status_code,
        detail={
            "error": exception.message,
            "details": exception.details
        }
    )
