# app.py
"""
VADG API - AI-Powered Health Insights and Disease Prediction Platform
Main FastAPI application with comprehensive error handling, security, and monitoring.
"""

import asyncio
import json
import logging
import math
import os
import re
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
from diagnosis_methods.patient_state import initialize_patient_state
from symptom_extractor_v5 import extract_initial_symptoms
from Followup_Generation.followup_v5 import (
    get_followup_for_diagnosis_v5,
    update_state_with_answer_v5,
)
from diagnosis_methods.state_followup import build_contextual_fallback_mcq
from diagnosis_rule_engine_v5 import get_final_diagnosis_v5
from diagnosis_report.report import final_report, build_next_diagnostic_steps

# Import database and new route modules
from database.connection import connect_to_mongodb, close_mongodb_connection
from routes import admin, form, contact, report_analyzer, translate, disease_info, analytics, careers
# NOTE: IndicTrans2 integration disabled - using Google/Gemini instead
# from routes import translateProxy, localizedReport
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

# Disease info prompt (used by disease info route)
DISEASE_INFO_PROMPT = """You are a medical expert. Provide accurate, patient-friendly information about: {disease_name}
Please provide information in {language} language covering:
1) What is this disease? (Brief description)
2) What causes it? (Etiology)
3) Common symptoms and signs
4) How is it diagnosed?
5) Treatment options (medical and lifestyle)
6) Prevention methods
7) Home remedies (if applicable)
8) When to see a doctor (red flags)

Format your response in clear, easy-to-understand language for patients.
Use bullet points and sections for readability.
Be accurate but avoid unnecessary medical jargon."""

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

# Symptom-driven follow-up constraints
MIN_FOLLOWUP_QUESTIONS = 4
MAX_FOLLOWUP_QUESTIONS = 12

_GENERIC_RUNTIME_MARKERS = (
    "getting worse",
    "share more details",
    "any other symptoms",
    "specific clinical",
    "specific finding",
)

_PLACEHOLDER_RUNTIME_MARKERS = (
    "clinically precise question",
    "specific clinical",
    "specific finding",
    "specific option",
    "option a",
    "option b",
    "option c",
)


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
        from database.connection import is_database_available
        # Set a timeout for MongoDB connection
        connected = await asyncio.wait_for(connect_to_mongodb(), timeout=5.0)
        if connected and is_database_available():
            logger.info("✅ MongoDB connected")
        else:
            logger.warning("MongoDB unavailable - continuing with in-memory storage only")
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
app.include_router(careers.router)
app.include_router(report_analyzer.router)
app.include_router(translate.router, prefix="/api/translate")
app.include_router(disease_info.router)
app.include_router(analytics.router)
app.include_router(analytics.telemetry_router)

