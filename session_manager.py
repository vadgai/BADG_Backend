"""
Session management for VADG API.
Handles session storage, validation, and cleanup with proper security measures.
"""

import time
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from threading import Lock
import asyncio

from .models import SessionData
from .config import get_settings
from .logging_config import get_logger, log_session_event
from .exceptions import SessionNotFoundError, InvalidPatientDataError

logger = get_logger("session_manager")
settings = get_settings()


class SessionManager:
    """Thread-safe session manager with automatic cleanup."""
    
    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}
        self._lock = Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """Start background task for session cleanup."""
        if not self._cleanup_task or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_sessions())
    
    async def _cleanup_sessions(self):
        """Background task to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                await self.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session cleanup task: {e}")
    
    def create_session(self, patient_data: Dict[str, Any]) -> str:
        """
        Create a new session with patient data.
        
        Args:
            patient_data: Patient information dictionary
            
        Returns:
            Session ID string
            
        Raises:
            InvalidPatientDataError: If patient data is invalid
        """
        try:
            # Validate required fields
            if not patient_data.get("name"):
                raise InvalidPatientDataError("Patient name is required", "name")
            
            if not patient_data.get("symptoms"):
                raise InvalidPatientDataError("Symptoms are required", "symptoms")
            
            # Generate unique session ID
            session_id = str(uuid.uuid4())
            
            # Create session data
            session_data = SessionData(
                name=patient_data["name"],
                age=patient_data.get("age"),
                gender=patient_data.get("gender", "unknown"),
                symptoms=patient_data["symptoms"] if isinstance(patient_data["symptoms"], list) else [patient_data["symptoms"]],
                chat_history=[],
                question_count=0
            )
            
            # Store session
            with self._lock:
                # Check session limit
                if len(self._sessions) >= settings.max_sessions:
                    # Remove oldest session
                    oldest_session = min(
                        self._sessions.items(),
                        key=lambda x: x[1].created_at
                    )
                    del self._sessions[oldest_session[0]]
                    logger.warning(f"Removed oldest session {oldest_session[0]} due to limit")
                
                self._sessions[session_id] = session_data
            
            log_session_event(session_id, "created", patient_name=patient_data["name"])
            logger.info(f"Created session {session_id} for patient {patient_data['name']}")
            
            return session_id
            
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            raise InvalidPatientDataError(f"Failed to create session: {str(e)}")
    
    def get_session(self, session_id: str) -> SessionData:
        """
        Get session data by ID.
        
        Args:
            session_id: Session ID string
            
        Returns:
            SessionData object
            
        Raises:
            SessionNotFoundError: If session not found
        """
        with self._lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(session_id)
            
            session = self._sessions[session_id]
            
            # Update last activity
            session.last_activity = datetime.utcnow()
            
            return session
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> None:
        """
        Update session data.
        
        Args:
            session_id: Session ID string
            updates: Dictionary of updates to apply
            
        Raises:
            SessionNotFoundError: If session not found
        """
        with self._lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(session_id)
            
            session = self._sessions[session_id]
            
            # Apply updates
            for key, value in updates.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            
            # Update last activity
            session.last_activity = datetime.utcnow()
            
            log_session_event(session_id, "updated", updates=list(updates.keys()))
    
    def add_chat_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """
        Add a message to session chat history.
        
        Args:
            session_id: Session ID string
            message: Message dictionary with 'user' or 'bot' key
        """
        with self._lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(session_id)
            
            session = self._sessions[session_id]
            session.chat_history.append(message)
            session.last_activity = datetime.utcnow()
            
            log_session_event(session_id, "chat_message_added", message_type=list(message.keys())[0])
    
    def increment_question_count(self, session_id: str) -> None:
        """
        Increment question count for session.
        
        Args:
            session_id: Session ID string
        """
        with self._lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(session_id)
            
            session = self._sessions[session_id]
            session.question_count += 1
            session.last_activity = datetime.utcnow()
    
    def delete_session(self, session_id: str) -> None:
        """
        Delete a session.
        
        Args:
            session_id: Session ID string
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                log_session_event(session_id, "deleted")
                logger.info(f"Deleted session {session_id}")
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        current_time = datetime.utcnow()
        expired_sessions = []
        
        with self._lock:
            for session_id, session in self._sessions.items():
                if current_time - session.last_activity > timedelta(seconds=settings.session_timeout):
                    expired_sessions.append(session_id)
        
        # Delete expired sessions
        for session_id in expired_sessions:
            self.delete_session(session_id)
            log_session_event(session_id, "expired_cleanup")
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
        
        return len(expired_sessions)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """
        Get session statistics.
        
        Returns:
            Dictionary with session statistics
        """
        with self._lock:
            current_time = datetime.utcnow()
            active_sessions = 0
            expired_sessions = 0
            
            for session in self._sessions.values():
                if current_time - session.last_activity <= timedelta(seconds=settings.session_timeout):
                    active_sessions += 1
                else:
                    expired_sessions += 1
            
            return {
                "total_sessions": len(self._sessions),
                "active_sessions": active_sessions,
                "expired_sessions": expired_sessions,
                "max_sessions": settings.max_sessions,
                "session_timeout": settings.session_timeout
            }
    
    def get_all_sessions(self) -> Dict[str, SessionData]:
        """
        Get all sessions (for debugging purposes).
        
        Returns:
            Dictionary of all sessions
        """
        with self._lock:
            return self._sessions.copy()
    
    def close(self):
        """Close session manager and cleanup resources."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        logger.info("Session manager closed")


# Global session manager instance
session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    """Get the global session manager instance."""
    return session_manager
