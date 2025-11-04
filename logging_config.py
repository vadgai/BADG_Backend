"""
Logging configuration for VADG API.
Provides structured logging with proper formatting and security considerations.
"""

import logging
import sys
from typing import Dict, Any
from datetime import datetime
import json
import os


class SecurityFilter(logging.Filter):
    """Filter to remove sensitive information from logs."""
    
    SENSITIVE_KEYS = {
        'password', 'token', 'key', 'secret', 'api_key', 'authorization',
        'credit_card', 'ssn', 'social_security', 'patient_id'
    }
    
    def filter(self, record):
        """Remove sensitive information from log records."""
        if hasattr(record, 'args') and isinstance(record.args, dict):
            record.args = self._sanitize_dict(record.args)
        return True
    
    def _sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize dictionary data."""
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_KEYS):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [self._sanitize_dict(item) if isinstance(item, dict) else item for item in value]
            else:
                sanitized[key] = value
        return sanitized


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record):
        """Format log record as JSON."""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, 'session_id'):
            log_entry['session_id'] = record.session_id
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_entry['request_id'] = record.request_id
            
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> logging.Logger:
    """
    Set up logging configuration for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format (json, text)
    
    Returns:
        Configured logger instance
    """
    # Get log level from environment or parameter
    level = getattr(logging, os.getenv("LOG_LEVEL", log_level).upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger("vadg")
    logger.setLevel(level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Set formatter
    if log_format.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s'
        )
    
    console_handler.setFormatter(formatter)
    
    # Add security filter
    security_filter = SecurityFilter()
    console_handler.addFilter(security_filter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    # Configure uvicorn logger
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.setLevel(level)
    uvicorn_logger.addHandler(console_handler)
    
    # Configure uvicorn access logger
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.setLevel(logging.INFO)
    uvicorn_access_logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(f"vadg.{name}")


# Health check logging
def log_health_check(endpoint: str, status: str, response_time: float, **kwargs):
    """Log health check information."""
    logger = get_logger("health")
    logger.info(
        f"Health check: {endpoint} - {status}",
        extra={
            "endpoint": endpoint,
            "status": status,
            "response_time": response_time,
            **kwargs
        }
    )


# API request logging
def log_api_request(method: str, path: str, status_code: int, response_time: float, **kwargs):
    """Log API request information."""
    logger = get_logger("api")
    logger.info(
        f"API Request: {method} {path} - {status_code}",
        extra={
            "method": method,
            "path": path,
            "status_code": status_code,
            "response_time": response_time,
            **kwargs
        }
    )


# AI processing logging
def log_ai_processing(component: str, operation: str, success: bool, **kwargs):
    """Log AI processing information."""
    logger = get_logger("ai")
    level = logging.INFO if success else logging.ERROR
    logger.log(
        level,
        f"AI Processing: {component} - {operation} - {'Success' if success else 'Failed'}",
        extra={
            "component": component,
            "operation": operation,
            "success": success,
            **kwargs
        }
    )


# Session logging
def log_session_event(session_id: str, event: str, **kwargs):
    """Log session-related events."""
    logger = get_logger("session")
    logger.info(
        f"Session Event: {session_id} - {event}",
        extra={
            "session_id": session_id,
            "event": event,
            **kwargs
        }
    )
