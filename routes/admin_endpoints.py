"""
Additional Admin Endpoints for Phase 4
Endpoints for active sessions, model logs, API failures, errors, PDF logs, and user history
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Set
from fastapi import APIRouter, HTTPException, Query, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_database, is_database_available

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Try to import JWT auth for admin endpoints
try:
    from auth.jwt_auth import get_current_admin as get_jwt_admin
    JWT_AVAILABLE = True
except ImportError:
    logger.warning("JWT auth not available for admin endpoints")
    JWT_AVAILABLE = False
    def get_jwt_admin():
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="JWT auth not available")

# WebSocket connection manager for live sessions
class SessionBroadcastManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._polling_task = None
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
        
        # Start polling if this is the first connection
        if len(self.active_connections) == 1:
            self._start_polling()
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
        
        # Stop polling if no connections
        if len(self.active_connections) == 0 and self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    def _start_polling(self):
        """Start polling for session updates"""
        if self._polling_task and not self._polling_task.done():
            return
        
        async def poll_sessions():
            while True:
                try:
                    await asyncio.sleep(5)  # Poll every 5 seconds
                    await self._fetch_and_broadcast_sessions()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in session polling: {e}")
                    await asyncio.sleep(5)
        
        self._polling_task = asyncio.create_task(poll_sessions())
    
    async def _fetch_and_broadcast_sessions(self):
        """Fetch active sessions and broadcast updates"""
        try:
            if not is_database_available():
                return
            
            db = get_database()
            if db is None:
                return
            
            sessions_collection = db.sessions
            thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
            
            sessions = []
            async for session in sessions_collection.find({
                "is_active": True,
                "last_heartbeat": {"$gte": thirty_minutes_ago}
            }).sort("last_heartbeat", -1).limit(100):
                # Convert ObjectId to string for JSON serialization
                if "_id" in session:
                    session["_id"] = str(session["_id"])
                sessions.append(session)
            
            # Broadcast update
            await self.broadcast({
                "type": "session_update",
                "sessions": sessions,
                "count": len(sessions),
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Error fetching sessions for broadcast: {e}")

# Global broadcast manager instance
session_broadcast_manager = SessionBroadcastManager()


@router.get("/sessions/active")
async def get_active_sessions(current_admin=Depends(get_jwt_admin)):
    """
    Get all currently active sessions.
    """
    try:
        if not is_database_available():
            return {"success": True, "data": {"sessions": []}}
        
        db = get_database()
        if db is None:
            return {"success": True, "data": {"sessions": []}}
        
        sessions_collection = db.sessions
        
        # Get active sessions (last heartbeat within 30 minutes)
        thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
        
        sessions = []
        async for session in sessions_collection.find({
            "is_active": True,
            "last_heartbeat": {"$gte": thirty_minutes_ago}
        }).sort("last_heartbeat", -1).limit(100):
            sessions.append(session)
        
        return {
            "success": True,
            "data": {
                "sessions": sessions,
                "count": len(sessions)
            }
        }
    except Exception as e:
        logger.error(f"Error getting active sessions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get active sessions: {str(e)}")


@router.websocket("/sessions/live")
async def websocket_sessions_live(websocket: WebSocket, token: Optional[str] = Query(None)):
    """
    WebSocket endpoint for live session updates.
    Requires admin token as query parameter: ?token=<jwt_token>
    Accepts either JWT token or ADMIN_TOKEN from environment.
    """
    # Verify admin token - try JWT first, then fallback to ADMIN_TOKEN
    import os
    authenticated = False
    auth_error = None
    
    if not token:
        logger.warning("WebSocket connection attempt without token")
        await websocket.close(code=1008, reason="Missing token")
        return
    
    # Try JWT token verification
    try:
        from auth.jwt_auth import verify_token
        jwt_payload = verify_token(token)
        if jwt_payload:
            authenticated = True
            logger.info(f"WebSocket authenticated via JWT for user: {jwt_payload.get('email', 'unknown')}")
        else:
            auth_error = "JWT token invalid or expired"
    except Exception as e:
        auth_error = f"JWT verification error: {str(e)}"
        logger.debug(f"JWT verification failed: {e}")
    
    # Fallback to ADMIN_TOKEN if JWT verification failed
    if not authenticated:
        ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
        if ADMIN_TOKEN and token == ADMIN_TOKEN:
            authenticated = True
            logger.info("WebSocket authenticated via ADMIN_TOKEN")
        else:
            if not auth_error:
                auth_error = "Token does not match ADMIN_TOKEN"
    
    if not authenticated:
        logger.warning(f"WebSocket authentication failed: {auth_error}")
        await websocket.close(code=1008, reason="Unauthorized")
        return
    
    try:
        await session_broadcast_manager.connect(websocket)
        
        # Send initial session list
        try:
            if is_database_available():
                db = get_database()
                if db is not None:
                    sessions_collection = db.sessions
                    thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
                    
                    sessions = []
                    async for session in sessions_collection.find({
                        "is_active": True,
                        "last_heartbeat": {"$gte": thirty_minutes_ago}
                    }).sort("last_heartbeat", -1).limit(100):
                        if "_id" in session:
                            session["_id"] = str(session["_id"])
                        sessions.append(session)
                    
                    await websocket.send_json({
                        "type": "initial",
                        "sessions": sessions,
                        "count": len(sessions)
                    })
        except Exception as e:
            logger.error(f"Error sending initial sessions: {e}")
        
        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for ping or close
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo ping messages
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "keepalive"})
            except WebSocketDisconnect:
                break
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        session_broadcast_manager.disconnect(websocket)


@router.get("/model-logs")
async def get_model_logs(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, description="Limit"),
    current_admin=Depends(get_jwt_admin)
):
    """
    Get model performance logs.
    """
    try:
        if not is_database_available():
            # Use in-memory logs as fallback
            try:
                from analytics.model_logger import get_in_memory_model_logs
                logs = get_in_memory_model_logs(start_date=start_date, end_date=end_date, limit=limit)
                # Convert datetime objects to ISO format strings for JSON serialization
                for log in logs:
                    if "input_timestamp" in log and isinstance(log["input_timestamp"], datetime):
                        log["input_timestamp"] = log["input_timestamp"].isoformat()
                    if "output_timestamp" in log and isinstance(log["output_timestamp"], datetime):
                        log["output_timestamp"] = log["output_timestamp"].isoformat()
                return {
                    "success": True,
                    "data": {
                        "logs": logs,
                        "count": len(logs)
                    }
                }
            except ImportError:
                logger.warning("In-memory model logs not available")
                return {"success": True, "data": {"logs": [], "count": 0}}
        
        db = get_database()
        if db is None:
            # Try in-memory fallback
            try:
                from analytics.model_logger import get_in_memory_model_logs
                logs = get_in_memory_model_logs(start_date=start_date, end_date=end_date, limit=limit)
                # Convert datetime objects to ISO format strings
                for log in logs:
                    if "input_timestamp" in log and isinstance(log["input_timestamp"], datetime):
                        log["input_timestamp"] = log["input_timestamp"].isoformat()
                    if "output_timestamp" in log and isinstance(log["output_timestamp"], datetime):
                        log["output_timestamp"] = log["output_timestamp"].isoformat()
                return {
                    "success": True,
                    "data": {
                        "logs": logs,
                        "count": len(logs)
                    }
                }
            except ImportError:
                return {"success": True, "data": {"logs": [], "count": 0}}
        
        model_logs_collection = db.model_logs
        
        query = {}
        if start_date or end_date:
            query["input_timestamp"] = {}
            if start_date:
                query["input_timestamp"]["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query["input_timestamp"]["$lt"] = end_dt
        
        logs = []
        async for log in model_logs_collection.find(query).sort("input_timestamp", -1).limit(limit):
            # Convert ObjectId to string and datetime to ISO format
            if "_id" in log:
                log["_id"] = str(log["_id"])
            if "input_timestamp" in log and isinstance(log["input_timestamp"], datetime):
                log["input_timestamp"] = log["input_timestamp"].isoformat()
            if "output_timestamp" in log and isinstance(log["output_timestamp"], datetime):
                log["output_timestamp"] = log["output_timestamp"].isoformat()
            logs.append(log)
        
        return {
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        }
    except Exception as e:
        logger.error(f"Error getting model logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get model logs: {str(e)}")


@router.get("/api-failures")
async def get_api_failures(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, description="Limit"),
    current_admin=Depends(get_jwt_admin)
):
    """
    Get API failure logs.
    """
    try:
        if not is_database_available():
            # Use in-memory failures as fallback
            try:
                from analytics.error_logger import get_in_memory_api_failures
                failures = get_in_memory_api_failures(start_date=start_date, end_date=end_date, limit=limit)
                # Convert datetime objects to ISO format strings for JSON serialization
                for failure in failures:
                    if "timestamp" in failure and isinstance(failure["timestamp"], datetime):
                        failure["timestamp"] = failure["timestamp"].isoformat()
                return {
                    "success": True,
                    "data": {
                        "failures": failures,
                        "count": len(failures)
                    }
                }
            except ImportError:
                logger.warning("In-memory API failures not available")
                return {"success": True, "data": {"failures": [], "count": 0}}
        
        db = get_database()
        if db is None:
            # Try in-memory fallback
            try:
                from analytics.error_logger import get_in_memory_api_failures
                failures = get_in_memory_api_failures(start_date=start_date, end_date=end_date, limit=limit)
                # Convert datetime objects to ISO format strings
                for failure in failures:
                    if "timestamp" in failure and isinstance(failure["timestamp"], datetime):
                        failure["timestamp"] = failure["timestamp"].isoformat()
                return {
                    "success": True,
                    "data": {
                        "failures": failures,
                        "count": len(failures)
                    }
                }
            except ImportError:
                return {"success": True, "data": {"failures": [], "count": 0}}
        
        api_failures_collection = db.api_failures
        
        query = {}
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query["timestamp"]["$lt"] = end_dt
        
        failures = []
        async for failure in api_failures_collection.find(query).sort("timestamp", -1).limit(limit):
            # Convert ObjectId to string and datetime to ISO format
            if "_id" in failure:
                failure["_id"] = str(failure["_id"])
            if "timestamp" in failure and isinstance(failure["timestamp"], datetime):
                failure["timestamp"] = failure["timestamp"].isoformat()
            failures.append(failure)
        
        return {
            "success": True,
            "data": {
                "failures": failures,
                "count": len(failures)
            }
        }
    except Exception as e:
        logger.error(f"Error getting API failures: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get API failures: {str(e)}")


@router.get("/errors")
async def get_errors(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, description="Limit"),
    severity: Optional[str] = Query(None, description="Severity filter"),
    current_admin=Depends(get_jwt_admin)
):
    """
    Get error logs.
    """
    try:
        if not is_database_available():
            # Use in-memory errors as fallback
            try:
                from analytics.error_logger import get_in_memory_error_logs
                errors = get_in_memory_error_logs(start_date=start_date, end_date=end_date, limit=limit, severity=severity)
                # Convert datetime objects to ISO format strings for JSON serialization
                for error in errors:
                    if "timestamp" in error and isinstance(error["timestamp"], datetime):
                        error["timestamp"] = error["timestamp"].isoformat()
                return {
                    "success": True,
                    "data": {
                        "errors": errors,
                        "count": len(errors)
                    }
                }
            except ImportError:
                logger.warning("In-memory error logs not available")
                return {"success": True, "data": {"errors": [], "count": 0}}
        
        db = get_database()
        if db is None:
            # Try in-memory fallback
            try:
                from analytics.error_logger import get_in_memory_error_logs
                errors = get_in_memory_error_logs(start_date=start_date, end_date=end_date, limit=limit, severity=severity)
                # Convert datetime objects to ISO format strings
                for error in errors:
                    if "timestamp" in error and isinstance(error["timestamp"], datetime):
                        error["timestamp"] = error["timestamp"].isoformat()
                return {
                    "success": True,
                    "data": {
                        "errors": errors,
                        "count": len(errors)
                    }
                }
            except ImportError:
                return {"success": True, "data": {"errors": [], "count": 0}}
        
        errors_collection = db.errors
        
        query = {}
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query["timestamp"]["$lt"] = end_dt
        
        if severity:
            query["severity"] = severity
        
        errors = []
        async for error in errors_collection.find(query).sort("timestamp", -1).limit(limit):
            # Convert ObjectId to string and datetime to ISO format
            if "_id" in error:
                error["_id"] = str(error["_id"])
            if "timestamp" in error and isinstance(error["timestamp"], datetime):
                error["timestamp"] = error["timestamp"].isoformat()
            errors.append(error)
        
        return {
            "success": True,
            "data": {
                "errors": errors,
                "count": len(errors)
            }
        }
    except Exception as e:
        logger.error(f"Error getting errors: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get errors: {str(e)}")


@router.get("/pdf-logs")
async def get_pdf_logs(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, description="Limit"),
    current_admin=Depends(get_jwt_admin)
):
    """
    Get PDF generation logs.
    """
    try:
        if not is_database_available():
            return {"success": True, "data": {"logs": []}}
        
        db = get_database()
        if db is None:
            return {"success": True, "data": {"logs": []}}
        
        pdf_logs_collection = db.pdf_logs
        
        query = {}
        if start_date or end_date:
            query["render_start"] = {}
            if start_date:
                query["render_start"]["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query["render_start"]["$lt"] = end_dt
        
        logs = []
        async for log in pdf_logs_collection.find(query).sort("render_start", -1).limit(limit):
            logs.append(log)
        
        return {
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        }
    except Exception as e:
        logger.error(f"Error getting PDF logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get PDF logs: {str(e)}")


@router.get("/users/{user_id}/history")
async def get_user_history(
    user_id: str,
    current_admin=Depends(get_jwt_admin)
):
    """
    Get user diagnosis history.
    """
    try:
        if not is_database_available():
            return {"success": True, "data": {"sessions": [], "diagnoses": []}}
        
        db = get_database()
        if db is None:
            return {"success": True, "data": {"sessions": [], "diagnoses": []}}
        
        # Get sessions for this user (by visitor_id or user_id)
        sessions_collection = db.sessions
        sessions = []
        async for session in sessions_collection.find({
            "$or": [
                {"visitor_id": user_id},
                {"user_id": user_id}
            ]
        }).sort("started_at", -1):
            sessions.append(session)
        
        # Get diagnoses for these sessions
        session_ids = [s.get("session_id") for s in sessions]
        reports_collection = db.reports
        
        diagnoses = []
        if session_ids:
            async for report in reports_collection.find({
                "sessionId": {"$in": session_ids}
            }).sort("timestamp", -1):
                diagnoses.append(report)
        
        return {
            "success": True,
            "data": {
                "sessions": sessions,
                "diagnoses": diagnoses,
                "session_count": len(sessions),
                "diagnosis_count": len(diagnoses)
            }
        }
    except Exception as e:
        logger.error(f"Error getting user history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get user history: {str(e)}")

