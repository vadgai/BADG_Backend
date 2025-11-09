# app.py
"""
VADG API - AI-Powered Health Insights and Disease Prediction Platform
Main FastAPI application with comprehensive error handling, security, and monitoring.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional, Union

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator

# Import internal modules
from symptom_processing.symptom import hybrid_symptom_extraction
from Followup_Generation.followup import get_followup_for_diagnosis
from symptom_mapping.mapping import get_disease_symptom_mapping
from diagnosis_report.report import final_report

# Import database and new route modules
from database.connection import connect_to_mongodb, close_mongodb_connection
from routes import admin, form, contact, report_analyzer, translate, translateProxy, localizedReport
from routes.admin_analytics import router as admin_analytics_router

# Import new modules (commented out until modules are created)
# from models import DiagnosisRequest, DiagnosisResponse, ErrorResponse, HealthCheckResponse
# from config import get_settings, get_cors_origins
# from logging_config import setup_logging, get_logger
# from middleware import (
#     RequestIDMiddleware, SecurityHeadersMiddleware, LoggingMiddleware,
#     RateLimitMiddleware, HealthCheckMiddleware, CORSSecurityMiddleware
# )
# from session_manager import get_session_manager
# from api_utils import (
#     create_success_response, create_error_response, validate_patient_data,
#     sanitize_input, extract_request_info, handle_ai_error
# )
# from exceptions import VADGException, create_http_exception
# from health_check import health_router

# Load environment variables
load_dotenv()

# Ensure local package imports (e.g., `database.models`, `routes.*`) resolve when running locally
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Initialize logging
logger = logging.getLogger("uvicorn.error")

# Create FastAPI app
app = FastAPI(
    title="VADG API",
    description="AI-Powered Health Insights and Disease Prediction Platform",
    version="2.0.1"
)

# CORS configuration
allowed = os.getenv(
    "ALLOWED_ORIGINS", 
    "https://vadg.in,http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
)
ALLOWED_ORIGINS = [origin.strip() for origin in allowed.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=4)

# In-memory session store (hybrid approach with MongoDB)
session_store: Dict[str, dict] = {}


#
# --- Application Lifecycle Events ---
#
@app.on_event("startup")
async def startup_event():
    """Initialize database connection and other startup tasks"""
    logger.info("🚀 Starting VADG API...")
    logger.info("PORT: %s", os.getenv("PORT", "8080"))
    logger.info("Environment: %s", os.getenv("ENVIRONMENT", "development"))
    
    # Try MongoDB connection with timeout
    logger.info("Attempting MongoDB connection...")
    try:
        import asyncio
        # Set a timeout for MongoDB connection
        await asyncio.wait_for(connect_to_mongodb(), timeout=5.0)
        logger.info("✅ MongoDB connected")
    except asyncio.TimeoutError:
        logger.warning("MongoDB connection timeout - continuing without database")
    except Exception as e:
        logger.warning(f"MongoDB connection skipped: {e}")
        logger.info("Continuing without MongoDB (core features will still work)")
    
    logger.info("✅ Startup complete - Ready to serve requests")


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connections and cleanup"""
    logger.info("🔄 Shutting down VADG API...")
    await close_mongodb_connection()
    logger.info("✅ Shutdown complete")


#
# --- Include Route Modules ---
#
# Include admin analytics routers and form routes
app.include_router(admin.public_router)
app.include_router(admin.router)
app.include_router(admin_analytics_router)
app.include_router(form.router)
app.include_router(contact.router)
app.include_router(report_analyzer.router)
app.include_router(translate.router, prefix="/api/translate")
app.include_router(translateProxy.router, prefix="/internal/translate")
app.include_router(localizedReport.router, prefix="/api/localize-report")


#
# --- Middleware: log request bodies (for debugging) ---
#
@app.middleware("http")
async def log_request_body_middleware(request: Request, call_next):
    """
    Logs the body for POST/PUT/PATCH requests for debugging purposes.
    WARNING: Do not keep detailed body logging in production for PII/security reasons.
    """
    try:
        if request.method in ("POST", "PUT", "PATCH"):
            raw = await request.body()
            text = raw.decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(text) if text else None
            except Exception:
                parsed = text
            logger.info("Incoming request %s %s body=%s", request.method, request.url.path, parsed)
            # Re-create the request stream so downstream can read it
            request._body = raw  # internal usage; acceptable for debugging
    except Exception as e:
        logger.warning("Could not log request body: %s", e)
    response = await call_next(request)
    return response


