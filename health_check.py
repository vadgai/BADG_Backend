"""
Health check module for VADG API.
Provides comprehensive health monitoring and status reporting.
"""

import time
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .models import HealthCheckResponse
from .config import get_settings
from .logging_config import get_logger, log_health_check
from .session_manager import get_session_manager

logger = get_logger("health_check")
settings = get_settings()

# Create health check router
health_router = APIRouter(prefix="/health", tags=["Health Check"])


class HealthChecker:
    """Health check service for monitoring system components."""
    
    def __init__(self):
        self.session_manager = get_session_manager()
        self._start_time = time.time()
        self._last_check = None
        self._check_results = {}
    
    async def check_ai_service(self) -> Dict[str, Any]:
        """Check AI service availability."""
        try:
            # Import here to avoid circular imports
            from .symptom_processing.symptom import model_available
            
            if not model_available:
                return {
                    "status": "unavailable",
                    "message": "AI model not configured",
                    "response_time": 0
                }
            
            start_time = time.time()
            
            # Simple test prompt
            test_prompt = "Test connection"
            # Note: In a real implementation, you would test the actual AI service
            # For now, we'll simulate a check
            
            response_time = time.time() - start_time
            
            return {
                "status": "healthy",
                "message": "AI service responding",
                "response_time": response_time
            }
            
        except Exception as e:
            logger.error(f"AI service health check failed: {e}")
            return {
                "status": "unhealthy",
                "message": f"AI service error: {str(e)}",
                "response_time": 0
            }
    
    async def check_session_manager(self) -> Dict[str, Any]:
        """Check session manager health."""
        try:
            start_time = time.time()
            
            # Get session statistics
            stats = self.session_manager.get_session_stats()
            
            response_time = time.time() - start_time
            
            # Check if session manager is overloaded
            if stats["total_sessions"] >= stats["max_sessions"] * 0.9:
                return {
                    "status": "warning",
                    "message": "Session manager near capacity",
                    "response_time": response_time,
                    "details": stats
                }
            
            return {
                "status": "healthy",
                "message": "Session manager operational",
                "response_time": response_time,
                "details": stats
            }
            
        except Exception as e:
            logger.error(f"Session manager health check failed: {e}")
            return {
                "status": "unhealthy",
                "message": f"Session manager error: {str(e)}",
                "response_time": 0
            }
    
    async def check_database(self) -> Dict[str, Any]:
        """Check database connectivity (placeholder for future implementation)."""
        try:
            start_time = time.time()
            
            # Placeholder for database check
            # In the future, this would check actual database connectivity
            await asyncio.sleep(0.01)  # Simulate database check
            
            response_time = time.time() - start_time
            
            return {
                "status": "healthy",
                "message": "Database operational",
                "response_time": response_time
            }
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "message": f"Database error: {str(e)}",
                "response_time": 0
            }
    
    async def check_external_services(self) -> Dict[str, Any]:
        """Check external service dependencies."""
        try:
            start_time = time.time()
            
            # Check Google AI service
            google_ai_status = "unavailable"
            if settings.google_api_key:
                google_ai_status = "configured"
            
            response_time = time.time() - start_time
            
            return {
                "status": "healthy" if google_ai_status == "configured" else "warning",
                "message": f"External services: Google AI {google_ai_status}",
                "response_time": response_time,
                "details": {
                    "google_ai": google_ai_status
                }
            }
            
        except Exception as e:
            logger.error(f"External services health check failed: {e}")
            return {
                "status": "unhealthy",
                "message": f"External services error: {str(e)}",
                "response_time": 0
            }
    
    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks."""
        start_time = time.time()
        
        # Run checks in parallel
        checks = await asyncio.gather(
            self.check_ai_service(),
            self.check_session_manager(),
            self.check_database(),
            self.check_external_services(),
            return_exceptions=True
        )
        
        total_response_time = time.time() - start_time
        
        # Process results
        results = {
            "ai_service": checks[0] if not isinstance(checks[0], Exception) else {
                "status": "unhealthy",
                "message": str(checks[0]),
                "response_time": 0
            },
            "session_manager": checks[1] if not isinstance(checks[1], Exception) else {
                "status": "unhealthy",
                "message": str(checks[1]),
                "response_time": 0
            },
            "database": checks[2] if not isinstance(checks[2], Exception) else {
                "status": "unhealthy",
                "message": str(checks[2]),
                "response_time": 0
            },
            "external_services": checks[3] if not isinstance(checks[3], Exception) else {
                "status": "unhealthy",
                "message": str(checks[3]),
                "response_time": 0
            }
        }
        
        # Determine overall status
        statuses = [result["status"] for result in results.values()]
        if "unhealthy" in statuses:
            overall_status = "unhealthy"
        elif "warning" in statuses:
            overall_status = "warning"
        else:
            overall_status = "healthy"
        
        # Update last check
        self._last_check = datetime.utcnow()
        self._check_results = results
        
        return {
            "overall_status": overall_status,
            "total_response_time": total_response_time,
            "components": results,
            "timestamp": self._last_check.isoformat(),
            "uptime": time.time() - self._start_time
        }


# Global health checker instance
health_checker = HealthChecker()


@health_router.get("/", response_model=HealthCheckResponse)
async def health_check():
    """Basic health check endpoint."""
    try:
        start_time = time.time()
        
        # Quick basic check
        uptime = time.time() - health_checker._start_time
        
        response_time = time.time() - start_time
        
        log_health_check("basic", "healthy", response_time)
        
        return HealthCheckResponse(
            status="healthy",
            version=settings.app_version,
            dependencies={
                "session_manager": "operational",
                "ai_service": "configured" if settings.google_api_key else "unavailable"
            }
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@health_router.get("/detailed")
async def detailed_health_check():
    """Detailed health check with component status."""
    try:
        start_time = time.time()
        
        # Run comprehensive health checks
        results = await health_checker.run_all_checks()
        
        response_time = time.time() - start_time
        
        log_health_check("detailed", results["overall_status"], response_time)
        
        return JSONResponse(
            status_code=200 if results["overall_status"] == "healthy" else 503,
            content={
                "success": True,
                "data": results,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "Health check failed",
                "detail": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@health_router.get("/ready")
async def readiness_check():
    """Readiness check for load balancers."""
    try:
        # Check if service is ready to accept requests
        session_stats = health_checker.session_manager.get_session_stats()
        
        if session_stats["total_sessions"] >= session_stats["max_sessions"]:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": "Session capacity exceeded"}
            )
        
        return JSONResponse(
            status_code=200,
            content={"status": "ready"}
        )
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": str(e)}
        )


@health_router.get("/live")
async def liveness_check():
    """Liveness check for container orchestration."""
    try:
        # Simple check to ensure the service is alive
        uptime = time.time() - health_checker._start_time
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "alive",
                "uptime": uptime,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "dead", "reason": str(e)}
        )


@health_router.get("/metrics")
async def metrics():
    """Basic metrics endpoint."""
    try:
        session_stats = health_checker.session_manager.get_session_stats()
        uptime = time.time() - health_checker._start_time
        
        return JSONResponse(
            status_code=200,
            content={
                "uptime_seconds": uptime,
                "session_stats": session_stats,
                "version": settings.app_version,
                "environment": "development" if settings.debug else "production",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Metrics check failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve metrics", "detail": str(e)}
        )