# NOTE: IndicTrans2 routes disabled - using Google/Gemini translation instead
# app.include_router(translateProxy.router, prefix="/internal/translate")
# app.include_router(localizedReport.router, prefix="/api/localize-report")


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

    @staticmethod
    def _parse_measurement(v, field_name: str):
        """
        Parse height/weight safely.
        Returns None for missing/invalid/unclear values so the diagnosis flow continues.
        """
        if v is None:
            return None
        if isinstance(v, bool):
            return None

        if isinstance(v, str):
            raw = v.strip().lower()
            if raw in {"", "na", "n/a", "none", "null", "unknown", "-"}:
                return None
            cleaned = "".join(ch for ch in raw if ch in "0123456789.+-")
            if cleaned in {"", ".", "+", "-", "+.", "-."}:
                return None
            try:
                numeric = float(cleaned)
            except (ValueError, TypeError):
                return None
        else:
            try:
                numeric = float(v)
            except (ValueError, TypeError):
                return None

        if not math.isfinite(numeric) or numeric <= 0:
            return None

        if field_name == "height":
            # Accept meters/inches and normalize to cm.
            if 0.5 <= numeric <= 2.5:
                numeric *= 100.0
            elif 36 <= numeric <= 96:
                numeric *= 2.54
            if not (90 <= numeric <= 250):
                return None
            return round(numeric, 2)

        if field_name == "weight":
            if not (20 <= numeric <= 400):
                return None
            return round(numeric, 2)

        return numeric

    @validator("weight", pre=True, always=True)
    def parse_weight(cls, v):
        return cls._parse_measurement(v, "weight")

    @validator("height", pre=True, always=True)
    def parse_height(cls, v):
        return cls._parse_measurement(v, "height")

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

        # Use v5 symptom extraction with error handling
        fallback_list = (
            payload.symptoms if isinstance(payload.symptoms, list)
            else (payload.symptoms_as_text().split("\n") if payload.symptoms_as_text() else [])
        )
        try:
            extracted_symptoms = extract_initial_symptoms(symptoms_text, fallback_list)
        except Exception as e:
            # If extraction fails, log and proceed with the normalized list fallback
            logger.warning("extract_initial_symptoms failed: %s. Falling back to normalized symptoms list.", e)
            extracted_symptoms = fallback_list

        # Create session with enhanced patient data
        session_id = str(uuid.uuid4())
        # Initialize v5 patient state for reasoning loop
        patient_state = initialize_patient_state(
            payload.age,
            payload.gender or "unknown",
            extracted_symptoms,
            weight=payload.weight,
            height=payload.height,
        )
        symptom_state = {
            "current_symptoms": list(extracted_symptoms),
            "modifiers": [],
            "modifier_map": {
                "duration": "",
                "onset": "",
                "location": "",
                "quality": "",
                "severity": "",
                "aggravating_factors": [],
                "relieving_factors": [],
                "associated_symptoms": [],
            },
            "red_flags": [],
            "questions_asked": [],
        }
        patient_state["symptom_state"] = symptom_state

        session_store[session_id] = {
            "name": payload.name or "Unknown",
            "age": payload.age,
            "gender": payload.gender or "unknown",
            "symptoms": extracted_symptoms,
            "initial_symptoms": list(extracted_symptoms),
            "raw_symptoms": symptoms_text,
            "chat_history": [],  # kept only for backward compatibility; prompts use structured state
            "symptom_state": symptom_state,
            "diagnostic_trace": [],
            "question_count": 0,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "patient_state": patient_state,
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
                    "structured_symptom_count": len(
                        (session.get("symptom_state") or {}).get("current_symptoms", [])
                    ) if isinstance(session.get("symptom_state"), dict) else 0,
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
            "symptom_state": session.get("symptom_state", {}),
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
    Symptom-driven websocket follow-up flow:
      - First question generated immediately after connect
      - Structured symptom state updates after each patient answer
      - Minimum 7 and maximum 10 questions
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
        
        session = session_store[session_id]
        age = session.get("age")
        gender = session.get("gender")
        symptoms = session.get("symptoms") or []
        logger.info(
            "✅ Session found. age=%s gender=%s symptom_count=%s",
            age,
            gender,
            len(symptoms) if isinstance(symptoms, list) else 1,
        )

        # helper to run blocking generator in threadpool
        async def run_generator(func, *args, **kwargs):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))

        def _dedupe_preserve(items):
            out = []
            seen = set()
            for item in items or []:
                val = str(item).strip()
                key = val.lower()
                if not val or key in seen:
                    continue
                out.append(val)
                seen.add(key)
            return out

        def _ensure_states():
            patient_state_local = session.get("patient_state")
            if not isinstance(patient_state_local, dict):
                patient_state_local = initialize_patient_state(
                    age,
                    gender or "unknown",
                    symptoms if isinstance(symptoms, list) else [str(symptoms)],
                )
            symptom_state_local = session.get("symptom_state")
            if not isinstance(symptom_state_local, dict):
                symptom_state_local = {
                    "current_symptoms": list(patient_state_local.get("identified_symptoms", []) or []),
                    "modifiers": [],
                    "modifier_map": {
                        "duration": "",
                        "onset": "",
                        "location": "",
                        "quality": "",
                        "severity": "",
                        "aggravating_factors": [],
                        "relieving_factors": [],
                        "associated_symptoms": [],
                    },
                    "red_flags": list(patient_state_local.get("red_flags", []) or []),
                    "questions_asked": [],
                }
            patient_state_local["symptom_state"] = symptom_state_local
            patient_state_local.setdefault("diagnostic_trace", [])
            patient_state_local.setdefault(
                "diagnostic_counters",
                {
                    "repeated_question_prevention_hits": 0,
                    "generic_question_rejection_hits": 0,
                    "deterministic_fallback_frequency": 0,
                    "out_of_pool_llm_suggestion_rejections": 0,
                },
            )
            session["patient_state"] = patient_state_local
            session["symptom_state"] = symptom_state_local
            return patient_state_local, symptom_state_local

        def _sync_structured_state(patient_state_local, symptom_state_local):
            symptom_state_local["current_symptoms"] = _dedupe_preserve(
                patient_state_local.get("identified_symptoms", [])
            )
            symptom_state_local["red_flags"] = _dedupe_preserve(
                patient_state_local.get("red_flags", [])
            )
            symptom_state_local.setdefault("modifiers", [])
            symptom_state_local.setdefault(
                "modifier_map",
                {
                    "duration": "",
                    "onset": "",
                    "location": "",
                    "quality": "",
                    "severity": "",
                    "aggravating_factors": [],
                    "relieving_factors": [],
                    "associated_symptoms": [],
                },
            )
            symptom_state_local.setdefault("questions_asked", [])
            patient_state_local["symptom_state"] = symptom_state_local
            session["symptom_state"] = symptom_state_local
            session["patient_state"] = patient_state_local
            session["symptoms"] = symptom_state_local.get("current_symptoms", [])
            session["negatives"] = patient_state_local.get("negatives", [])
            session["diagnostic_trace"] = patient_state_local.get("diagnostic_trace", [])

        def _normalize_text(text):
            return re.sub(r"\s+", " ", str(text or "").strip().lower())

        def _is_repeated_question(question_text, asked_questions):
            q = _normalize_text(question_text)
            if not q:
                return True
            q_tokens = set(re.findall(r"[a-z0-9]+", q))
            for asked in asked_questions or []:
                a = _normalize_text(asked)
                if not a:
                    continue
                if q == a:
                    return True
                a_tokens = set(re.findall(r"[a-z0-9]+", a))
                if q_tokens and a_tokens:
                    # Lowered from 0.78 to 0.65 to catch near-identical questions
                    overlap = len(q_tokens & a_tokens) / float(len(q_tokens | a_tokens))
                    if overlap >= 0.65:
                        return True
            return False

        def _is_low_utility_question(question_text):
            q = _normalize_text(question_text)
            if not q:
                return True
            return any(marker in q for marker in _GENERIC_RUNTIME_MARKERS)

        def _contains_placeholder_text(question_obj):
            if not isinstance(question_obj, dict):
                return True
            combined = " ".join(
                str(question_obj.get(key, "")).strip().lower()
                for key in ("Question", "A", "B", "C", "D")
            )
            if not combined:
                return True
            return any(marker in combined for marker in _PLACEHOLDER_RUNTIME_MARKERS)

        def _has_distinct_options(question_obj):
            options = []
            for key in ("A", "B", "C"):
                value = str(question_obj.get(key, "")).strip()
                if not value:
                    return False
                options.append(_normalize_text(value))
            return len(set(options)) == 3

        def _options_already_seen(question_obj, asked_questions):
            """Check if this question's options are a near-duplicate of a previously asked question's options.
            Catches cases where Q text differs slightly but options are identical (repeated pattern).
            """
            # Build a fingerprint from sorted option values A-D
            opts = []
            for key in ("A", "B", "C", "D"):
                v = _normalize_text(str(question_obj.get(key, "")))
                if v:
                    opts.append(v)
            if len(opts) < 3:
                return False
            current_sig = "|".join(sorted(opts))
            # Store seen option signatures in symptom_state
            seen_sigs = symptom_state.get("_asked_option_sigs", [])
            for sig in seen_sigs:
                # Count matching options
                sig_parts = set(sig.split("|"))
                cur_parts = set(current_sig.split("|"))
                overlap = len(sig_parts & cur_parts) / max(len(sig_parts | cur_parts), 1)
                if overlap >= 0.75:  # 3 of 4 options the same = repeated
                    return True
            return False

        def _track_option_sig(question_obj):
            """Record the option fingerprint so future questions can detect duplicate option sets."""
            opts = []
            for key in ("A", "B", "C", "D"):
                v = _normalize_text(str(question_obj.get(key, "")))
                if v:
                    opts.append(v)
            if len(opts) >= 3:
                sig = "|".join(sorted(opts))
                sigs = symptom_state.setdefault("_asked_option_sigs", [])
                if sig not in sigs:
                    sigs.append(sig)

        def _is_valid_question_payload(question_obj, asked_questions):
            if not isinstance(question_obj, dict):
                return False
            question_text = str(question_obj.get("Question", "")).strip()
            if not question_text:
                return False
            if _contains_placeholder_text(question_obj):
                return False
            if _is_low_utility_question(question_text):
                return False
            if _is_repeated_question(question_text, asked_questions):
                return False
            if _options_already_seen(question_obj, asked_questions):
                return False
            if not _has_distinct_options(question_obj):
                return False
            return True

        def _question_rejection_reason(question_obj, asked_questions):
            if not isinstance(question_obj, dict):
                return "invalid_format"
            question_text = str(question_obj.get("Question", "")).strip()
            if not question_text:
                return "missing_question"
            if _contains_placeholder_text(question_obj):
                return "placeholder"
            if _is_low_utility_question(question_text):
                return "generic"
            if _is_repeated_question(question_text, asked_questions):
                return "repeated"
            if not _has_distinct_options(question_obj):
                return "non_distinct_options"
            return "unknown"

        def _top2_from_state(state_obj):
            if not isinstance(state_obj, dict):
                return []
            ddx = state_obj.get("differential_diagnosis")
            names = []
            if isinstance(ddx, list):
                for item in ddx:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    if name:
                        names.append(name)
                    if len(names) >= 2:
                        break
            return names

        def _record_question_trace(state_obj, question_obj, next_turn):
            if not isinstance(state_obj, dict):
                return None
            trace = state_obj.setdefault("diagnostic_trace", [])
            if not isinstance(trace, list):
                trace = []
                state_obj["diagnostic_trace"] = trace
            entry = {
                "turn": next_turn,
                "top2_before_question": question_obj.get("differentiates_between") if isinstance(question_obj.get("differentiates_between"), list) else _top2_from_state(state_obj),
                "selected_discriminator_feature": question_obj.get("feature_id"),
                "question_source": question_obj.get("question_source", "deterministic"),
                "question": question_obj.get("Question"),
                "timestamp": datetime.utcnow().isoformat(),
            }
            trace.append(entry)
            return entry

        def _update_last_trace_after_answer(state_obj, signals):
            if not isinstance(state_obj, dict):
                return
            trace = state_obj.get("diagnostic_trace")
            if not isinstance(trace, list) or not trace:
                return
            last = trace[-1]
            if not isinstance(last, dict):
                return
            if isinstance(signals, dict):
                last["extracted_new_evidence"] = {
                    "new_positive_findings": signals.get("new_positive_findings", []),
                    "new_negative_findings": signals.get("new_negative_findings", []),
                    "red_flags_detected": signals.get("red_flags_detected", []),
                    "modifier_map": signals.get("modifier_map", {}),
                }
            last["top2_after_answer"] = _top2_from_state(state_obj)

        def _fallback_question(patient_state_local, symptom_state_local):
            fallback = build_contextual_fallback_mcq(patient_state_local if isinstance(patient_state_local, dict) else {})
            if isinstance(fallback, dict):
                fallback.setdefault("D", "None of these")
                fallback.setdefault("E", "None of these / Not sure")  # Fix: ensure E is always present
                fallback.setdefault(
                    "priority",
                    "red-flag" if symptom_state_local.get("red_flags") else "high",
                )
                fallback.setdefault(
                    "clinical_intent",
                    "Differentiate top competing diagnoses using current structured symptom evidence",
                )
                fallback.setdefault(
                    "differentiates_between",
                    ["Top suspect #1", "Top suspect #2"],
                )
                fallback.setdefault("allow_other", True)
                fallback.setdefault("question_source", "deterministic")
                if isinstance(patient_state_local, dict):
                    counters = patient_state_local.setdefault("diagnostic_counters", {})
                    counters["deterministic_fallback_frequency"] = int(counters.get("deterministic_fallback_frequency", 0) or 0) + 1
            return fallback

        def _min_depth_safe_question(patient_state_local, symptom_state_local):
            asked = symptom_state_local.get("questions_asked", []) if isinstance(symptom_state_local, dict) else []
            current_symptoms = symptom_state_local.get("current_symptoms", []) if isinstance(symptom_state_local, dict) else []
            symptom_blob = " ".join(str(item).strip().lower() for item in current_symptoms if str(item).strip())
            if not symptom_blob and isinstance(patient_state_local, dict):
                symptom_blob = str(patient_state_local.get("chief_complaint", "")).strip().lower()

            top_two = _top2_from_state(patient_state_local)
            if len(top_two) < 2:
                top_two = ["Top suspect #1", "Top suspect #2"]

            candidates = []
            if any(token in symptom_blob for token in ("abdominal", "stomach", "vomit", "diarrhea", "bowel")):
                candidates.append({
                    "Question": "Which abdominal pattern is most prominent right now?",
                    "A": "Pain is right-lower and worse with movement or coughing",
                    "B": "Pain is diffuse with loose stools or repeated vomiting",
                    "C": "Pain is upper-abdominal burning, often after meals",
                    "D": "Cramping pain relieved after passing stool",
                    "E": "None of these / Not sure",  # Fix: add option E
                    "feature_id": "abdominal_pattern",
                })
            if any(token in symptom_blob for token in ("cough", "breath", "chest", "wheeze", "phlegm")):
                candidates.append({
                    "Question": "Which respiratory pattern best matches your current symptoms?",
                    "A": "Breathlessness with chest tightness or wheeze episodes",
                    "B": "Productive cough with yellow/green sputum and fever",
                    "C": "Dry cough with throat irritation and minimal sputum",
                    "D": "Sudden onset breathlessness without cough or sputum",
                    "E": "None of these / Not sure",  # Fix: add option E
                    "feature_id": "respiratory_pattern",
                })
            if any(token in symptom_blob for token in ("headache", "dizziness", "weakness", "numb", "balance")):
                candidates.append({
                    "Question": "Which neurological pattern is most noticeable now?",
                    "A": "One-sided weakness/numbness or speech disturbance",
                    "B": "Severe throbbing headache with light sensitivity",
                    "C": "Spinning dizziness without focal weakness",
                    "D": "Gradual memory or concentration difficulties",
                    "E": "None of these / Not sure",  # Fix: add option E
                    "feature_id": "neurological_pattern",
                })

            candidates.append({
                "Question": "Which associated feature is most clearly present with your current symptoms?",
                "A": "Localized focal symptoms in one body area",
                "B": "Systemic features like fever, fatigue, or chills",
                "C": "Trigger-linked intermittent episodes",
                "D": "Symptoms worse at specific times (morning, night, after meals)",
                "E": "None of these / Not sure",  # Fix: add option E
                "feature_id": "associated_pattern",
            })

            for candidate in candidates:
                candidate.setdefault("priority", "high")
                candidate.setdefault(
                    "clinical_intent",
                    f"Differentiate {top_two[0]} vs {top_two[1]} with a non-repetitive clinical discriminator",
                )
                candidate.setdefault("differentiates_between", top_two[:2])
                candidate.setdefault("allow_other", True)
                candidate.setdefault("question_source", "deterministic")
                if _is_valid_question_payload(candidate, asked):
                    return candidate
            return None

        def _force_unique_min_depth_question(patient_state_local, symptom_state_local, current_question_count):
            """Guaranteed non-repeating MCQ when LLM/deterministic fallbacks are exhausted."""
            asked = symptom_state_local.get("questions_asked", []) if isinstance(symptom_state_local, dict) else []
            symptoms = symptom_state_local.get("current_symptoms", []) if isinstance(symptom_state_local, dict) else []
            chief = next((str(s).strip() for s in symptoms if str(s).strip()), "your symptoms")
            top_two = _top2_from_state(patient_state_local)
            if len(top_two) < 2:
                top_two = ["Top suspect #1", "Top suspect #2"]

            turn_templates = [
                {
                    "Question": f"How long have you had {chief}?",
                    "A": "Less than 24 hours",
                    "B": "1 to 3 days",
                    "C": "4 to 7 days",
                    "D": "More than 1 week",
                    "E": "None of these / Not sure",
                    "feature_id": "duration",
                },
                {
                    "Question": f"How did your {chief} start?",
                    "A": "Suddenly over minutes to hours",
                    "B": "Gradually over several days",
                    "C": "Intermittent episodes that come and go",
                    "D": "Constant since it began",
                    "E": "None of these / Not sure",
                    "feature_id": "onset",
                },
                {
                    "Question": f"How severe is your {chief} right now?",
                    "A": "Mild — noticeable but not limiting daily activity",
                    "B": "Moderate — interferes with normal activity",
                    "C": "Severe — hard to function normally",
                    "D": "Worst at specific times of day only",
                    "E": "None of these / Not sure",
                    "feature_id": "severity",
                },
                {
                    "Question": "Which factor most clearly worsens your symptoms?",
                    "A": "Physical activity or exertion",
                    "B": "Eating, fasting, or specific foods",
                    "C": "Stress, poor sleep, or fatigue",
                    "D": "No clear trigger — symptoms are constant",
                    "E": "None of these / Not sure",
                    "feature_id": "aggravating_factor",
                },
                {
                    "Question": "Have you noticed any of these associated features?",
                    "A": "Fever, chills, or night sweats",
                    "B": "Nausea, vomiting, or appetite loss",
                    "C": "Breathlessness or chest discomfort",
                    "D": "No associated features beyond main symptoms",
                    "E": "None of these / Not sure",
                    "feature_id": "associated_features",
                },
                {
                    "Question": "Have you tried any treatment since symptoms began?",
                    "A": "Over-the-counter medicines with some relief",
                    "B": "Over-the-counter medicines with no relief",
                    "C": "Prescription medicines from a doctor",
                    "D": "No treatment tried yet",
                    "E": "None of these / Not sure",
                    "feature_id": "treatment_trial",
                },
                {
                    "Question": "Have you had similar episodes before?",
                    "A": "Yes, similar episodes in the past",
                    "B": "No, this is the first time",
                    "C": "Unsure — possibly mild episodes before",
                    "D": "Yes, but this episode feels clearly worse",
                    "E": "None of these / Not sure",
                    "feature_id": "prior_episodes",
                },
                {
                    "Question": "Which red-flag pattern is most relevant for you now?",
                    "A": "Sudden severe worsening or confusion",
                    "B": "Difficulty breathing or chest pain",
                    "C": "Persistent high fever or rigors",
                    "D": "None of these red flags",
                    "E": "None of these / Not sure",
                    "feature_id": "red_flag_screen",
                },
                {
                    "Question": "How are your symptoms affecting daily function?",
                    "A": "Can work/perform daily tasks with mild discomfort",
                    "B": "Need rest but can manage basic tasks",
                    "C": "Mostly bed-bound or unable to work",
                    "D": "Symptoms fluctuate through the day",
                    "E": "None of these / Not sure",
                    "feature_id": "functional_impact",
                },
                {
                    "Question": "Any recent exposure that could explain your illness?",
                    "A": "Contact with someone who was sick recently",
                    "B": "Recent travel or crowded exposure",
                    "C": "New medication, supplement, or food trigger",
                    "D": "No known recent exposure",
                    "E": "None of these / Not sure",
                    "feature_id": "exposure_history",
                },
                {
                    "Question": "Which pattern best describes symptom progression?",
                    "A": "Getting progressively worse each day",
                    "B": "Improving slightly but not resolved",
                    "C": "Stable without major change",
                    "D": "Waxing and waning repeatedly",
                    "E": "None of these / Not sure",
                    "feature_id": "progression",
                },
                {
                    "Question": "Which relieving factor applies most to your symptoms?",
                    "A": "Rest or sleep helps noticeably",
                    "B": "Fluids, food, or warmth helps",
                    "C": "Pain/symptom medicine helps",
                    "D": "Nothing clearly relieves symptoms",
                    "E": "None of these / Not sure",
                    "feature_id": "relieving_factor",
                },
            ]

            start_idx = max(int(current_question_count or 0), 0)
            for offset in range(len(turn_templates)):
                candidate = dict(turn_templates[(start_idx + offset) % len(turn_templates)])
                candidate.setdefault("priority", "high")
                candidate.setdefault(
                    "clinical_intent",
                    f"Collect structured discriminator #{start_idx + offset + 1} for {top_two[0]} vs {top_two[1]}",
                )
                candidate.setdefault("differentiates_between", top_two[:2])
                candidate.setdefault("allow_other", True)
                candidate.setdefault("question_source", "turn_indexed")
                if _is_valid_question_payload(candidate, asked):
                    return candidate

            # Last resort: append turn marker so dedup accepts a unique question.
            fallback = dict(turn_templates[start_idx % len(turn_templates)])
            fallback["Question"] = f"{fallback['Question']} (follow-up {start_idx + 1})"
            fallback.setdefault("D", "None of these")
            fallback.setdefault("E", "None of these / Not sure")
            fallback.setdefault("allow_other", True)
            fallback.setdefault("question_source", "turn_indexed")
            fallback.setdefault("differentiates_between", top_two[:2])
            return fallback

        def _select_question_candidate(primary_candidate, patient_state_local, symptom_state_local, current_question_count):
            asked_qs = symptom_state_local.get("questions_asked", []) if isinstance(symptom_state_local, dict) else []
            candidate_chain = [
                primary_candidate,
                _fallback_question(patient_state_local, symptom_state_local),
                _min_depth_safe_question(patient_state_local, symptom_state_local),
                _force_unique_min_depth_question(patient_state_local, symptom_state_local, current_question_count),
            ]
            counters = patient_state_local.setdefault("diagnostic_counters", {}) if isinstance(patient_state_local, dict) else {}

            for index, candidate in enumerate(candidate_chain):
                if isinstance(candidate, str):
                    if "ready for diagnosis" in candidate.lower():
                        if current_question_count >= MIN_FOLLOWUP_QUESTIONS:
                            return "Ready for diagnosis"
                        continue
                if _is_valid_question_payload(candidate, asked_qs):
                    candidate.setdefault("D", "None of these")
                    candidate.setdefault("E", "None of these / Not sure")
                    candidate.setdefault("allow_other", True)
                    if index > 0:
                        logger.info(
                            "[QSELECT] primary candidate rejected; using fallback index=%s source=%s",
                            index,
                            candidate.get("question_source"),
                        )
                    return candidate
                if index == 0:
                    reason = _question_rejection_reason(candidate, asked_qs)
                    logger.info(
                        "[QSELECT] LLM/primary question rejected reason=%s q=%r",
                        reason,
                        str(candidate.get("Question", ""))[:80] if isinstance(candidate, dict) else candidate,
                    )
                    if reason == "repeated":
                        counters["repeated_question_prevention_hits"] = int(counters.get("repeated_question_prevention_hits", 0) or 0) + 1
                    if reason in {"generic", "placeholder"}:
                        counters["generic_question_rejection_hits"] = int(counters.get("generic_question_rejection_hits", 0) or 0) + 1

            forced = _force_unique_min_depth_question(patient_state_local, symptom_state_local, current_question_count)
            if isinstance(forced, dict) and forced.get("Question"):
                forced.setdefault("D", "None of these")
                forced.setdefault("E", "None of these / Not sure")
                forced.setdefault("allow_other", True)
                return forced
            return None

        def _mcq_options(question_dict):
            options = []
            for key in ("A", "B", "C", "D", "E"):  # Fix D: include option E
                if key in question_dict:
                    options.append({"key": key, "value": question_dict[key]})
            return options

        patient_state, symptom_state = _ensure_states()
        _sync_structured_state(patient_state, symptom_state)
        session.setdefault("question_count", 0)

        if session.get("question_count", 0) >= 12:
            await websocket.send_json({"message": "Maximum questions reached, generating diagnosis", "status": "ready_for_diagnosis"})
            await websocket.close(code=1000, reason="Max questions reached")
            return

        # Auto-generate first question when session starts.
        if session.get("question_count", 0) == 0:
            logger.info("[START] Auto-generating first question for session %s", session_id)
            try:
                raw_response = await run_generator(
                    get_followup_for_diagnosis_v5,
                    patient_state,
                    1,
                )
            except Exception as e:
                logger.warning("Initial generation failed for session %s: %s", session_id, e)
                raw_response = _fallback_question(patient_state, symptom_state)

            if isinstance(raw_response, dict) and raw_response.get("error") == "api_key_failure":
                await websocket.send_json({"error": raw_response.get("message", "Service temporarily unavailable. Please try again later.")})
                await websocket.close(code=1011, reason="API key failure")
                return

            selected_initial = _select_question_candidate(
                raw_response,
                patient_state,
                symptom_state,
                session.get("question_count", 0),
            )

            if isinstance(selected_initial, str) and "ready for diagnosis" in selected_initial.lower():
                await websocket.send_json({"message": "Diagnosis is ready", "status": "ready_for_diagnosis"})
                await websocket.close(code=1000, reason="Diagnosis ready")
                return

            if not (isinstance(selected_initial, dict) and selected_initial.get("Question")):
                selected_initial = _force_unique_min_depth_question(
                    patient_state, symptom_state, session.get("question_count", 0)
                )

            if not (isinstance(selected_initial, dict) and selected_initial.get("Question")):
                await websocket.send_json({"error": "Unable to generate a clinically valid follow-up question."})
                await websocket.close(code=1011, reason="Question generation failure")
                return

            raw_response = selected_initial
            session["question_count"] = 1
            session["last_options"] = raw_response
            session["last_question_data"] = raw_response
            session["last_question_text"] = raw_response.get("Question")
            if raw_response.get("Question"):
                questions = symptom_state.get("questions_asked", [])
                if raw_response["Question"] not in questions:
                    questions.append(raw_response["Question"])
                symptom_state["questions_asked"] = questions
                _track_option_sig(raw_response)  # track option fingerprint for dedup
            diagnostic_trace_turn = _record_question_trace(patient_state, raw_response, session["question_count"])
            _sync_structured_state(patient_state, symptom_state)

            payload = {
                "question": raw_response["Question"],
                "options": _mcq_options(raw_response),
                "status": "waiting_for_answer",
                "allow_other": bool(raw_response.get("allow_other", True)),
            }
            for meta_key in ("priority", "clinical_intent", "differentiates_between", "feature_id", "question_source"):
                if meta_key in raw_response:
                    payload[meta_key] = raw_response.get(meta_key)
            if isinstance(diagnostic_trace_turn, dict):
                payload["diagnostic_trace_turn"] = diagnostic_trace_turn
            await websocket.send_json(payload)
        else:
            # Reconnection case: resend last question if available.
            last_q = session.get("last_options")
            if isinstance(last_q, dict) and last_q.get("Question"):
                await websocket.send_json({
                    "question": last_q["Question"],
                    "options": _mcq_options(last_q),
                    "status": "waiting_for_answer",
                    "allow_other": bool(last_q.get("allow_other", True)),
                    "feature_id": last_q.get("feature_id"),
                    "question_source": last_q.get("question_source"),
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
            
            client_msg_raw = client_msg.strip()
            client_msg_clean = client_msg_raw.upper()

            # Map A/B/C/D to option text when possible
            last_response = session.get("last_options", {})
            mapped_answer = None
            if client_msg_clean in ("A", "B", "C", "D", "E"):
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
                # If mapping fails, append raw (preserve user wording)
                logger.warning("Unmapped response from client for session %s: %s; appending raw.", session_id, client_msg_raw)
                user_answer = client_msg_raw

            logger.info("[ANSWER] Session %s answer=%s", session_id, user_answer)
            last_question_text = session.get("last_question_text", "")
            try:
                patient_state, update_meta = await run_generator(
                    update_state_with_answer_v5,
                    patient_state,
                    last_question_text or "",
                    user_answer,
                )
                if isinstance(update_meta, dict):
                    signals = update_meta.get("signals") or {}
                    if isinstance(signals, dict):
                        logger.info(
                            "[STATE] symptoms=%s negatives=%s red_flags=%s",
                            patient_state.get("identified_symptoms", []),
                            patient_state.get("negatives", []),
                            patient_state.get("red_flags", []),
                        )
                        _update_last_trace_after_answer(patient_state, signals)
                _sync_structured_state(patient_state, symptom_state)
            except Exception as e:
                logger.warning("update_state_with_answer_v5 failed for session %s: %s", session_id, e)

            current_question_count = session.get("question_count", 0)
            if current_question_count >= 12:
                await websocket.send_json({"message": "Maximum questions reached, generating diagnosis", "status": "ready_for_diagnosis"})
                await websocket.close(code=1000, reason="Max questions reached")
                break

            # Generate next question from structured state
            try:
                next_raw = await run_generator(
                    get_followup_for_diagnosis_v5,
                    patient_state,
                    1,  # max_retries
                )
            except Exception as e:
                logger.exception("get_followup_for_diagnosis_v5 error mid-conversation for session %s: %s", session_id, e)
                await websocket.send_json({"error": "Failed to process answer (server error)."})
                await websocket.close(code=1011, reason="Internal processing error")
                break

            logger.info("Raw next response (type=%s) for session %s: %s", type(next_raw).__name__, session_id, repr(next_raw)[:2000])

            # Handle different generator outputs safely with min/max turn constraints
            if isinstance(next_raw, dict) and next_raw.get("error") == "api_key_failure":
                await websocket.send_json({"error": next_raw.get("message", "Service temporarily unavailable due to high request volume. Please try again later.")})
                await websocket.close(code=1011, reason="API key failure")
                break

            selected_next = _select_question_candidate(
                next_raw,
                patient_state,
                symptom_state,
                current_question_count,
            )

            if isinstance(selected_next, str) and "ready for diagnosis" in selected_next.lower():
                if current_question_count >= MIN_FOLLOWUP_QUESTIONS:
                    await websocket.send_json({"message": "Diagnosis is ready", "status": "ready_for_diagnosis"})
                    await websocket.close(code=1000, reason="Diagnosis ready")
                    break
                selected_next = _force_unique_min_depth_question(
                    patient_state, symptom_state, current_question_count
                )

            if not (isinstance(selected_next, dict) and selected_next.get("Question")):
                if current_question_count >= MIN_FOLLOWUP_QUESTIONS:
                    await websocket.send_json({"message": "Diagnosis is ready", "status": "ready_for_diagnosis"})
                    await websocket.close(code=1000, reason="Diagnosis ready")
                    break
                selected_next = _force_unique_min_depth_question(
                    patient_state, symptom_state, current_question_count
                )

            if not (isinstance(selected_next, dict) and selected_next.get("Question")):
                logger.error(
                    "Session %s: exhausted all question fallbacks at count=%s",
                    session_id,
                    current_question_count,
                )
                await websocket.send_json({"error": "Unable to generate the next follow-up question. Please try again."})
                await websocket.close(code=1011, reason="Question generation failure")
                break

            next_raw = selected_next

            if current_question_count >= 12:
                await websocket.send_json({"message": "Maximum questions reached, generating diagnosis", "status": "ready_for_diagnosis"})
                await websocket.close(code=1000, reason="Max questions reached")
                break

            next_raw.setdefault("D", "None of these")
            next_raw.setdefault("allow_other", True)
            session["question_count"] = current_question_count + 1
            session["last_options"] = next_raw
            session["last_question_data"] = next_raw
            session["last_question_text"] = next_raw.get("Question")

            question_text = str(next_raw.get("Question", "")).strip()
            if question_text:
                questions = symptom_state.get("questions_asked", [])
                if question_text not in questions:
                    questions.append(question_text)
                symptom_state["questions_asked"] = questions
                _track_option_sig(next_raw)  # track option fingerprint for dedup
            diagnostic_trace_turn = _record_question_trace(patient_state, next_raw, session["question_count"])
            _sync_structured_state(patient_state, symptom_state)

            response_payload = {
                "question": next_raw["Question"],
                "options": _mcq_options(next_raw),
                "status": "waiting_for_answer",
                "allow_other": bool(next_raw.get("allow_other", True)),
            }
            for meta_key in ("priority", "clinical_intent", "differentiates_between", "feature_id", "question_source"):
                if meta_key in next_raw:
                    response_payload[meta_key] = next_raw.get(meta_key)
            if isinstance(diagnostic_trace_turn, dict):
                response_payload["diagnostic_trace_turn"] = diagnostic_trace_turn

            logger.info("Session %s: Asked question #%d", session_id, session["question_count"])
            await websocket.send_json(response_payload)

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
        # Fix HTTP 500: assign patient_state BEFORE reading chat_history from it
        patient_state = session.get("patient_state") if isinstance(session.get("patient_state"), dict) else {}
        chat_history = patient_state.get("chat_history") if isinstance(patient_state.get("chat_history"), list) else session.get("chat_history", [])
        symptom_state = session.get("symptom_state") if isinstance(session.get("symptom_state"), dict) else {}
        if patient_state.get("identified_symptoms"):
            symptoms = patient_state.get("identified_symptoms")
        elif isinstance(symptom_state.get("current_symptoms"), list) and symptom_state.get("current_symptoms"):
            symptoms = symptom_state.get("current_symptoms")
        negatives = patient_state.get("negatives", [])

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
                get_final_diagnosis_v5,
                age, gender, symptoms, chat_history, negatives, weight, height, occupation, location, physical_activity, diet_type, patient_state
            )
            
            symptom_state_for_report = patient_state.get("symptom_state") if isinstance(patient_state, dict) and isinstance(patient_state.get("symptom_state"), dict) else {}
            # Fix G: extract running_summary built during diagnosis loop
            running_summary_for_report = str(patient_state.get("running_summary", "")).strip() if isinstance(patient_state, dict) else ""
            report = await loop.run_in_executor(
                executor,
                final_report,
                age, gender, symptoms, chat_history, mapped_diseases,
                weight, height, occupation, location, physical_activity, diet_type,
                negatives, symptom_state_for_report, running_summary_for_report
            )
        except Exception as ai_error:
            logger.error(f"AI processing error in generate_report: {ai_error}")
            raise HTTPException(
                status_code=500, 
                detail="AI processing failed while generating report"
            )

        def _normalize_report_for_frontend(raw_report, session_data, mapping_data):
            """
            Ensure report has all required fields for frontend + PDF generation.
            Adds safe defaults when the AI output is incomplete.
            """
            report_obj = raw_report
            if isinstance(report_obj, str):
                try:
                    report_obj = json.loads(report_obj)
                except Exception:
                    report_obj = {}

            if not isinstance(report_obj, dict):
                report_obj = {}

            # Ensure PatientInfo
            patient_info = report_obj.get("PatientInfo") if isinstance(report_obj.get("PatientInfo"), dict) else {}
            age_val = session_data.get("age")
            gender_val = session_data.get("gender")
            name_val = session_data.get("name")
            if "Age" not in patient_info or not patient_info.get("Age"):
                patient_info["Age"] = f"{age_val} Years" if age_val is not None else "N/A"
            if "Gender" not in patient_info or not patient_info.get("Gender"):
                patient_info["Gender"] = str(gender_val).title() if gender_val else "Unknown"
            if "Name" not in patient_info or not patient_info.get("Name"):
                patient_info["Name"] = name_val or "Unknown"
            report_obj["PatientInfo"] = patient_info

            # Ensure MainSymptoms
            if not isinstance(report_obj.get("MainSymptoms"), list) or not report_obj.get("MainSymptoms"):
                symptoms_list = session_data.get("symptoms") or []
                if not isinstance(symptoms_list, list):
                    symptoms_list = [str(symptoms_list)]
                report_obj["MainSymptoms"] = symptoms_list[:8]

            # Ensure Urgency
            if not report_obj.get("Urgency"):
                report_obj["Urgency"] = "Routine"

            # Ensure TopDiseaseMatches
            def _fallback_top_matches(mapping):
                fallback = []
                conditions = []
                if isinstance(mapping, dict):
                    conditions = mapping.get("conditions") or []
                if isinstance(conditions, list) and conditions:
                    for idx, cond in enumerate(conditions[:2], start=1):
                        name = cond.get("name") if isinstance(cond, dict) else None
                        prob = cond.get("probability") if isinstance(cond, dict) else None
                        fallback.append(_flatten_match_entry({"Name": name, "MatchLevel": prob}, cond))
                if not fallback:
                    fallback = [{
                        "Name": "Undetermined",
                        "MatchLevel": "Moderate",
                        "PreHospitalCare": ["Rest", "Hydration"],
                        "SymptomsToWatch": ["Worsening symptoms"],
                        "SelfCare": ["Monitor temperature", "Avoid exertion"],
                        "MedicationSuggestion": ["Consult a doctor before medication"]
                    }]
                return fallback

            def _extract_match_name(entry):
                if not isinstance(entry, dict) or not entry:
                    return None
                flat = (
                    entry.get("Name")
                    or entry.get("name")
                    or entry.get("Disease")
                    or entry.get("disease")
                )
                if flat:
                    return str(flat).strip()
                key = next(
                    (k for k in entry.keys() if str(k).startswith("Disease")),
                    next(iter(entry.keys()), None),
                )
                data = entry.get(key) if key else None
                if isinstance(data, dict):
                    num = "".join(ch for ch in str(key) if ch.isdigit())
                    return str(
                        data.get(f"Name{num}")
                        or data.get("Name")
                        or data.get("name")
                        or data.get("Disease")
                        or data.get("disease")
                        or ""
                    ).strip() or None
                return None

            def _normalize_match_level(value):
                text = str(value or "Moderate").strip()
                if text.lower() in {"high", "high match"}:
                    return "High"
                if text.lower() in {"low", "low match"}:
                    return "Low"
                if text.lower() in {"moderate", "moderate match"}:
                    return "Moderate"
                return text or "Moderate"

            def _flatten_match_entry(entry, cond=None):
                name = _extract_match_name(entry) if isinstance(entry, dict) else None
                if not name and isinstance(cond, dict):
                    name = cond.get("name")
                match_level = _normalize_match_level(
                    (entry.get("MatchLevel") if isinstance(entry, dict) else None)
                    or (entry.get("matchLevel") if isinstance(entry, dict) else None)
                    or (cond.get("probability") if isinstance(cond, dict) else None)
                    or "Moderate"
                )
                pre_hospital = []
                self_care = []
                watch = []
                meds = []
                if isinstance(entry, dict):
                    pre_hospital = entry.get("PreHospitalCare") or entry.get("preHospitalCare") or []
                    self_care = entry.get("SelfCare") or entry.get("selfCare") or []
                    watch = entry.get("SymptomsToWatch") or entry.get("symptomsToWatch") or []
                    meds = entry.get("MedicationSuggestion") or entry.get("medicationSuggestion") or []
                    nested_key = next(
                        (k for k in entry.keys() if str(k).startswith("Disease")),
                        None,
                    )
                    if nested_key and isinstance(entry.get(nested_key), dict):
                        num = "".join(ch for ch in str(nested_key) if ch.isdigit())
                        nested = entry[nested_key]
                        pre_hospital = pre_hospital or nested.get(f"PreHospitalCare{num}") or nested.get("PreHospitalCare") or []
                        self_care = self_care or nested.get(f"SelfCare{num}") or nested.get("SelfCare") or []
                        watch = watch or nested.get(f"SymptomsToWatch{num}") or nested.get("SymptomsToWatch") or []
                        meds = meds or nested.get(f"MedicationSuggestion{num}") or nested.get("MedicationSuggestion") or []
                return {
                    "Name": name or "Unknown condition",
                    "MatchLevel": match_level,
                    "PreHospitalCare": pre_hospital if isinstance(pre_hospital, list) else [str(pre_hospital)],
                    "SymptomsToWatch": watch if isinstance(watch, list) else [str(watch)],
                    "SelfCare": self_care if isinstance(self_care, list) else [str(self_care)],
                    "MedicationSuggestion": meds if isinstance(meds, list) else [str(meds)],
                }

            def _build_match_entry(idx, name, match_level):
                return _flatten_match_entry(
                    {
                        "Name": name or "Unknown condition",
                        "MatchLevel": match_level or "Moderate",
                    }
                )

            def _ensure_two_matches(existing, mapping):
                """
                Return matches as-is when only one valid condition exists.
                Only add placeholders when there are zero valid matches.
                """
                matches = list(existing) if isinstance(existing, list) else []
                existing_names = set()
                flattened_matches = []
                for entry in matches:
                    flat = _flatten_match_entry(entry)
                    name = flat.get("Name")
                    if name:
                        name_key = str(name).strip().lower()
                        if name_key in existing_names:
                            continue
                        existing_names.add(name_key)
                        flattened_matches.append(flat)
                matches = flattened_matches

                conditions = []
                if isinstance(mapping, dict):
                    conditions = mapping.get("conditions") or []

                for cond in conditions:
                    if not isinstance(cond, dict):
                        continue
                    name = cond.get("name")
                    if not name:
                        continue
                    name_key = str(name).strip().lower()
                    if name_key in existing_names:
                        continue
                    match_level = cond.get("probability") or "Moderate"
                    matches.append(_flatten_match_entry({"Name": name, "MatchLevel": match_level}, cond))
                    existing_names.add(name_key)
                    if len(matches) >= 2:
                        break

                if len(matches) == 0:
                    matches.append(_build_match_entry(1, "Undetermined", "Moderate"))

                return matches[:2]

            top_matches = report_obj.get("TopDiseaseMatches")
            if not isinstance(top_matches, list) or not top_matches:
                top_matches = _fallback_top_matches(mapping_data)
            elif len(top_matches) > 2:
                top_matches = top_matches[:2]

            # Ensure we return 1-2 usable matches
            report_obj["TopDiseaseMatches"] = _ensure_two_matches(top_matches, mapping_data)

            report_obj["NextDiagnosticSteps"] = build_next_diagnostic_steps(
                report_obj, mapping_data
            )

            return report_obj

        if report:
            # Parse report if it's a JSON string
            if isinstance(report, str):
                try:
                    import json
                    report = json.loads(report)
                except:
                    # If parsing fails, use as is
                    pass

            # Normalize report structure for frontend/PDF robustness
            report = _normalize_report_for_frontend(report, session, mapped_diseases)
            
            # NOTE: IndicTrans2 translation service integration disabled
            # Currently using Google/Gemini for all translation (via /api/translate)
            # The lang parameter is kept for frontend compatibility but not used for backend translation
            # Frontend handles translation using existing Google/Gemini infrastructure
            
            # Update session with report status
            session["report_generated"] = True
            session["report_timestamp"] = datetime.utcnow().isoformat()
            session["report_language"] = lang
            
            session_location = session.get("location") if isinstance(session.get("location"), dict) else {}
            response_data = {
                "patient_details": {
                    "name": name,
                    "age": age,
                    "gender": gender,
                    "weight": session.get("weight"),
                    "height": session.get("height"),
                    "occupation": session.get("occupation"),
                    "physical_activity": session.get("physical_activity"),
                    "diet_type": session.get("diet_type"),
                    "location": session_location,
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generating report for session %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail="Internal Server Error generating report")