#
# --- Exception handler for validation errors (gives structured 422) ---
#
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Return a structured 422 with validation detail and raw body for debugging.
    """
    try:
        raw = await request.body()
        raw_text = raw.decode("utf-8", errors="ignore")
        try:
            parsed_raw = json.loads(raw_text) if raw_text else None
        except Exception:
            parsed_raw = raw_text
    except Exception:
        parsed_raw = "<could not read body>"

    logger.error("Validation error for %s %s: %s; body=%s", request.method, request.url.path, exc.errors(), parsed_raw)
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "body": parsed_raw})


#
# --- Tolerant Pydantic model for symptom submission ---
#
class LocationData(BaseModel):
    """Location data for patient."""
    country: Optional[str] = "India"
    state: Optional[str] = None
    city: Optional[str] = None

class DiagnosisRequest(BaseModel):
    """Request model for symptom submission and diagnosis initiation."""
    name: Optional[str] = None
    age: Optional[Union[int, str]] = None
    gender: Optional[str] = None
    symptoms: Optional[Union[List[str], str]] = None
    patient_id: Optional[str] = None
    notes: Optional[str] = None
    
    # New enhanced fields
    weight: Optional[float] = None
    height: Optional[float] = None
    occupation: Optional[str] = None
    location: Optional[LocationData] = None
    physical_activity: Optional[str] = None
    diet_type: Optional[str] = None

    @validator("age", pre=True, always=True)
    def parse_age(cls, v):
        """Parse and validate age input."""
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                if "." in v:
                    return int(float(v))
                return int(v)
            except (ValueError, TypeError):
                return v
        return v

    @validator("symptoms", pre=True, always=True)
    def parse_symptoms(cls, v):
        """Parse and normalize symptoms input."""
        if v is None:
            return []
        if isinstance(v, list):
            return [str(s).strip() for s in v if s is not None and str(s).strip()]
        if isinstance(v, str):
            if "\n" in v:
                parts = [p.strip() for p in v.split("\n") if p.strip()]
                return parts
            if "," in v:
                parts = [p.strip() for p in v.split(",") if p.strip()]
                return parts
            if v.strip():
                return [v.strip()]
            return []
        return [str(v).strip()] if v else []
    
    @validator("location", pre=True, always=True)
    def parse_location(cls, v):
        """Parse and normalize location input."""
        if v is None:
            return LocationData(country="India")
        if isinstance(v, dict):
            return LocationData(**v)
        return v

    def symptoms_as_text(self) -> str:
        """Convert symptoms list to text format for legacy functions."""
        if not self.symptoms:
            return ""
        if isinstance(self.symptoms, list):
            return "\n".join(self.symptoms)
        return str(self.symptoms)


#
# --- Routes ---
#
@app.get("/")
async def root():
    """Root endpoint for health checks"""
    return {
        "status": "ok",
        "message": "VADG API is running",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "symptom": "/symptom",
            "followup": "/followup/{session_id}"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and testing"""
    from datetime import datetime
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "service": "VADG API",
        "components": {
            "api": "operational",
            "websocket": "operational",
            "database": "operational" if session_store is not None else "degraded"
        }
    }

@app.options("/symptom")
async def options_symptom():
    """Handle OPTIONS requests for /symptom endpoint"""
    return JSONResponse(content={}, status_code=200)

@app.post("/symptom")
async def submit_symptom(payload: DiagnosisRequest):
    """
    Submit patient symptoms for AI analysis with comprehensive error handling.
    
    Args:
        payload: Validated patient data including name, age, gender, and symptoms
        
    Returns:
        Dictionary with session ID and processing status
    """
    try:
        # Log the incoming request
        logger.info("Processing symptom submission: name=%s age=%s gender=%s", 
                   payload.name, payload.age, payload.gender)

        # Normalize and extract symptoms
        symptoms_text = payload.symptoms_as_text()

        # Use AI symptom extraction with error handling
        try:
            extracted_symptoms = hybrid_symptom_extraction(symptoms_text)
        except Exception as e:
            # If extraction fails, log and proceed with the normalized list fallback
            logger.warning("hybrid_symptom_extraction failed: %s. Falling back to normalized symptoms list.", e)
            extracted_symptoms = payload.symptoms if isinstance(payload.symptoms, list) else (payload.symptoms_as_text().split("\n") if payload.symptoms_as_text() else [])

        # Create session with enhanced patient data
        session_id = str(uuid.uuid4())
        session_store[session_id] = {
            "name": payload.name or "Unknown",
            "age": payload.age,
            "gender": payload.gender or "unknown",
            "symptoms": extracted_symptoms,
            "chat_history": [],
            "question_count": 0,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            # Enhanced patient data
            "weight": payload.weight,
            "height": payload.height,
            "occupation": payload.occupation,
            "location": {
                "country": payload.location.country if payload.location else "India",
                "state": payload.location.state if payload.location else None,
                "city": payload.location.city if payload.location else None
            },
            "physical_activity": payload.physical_activity,
            "diet_type": payload.diet_type
        }

        logger.info("Created session %s for patient %s (age=%s)", session_id, payload.name, payload.age)

        return {
            "message": "Symptoms submitted successfully",
            "status": "symptom_submitted",
            "session_id": session_id
        }
        
    except Exception as e:
        logger.exception("Unexpected error processing symptom submission: %s", e)
        raise HTTPException(
            status_code=500, 
            detail="Internal server error processing symptom submission"
        )


@app.options("/debug_sessions")
async def options_debug_sessions():
    """Handle OPTIONS requests for /debug_sessions endpoint"""
    return JSONResponse(content={}, status_code=200)

@app.get("/debug_sessions")
def debug_sessions():
    """Get debug information about all sessions."""
    try:
        return {
            "session_count": len(session_store),
            "session_ids": list(session_store.keys()),
            "active_sessions": [
                {
                    "session_id": sid,
                    "name": session.get("name", "Unknown"),
                    "age": session.get("age"),
                    "gender": session.get("gender", "unknown"),
                    "symptom_count": len(session.get("symptoms", [])),
                    "question_count": session.get("question_count", 0),
                    "created_at": session.get("created_at"),
                    "last_activity": session.get("last_activity")
                }
                for sid, session in session_store.items()
            ]
        }
    except Exception as e:
        logger.error("Error getting debug sessions: %s", e)
        return {"error": "Failed to get session information"}

@app.options("/session/{session_id}")
async def options_session(session_id: str):  # pylint: disable=unused-argument
    """Handle OPTIONS requests for /session/{session_id} endpoint"""
    return JSONResponse(content={}, status_code=200)

@app.get("/session/{session_id}")
async def get_session_data(session_id: str):
    """Get session data by ID."""
    try:
        if session_id not in session_store:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = session_store[session_id]
        
        return {
            "session_id": session_id,
            "name": session.get("name", "Unknown"),
            "age": session.get("age"),
            "gender": session.get("gender", "unknown"),
            "symptoms": session.get("symptoms", []),
            "chat_history": session.get("chat_history", []),
            "question_count": session.get("question_count", 0),
            "created_at": session.get("created_at"),
            "last_activity": session.get("last_activity")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting session %s: %s", session_id, e)
        raise HTTPException(status_code=404, detail="Session not found")


#
# --- Robust WebSocket follow-up handler (single handler) ---
#
@app.websocket("/followup/{session_id}")
async def followup_handler(websocket: WebSocket, session_id: str):
    """
    Robust websocket followup handler:
      - Runs generator in threadpool (non-blocking)
      - Logs raw generator output (type + repr)
      - If generator output is unexpected, sends an error + fallback question
      - Maps client answers A/B/C/D to option text (avoids storing raw test strings)
      - Keeps the socket open on recoverable errors so client can continue
    """
    logger.info("="*80)
    logger.info("🔌 WEBSOCKET CONNECTION ATTEMPT")
    logger.info(f"   Session ID: {session_id}")
    logger.info(f"   Client: {websocket.client}")
    logger.info("="*80)
    
    try:
        await websocket.accept()
        logger.info("✅ WebSocket accepted for session %s", session_id)

        if session_id not in session_store:
            logger.error("❌ Invalid session_id on websocket connect: %s", session_id)
            logger.error("   Available sessions: %s", list(session_store.keys()))
            await websocket.send_json({"error": "Invalid session_id"})
            await websocket.close(code=1008, reason="Invalid session_id")
            return
        
        logger.info("✅ Session found. Patient data: age=%s, gender=%s, symptoms=%s", 
                   session_store[session_id].get('age'),
                   session_store[session_id].get('gender'),
                   len(session_store[session_id].get('symptoms', [])))

        session = session_store[session_id]
        age = session.get("age")
        gender = session.get("gender")
        symptoms = session.get("symptoms")
        chat_history = session.get("chat_history", [])
        # question_count = session.get("question_count", 0)  # Unused for now
        
        # Get enhanced patient data
        weight = session.get("weight")
        height = session.get("height")
        occupation = session.get("occupation")
        location = session.get("location")
        physical_activity = session.get("physical_activity")
        diet_type = session.get("diet_type")

        # initial ping
        logger.info("📤 Sending 'connected' status to client")
        await websocket.send_json({"status": "connected"})
        logger.info("✅ Client should now see 'Connected' indicator")

        # helper to run blocking generator in threadpool
        async def run_generator(func, *args, **kwargs):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))

        # Check if questions have already been asked (reconnection scenario)
        existing_question_count = session.get("question_count", 0)
        
        # If max questions already reached, send ready_for_diagnosis immediately
        if existing_question_count >= 12:
            logger.info("Session %s: Max questions (%d) already reached. Sending ready_for_diagnosis.", 
                       session_id, existing_question_count)
            await websocket.send_json({"message": "Maximum questions reached, generating diagnosis", "status": "ready_for_diagnosis"})
            await websocket.close(code=1000, reason="Max questions reached")
            return
        
        if existing_question_count > 0:
            logger.info("Session %s: Reconnection detected (question_count=%d), skipping initial question generation", 
                       session_id, existing_question_count)
            # Wait for client message instead of generating new question
            logger.info("Waiting for client to continue conversation...")
        else:
            # Generate initial followup safely with enhanced patient data
            logger.info("="*80)
            logger.info("📝 GENERATING INITIAL FOLLOW-UP QUESTION")
            logger.info(f"   Patient age: {age}, gender: {gender}")
            logger.info(f"   Symptoms: {symptoms}")
            logger.info(f"   Enhanced data: weight={weight}, height={height}")
            logger.info(f"   Occupation: {occupation}, Activity: {physical_activity}")
            logger.info(f"   Location: {location}")
            logger.info("="*80)
        
        if existing_question_count == 0:
            try:
                raw_response = await run_generator(
                    get_followup_for_diagnosis, 
                    age, gender, symptoms, chat_history,
                    1,  # max_retries
                    weight, height, occupation, location, physical_activity, diet_type
                )
                logger.info("✅ Initial question generated successfully")
            except Exception as e:
                # On AI error, synthesize a fallback response and KEEP the socket open
                logger.error("❌ get_followup_for_diagnosis FAILED during initial generation for session %s", session_id)
                logger.exception("Full error traceback: %s", e)
                await websocket.send_json({"warning": "AI model failed, using a safe fallback question."})
                raw_response = {
                    "Question": "Fallback: Does the patient currently have a fever?",
                    "A": "Yes",
                    "B": "No",
                    "C": "Unsure"
                }

            # Log raw response for debugging
            logger.info("Raw generator response (type=%s) for session %s: %s", type(raw_response).__name__, session_id, repr(raw_response)[:2000])

            # If response is valid dict with "Question"
            if isinstance(raw_response, dict) and "Question" in raw_response:
                # Initialize question count if not exists
                if "question_count" not in session:
                    session["question_count"] = 0
                session["question_count"] += 1
                session["last_options"] = raw_response
                chat_history.append({"bot": raw_response["Question"]})
                logger.info("Session %s: Asked question #%d", session_id, session["question_count"])
                await websocket.send_json({
                    "question": raw_response["Question"],
                    "options": [
                        {"key": k, "value": v}
                        for k, v in raw_response.items() if k in ["A", "B", "C", "D"]
                    ],
                    "status": "waiting_for_answer"
                })
            else:
                # unexpected format: log and provide fallback, don't close
                logger.error("Unexpected generator output for session %s: type=%s repr=%s", session_id, type(raw_response).__name__, repr(raw_response)[:2000])
                await websocket.send_json({"error": "Unable to generate initial question. Server logged the response for debugging."})
                await websocket.send_json({
                    "question": "Fallback: Is the patient improving after initial care? (A: Yes, B: No, C: Not sure)",
                    "options": [{"key": "A", "value": "Yes"}, {"key": "B", "value": "No"}, {"key": "C", "value": "Not sure"}],
                    "status": "waiting_for_answer"
                })

        # Conversation loop
        while True:
            try:
                client_msg = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("Session %s disconnected by client.", session_id)
                break
            except Exception as e:
                logger.exception("Error receiving message for session %s: %s", session_id, e)
                await websocket.send_json({"error": "Error receiving message"})
                await websocket.close(code=1011, reason="Receive error")
                break

            logger.info("Received message for session %s: %s", session_id, client_msg)
            
            # CRITICAL: Ignore heartbeat/ping messages - they are NOT patient answers!
            try:
                msg_data = json.loads(client_msg)
                if isinstance(msg_data, dict) and msg_data.get("type") == "ping":
                    logger.debug("Heartbeat ping received from session %s - ignoring", session_id)
                    await websocket.send_json({"type": "pong"})
                    continue
            except json.JSONDecodeError:
                pass  # Not JSON, treat as regular answer
            
            client_msg_clean = client_msg.strip().upper()

            # Map A/B/C/D to option text when possible
            last_response = session.get("last_options", {})
            mapped_answer = None
            if client_msg_clean in ("A", "B", "C", "D"):
                mapped_answer = last_response.get(client_msg_clean)
            else:
                # loose matching against option texts (case-insensitive)
                for key, value in last_response.items():
                    if isinstance(value, str) and client_msg_clean in value.upper():
                        mapped_answer = value
                        break

            if mapped_answer:
                user_answer = mapped_answer
            else:
                # If mapping fails, sanitize and append (or choose to ignore)
                logger.warning("Unmapped response from client for session %s: %s; appending raw (sanitized).", session_id, client_msg_clean)
                user_answer = client_msg_clean  # or skip appending entirely if you prefer

            # Add user answer to chat history
            chat_history.append({"user": user_answer})
            session["chat_history"] = chat_history
            
            # Get updated chat history from session to ensure persistence
            updated_chat_history = session.get("chat_history", [])
            
            # SAFETY CHECK: Detect repetitive questions BEFORE generating next one
            if len(updated_chat_history) >= 6:
                # Get last 3 bot questions
                last_bot_questions = [msg.get("bot", "") for msg in updated_chat_history[-6:] if isinstance(msg, dict) and "bot" in msg]
                if len(last_bot_questions) >= 3:
                    # Check if last 3 questions are identical
                    if len(set(last_bot_questions[-3:])) == 1:
                        logger.warning("Session %s: Detected 3 identical questions in a row, forcing diagnosis", session_id)
                        await websocket.send_json({"message": "Maximum questions reached, generating diagnosis", "status": "ready_for_diagnosis"})
                        await websocket.close(code=1000, reason="Repetitive questions detected")
                        break

            # Call generator in threadpool for next response with enhanced data
            try:
                next_raw = await run_generator(
                    get_followup_for_diagnosis, 
                    age, gender, symptoms, updated_chat_history,
                    1,  # max_retries
                    weight, height, occupation, location, physical_activity, diet_type
                )
            except Exception as e:
                logger.exception("get_followup_for_diagnosis error mid-conversation for session %s: %s", session_id, e)
                await websocket.send_json({"error": "Failed to process answer (server error)."})
                await websocket.close(code=1011, reason="Internal processing error")
                break

            logger.info("Raw next response (type=%s) for session %s: %s", type(next_raw).__name__, session_id, repr(next_raw)[:2000])

            # Handle different generator outputs safely
            if isinstance(next_raw, str) and "ready for diagnosis" in next_raw.lower():
                await websocket.send_json({"message": "Diagnosis is ready", "status": "ready_for_diagnosis"})
                await websocket.close(code=1000, reason="Diagnosis ready")
                break
            elif isinstance(next_raw, dict) and "Question" in next_raw:
                # Check question count limit before asking another question
                current_question_count = session.get("question_count", 0)
                if current_question_count >= 12:  # Set max to 12 questions
                    logger.info("Session %s: Reached maximum questions (%d), forcing diagnosis", session_id, current_question_count)
                    await websocket.send_json({"message": "Maximum questions reached, generating diagnosis", "status": "ready_for_diagnosis"})
                    await websocket.close(code=1000, reason="Max questions reached")
                    break
                
                # Increment question count
                session["question_count"] = current_question_count + 1
                
                # Add bot question to chat history
                updated_chat_history.append({"bot": next_raw["Question"]})
                session["chat_history"] = updated_chat_history
                
                # Update session with last options
                session["last_options"] = next_raw
                
                # Update local chat_history reference
                chat_history = updated_chat_history
                
                logger.info("Session %s: Asked question #%d", session_id, session["question_count"])
                
                await websocket.send_json({
                    "question": next_raw["Question"],
                    "options": [
                        {"key": k, "value": v}
                        for k, v in next_raw.items() if k in ["A", "B", "C", "D"]
                    ],
                    "status": "waiting_for_answer"
                })
            else:
                logger.error("Unexpected format from generator mid-conversation for session %s: type=%s repr=%s", session_id, type(next_raw).__name__, repr(next_raw)[:2000])
                await websocket.send_json({"error": "Unexpected format from generator. Please answer the fallback question."})
                await websocket.send_json({
                    "question": "Fallback: Is the patient improving after initial care? (A: Yes, B: No, C: Not sure)",
                    "options": [{"key": "A", "value": "Yes"}, {"key": "B", "value": "No"}, {"key": "C", "value": "Not sure"}],
                    "status": "waiting_for_answer"
                })
                # keep connection open for fallback answer

    except WebSocketDisconnect:
        logger.info("Session %s disconnected (outer catch).", session_id)
    except Exception as e:
        logger.exception("Unhandled websocket error for session %s: %s", session_id, e)
        try:
            await websocket.send_json({"error": "Internal server error during followup"})
            await websocket.close(code=1011, reason="Unhandled server error")
        except Exception:
            pass
    finally:
        logger.info("Connection closed for session %s", session_id)


@app.options("/generate_report/{session_id}")
async def options_generate_report(session_id: str):  # pylint: disable=unused-argument
    """Handle OPTIONS requests for /generate_report/{session_id} endpoint"""
    return JSONResponse(content={}, status_code=200)

@app.get("/generate_report/{session_id}")
async def generate_report(session_id: str, lang: str = "en"):
    """
    Generate medical report for a session with optional language localization.
    
    Args:
        session_id: The session ID
        lang: Target language code (en, hi, ta, te, bn, kn). Default: "en"
    
    Returns:
        Report in requested language (localized if lang != "en")
    """
    try:
        if session_id not in session_store:
            raise HTTPException(status_code=404, detail="Session not found")

        session = session_store[session_id]
        name = session.get("name", "Unknown")
        age = session.get("age")
        gender = session.get("gender")
        symptoms = session.get("symptoms")
        chat_history = session.get("chat_history", [])

        # Get enhanced patient data from session
        weight = session.get("weight")
        height = session.get("height")
        occupation = session.get("occupation")
        location = session.get("location")
        physical_activity = session.get("physical_activity")
        diet_type = session.get("diet_type")
        
        # Get mapped diseases and final report using thread pool with enhanced patient data
        try:
            loop = asyncio.get_event_loop()
            mapped_diseases = await loop.run_in_executor(
                executor,
                get_disease_symptom_mapping,
                age, gender, symptoms, chat_history, weight, height, occupation, location, physical_activity, diet_type
            )
            
            report = await loop.run_in_executor(
                executor,
                final_report,
                age, gender, symptoms, chat_history, mapped_diseases,
                weight, height, occupation, location, physical_activity, diet_type
            )
        except Exception as ai_error:
            logger.error(f"AI processing error in generate_report: {ai_error}")
            raise HTTPException(
                status_code=500, 
                detail="AI processing failed while generating report"
            )

        if report:
            # Parse report if it's a JSON string
            if isinstance(report, str):
                try:
                    import json
                    report = json.loads(report)
                except:
                    # If parsing fails, use as is
                    pass
            
            # Localize report if language is not English
            if lang and lang.lower() != "en":
                try:
                    from utils.localized_report import localize_diagnosis_report
                    
                    logger.info(f"Localizing report for session {session_id} to language: {lang}")
                    
                    # Get the actual report dict (may be nested)
                    report_dict = report.get("report", report) if isinstance(report, dict) else report
                    
                    # Localize the report
                    localized = await localize_diagnosis_report(report_dict, lang)
                    
                    # Replace report with localized version
                    if isinstance(report, dict) and "report" in report:
                        report["report"] = localized
                    else:
                        report = localized
                    
                    logger.info(f"✅ Report localized successfully to {lang}")
                    
                except Exception as localization_error:
                    # Log error but continue with English version (safe fallback)
                    logger.warning(
                        f"Failed to localize report to {lang}: {str(localization_error)}. "
                        f"Returning English version."
                    )
            
            # Update session with report status
            session["report_generated"] = True
            session["report_timestamp"] = datetime.utcnow().isoformat()
            session["report_language"] = lang
            
            response_data = {
                "patient_details": {
                    "name": name,
                    "age": age,
                    "gender": gender
                },
                "report": report,
                "session_id": session_id,
                "language": lang,
                "generated_at": datetime.utcnow().isoformat()
            }
            return JSONResponse(content=response_data, status_code=200)
        else:
            raise HTTPException(status_code=500, detail="Failed to generate medical report")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generating report for session %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail="Internal Server Error generating report")
