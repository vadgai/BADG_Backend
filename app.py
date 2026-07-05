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
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator

# Import internal modules
from diagnosis_methods.patient_state import initialize_patient_state
from symptom_extractor_v5 import extract_initial_symptoms
from followup.constants import MAX_FOLLOWUP_QUESTIONS, MIN_FOLLOWUP_QUESTIONS
from followup.websocket_handler import handle_followup_websocket
from diagnosis_rule_engine_v5 import get_final_diagnosis_v5
from diagnosis_report.report import final_report, build_next_diagnostic_steps
from symptom_card import generate_symptom_card, apply_symptom_card

# Import database and new route modules
from database.connection import connect_to_mongodb, close_mongodb_connection
from database.session_persistence import save_session, get_or_restore_session
from routes import admin, form, contact, report_analyzer, translate, disease_info, analytics, careers
# NOTE: IndicTrans2 integration disabled - using Google/Gemini instead.
# The translateProxy / localizedReport route modules were removed as dead code;
# restore them from git history if IndicTrans2 is ever re-enabled.
from routes.admin_analytics import router as admin_analytics_router
from routes.admin_endpoints import router as admin_endpoints_router
from routes.admin_insights import router as admin_insights_router

# Billing / entitlements (report limit enforcement)
from auth.dependencies import optional_user
from billing import entitlements as billing_entitlements
from billing import anon_entitlements

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
    "https://vadg.in,https://www.vadg.in,http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
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

# Bound the in-memory session store so it cannot grow without limit (memory leak).
# TTL evicts inactive sessions; the size cap drops the oldest when over the limit.
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TIMEOUT", "3600"))
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "1000"))


def _evict_stale_sessions() -> None:
    """Prune expired sessions (by TTL) and enforce a hard cap on session_store size."""
    try:
        now = datetime.utcnow()

        def _last_seen(session: dict) -> str:
            return session.get("last_activity") or session.get("created_at") or ""

        # 1) TTL eviction based on last activity / creation time.
        expired = []
        for sid, session in session_store.items():
            ts = _last_seen(session)
            if not ts:
                continue
            try:
                last = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                continue
            if (now - last).total_seconds() > SESSION_TTL_SECONDS:
                expired.append(sid)
        for sid in expired:
            session_store.pop(sid, None)

        # 2) Hard size cap — drop the oldest sessions first.
        overflow = len(session_store) - MAX_SESSIONS
        if overflow > 0:
            oldest = sorted(session_store.items(), key=lambda kv: _last_seen(kv[1]))
            for sid, _ in oldest[:overflow]:
                session_store.pop(sid, None)

        if expired or overflow > 0:
            logger.info(
                "session eviction: removed %s expired, %s over-cap (now %s active)",
                len(expired), max(0, overflow), len(session_store),
            )
    except Exception as exc:  # never let cleanup break request handling
        logger.warning("session eviction error: %s", exc)

#
# --- Application Lifecycle Events ---
#
# Holds references to fire-and-forget background tasks so they aren't GC'd.
_background_tasks = set()


async def _background_init():
    """
    Connect to MongoDB and run idempotent seeding. Runs as a background task so it
    never blocks the server from binding the port — critical for Cloud Run, whose
    startup probe fails the deploy if the container doesn't listen quickly. Every
    step is time-bounded and guarded so a slow/unavailable database can never wedge
    startup; the app serves immediately and degrades to in-memory storage until the
    database is ready.
    """
    import asyncio
    from database.connection import is_database_available

    # 1) Database connection (time-bounded).
    try:
        connected = await asyncio.wait_for(connect_to_mongodb(), timeout=10.0)
        if connected and is_database_available():
            logger.info("✅ MongoDB connected")
        else:
            logger.warning("MongoDB unavailable - continuing with in-memory storage only")
    except asyncio.TimeoutError:
        logger.warning("MongoDB connection timeout - continuing without database")
    except Exception as e:
        logger.warning("MongoDB connection skipped: %s", e)

    # 2) Idempotent seeding (each guarded + time-bounded).
    async def _run(label, coro_factory):
        try:
            await asyncio.wait_for(coro_factory(), timeout=20.0)
        except Exception as e:
            logger.error("%s failed/skipped: %s", label, e)

    try:
        from auth.seed import seed_permanent_admin
        await _run("Permanent admin seeding", seed_permanent_admin)
    except Exception as e:
        logger.error("Permanent admin import failed: %s", e)

    try:
        from billing.plans import seed_default_plans
        await _run("Pricing plan seeding", seed_default_plans)
    except Exception as e:
        logger.error("Pricing plan import failed: %s", e)

    if os.getenv("SEED_DUMMY_USERS", "false").lower() in ("true", "1", "yes", "on"):
        try:
            from auth.seed import seed_dummy_users
            await _run("Dummy user seeding", seed_dummy_users)
        except Exception as e:
            logger.error("Dummy user import failed: %s", e)

    logger.info("✅ Background init complete")


@app.on_event("startup")
async def startup_event():
    """
    Lightweight startup: kick off DB connect + seeding in the BACKGROUND and return
    immediately so uvicorn reports ready and the port binds without waiting on the
    database. This prevents Cloud Run 'failed to start / listen on port' timeouts.
    """
    logger.info("🚀 Starting VADG API (PORT=%s, ENV=%s)",
                os.getenv("PORT", "8080"), os.getenv("ENVIRONMENT", "development"))
    try:
        # Keep a reference so the task isn't garbage-collected mid-run.
        task = asyncio.create_task(_background_init())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except Exception as e:
        # Never let startup raise — that would fail the container health check.
        logger.error("Failed to schedule background init: %s", e)
    logger.info("✅ Startup complete - serving (DB init running in background)")


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
from routes import auth as auth_routes
from routes import billing as billing_routes
from routes import admin_billing as admin_billing_routes
app.include_router(auth_routes.router)
app.include_router(billing_routes.router)
app.include_router(admin_billing_routes.router)
app.include_router(admin.public_router)
app.include_router(admin.router)
app.include_router(admin_analytics_router)
app.include_router(admin_endpoints_router)
app.include_router(admin_insights_router)
app.include_router(form.router)
app.include_router(contact.router)
app.include_router(careers.router)
app.include_router(report_analyzer.router)
app.include_router(translate.router, prefix="/api/translate")
app.include_router(disease_info.router)
app.include_router(analytics.router)
app.include_router(analytics.telemetry_router)

# NOTE: IndicTrans2 routes disabled - using Google/Gemini translation instead.
# (translateProxy / localizedReport modules removed as dead code — see note above.)


#
# --- Middleware: log request bodies (for debugging) ---
#
# Body logging is opt-in and OFF by default. It logs raw request bodies (patient PII:
# symptoms, age, location) and must never be enabled in production. Set LOG_REQUEST_BODIES=true
# only for local debugging.
LOG_REQUEST_BODIES = os.getenv("LOG_REQUEST_BODIES", "false").strip().lower() in ("1", "true", "yes")


@app.middleware("http")
async def log_request_body_middleware(request: Request, call_next):
    """
    Optionally logs the body for POST/PUT/PATCH requests for local debugging only.
    Disabled unless LOG_REQUEST_BODIES=true, because bodies contain patient PII.
    """
    if LOG_REQUEST_BODIES:
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
async def submit_symptom(
    payload: DiagnosisRequest,
    current_user: Optional[dict] = Depends(optional_user),
    x_anon_id: Optional[str] = Header(None, alias="X-Anon-Id"),
):
    """
    Submit patient symptoms for AI analysis with comprehensive error handling.

    Args:
        payload: Validated patient data including name, age, gender, and symptoms

    Returns:
        Dictionary with session ID and processing status
    """
    try:
        # Anonymous visitors get exactly one free diagnosis per device. Gate here,
        # at the very start of the flow, so a second diagnosis never gets past the
        # patient-details step — the first one is never interrupted mid-flow since
        # this check only ever runs before a session is created.
        if not current_user and await anon_entitlements.has_used_free_report(x_anon_id):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "login_required",
                    "message": "You've used your free diagnosis. Please log in or create a free account to continue.",
                },
            )

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

        # Bound memory before adding a new session.
        _evict_stale_sessions()

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
            "feature_ids_asked": [],
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

        # Mirror to MongoDB so other Cloud Run instances (or a restarted one) can serve this session.
        await save_session(session_id, session_store[session_id])

        logger.info("Created session %s for patient %s (age=%s)", session_id, payload.name, payload.age)

        return {
            "message": "Symptoms submitted successfully",
            "status": "symptom_submitted",
            "session_id": session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error processing symptom submission: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Internal server error processing symptom submission"
        )


# NOTE: The unauthenticated /debug_sessions endpoint was removed — it exposed
# every patient's name/age/gender/symptom counts with no auth (privacy leak).

@app.options("/session/{session_id}")
async def options_session(session_id: str):  # pylint: disable=unused-argument
    """Handle OPTIONS requests for /session/{session_id} endpoint"""
    return JSONResponse(content={}, status_code=200)

@app.get("/session/{session_id}")
async def get_session_data(session_id: str):
    """Get session data by ID."""
    try:
        session = await get_or_restore_session(session_id, session_store)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

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
# --- Symptom selection cards (bracket the follow-up questionnaire) ---
#
class SymptomCardSubmission(BaseModel):
    """Selections from a symptom card."""
    offered: List[str] = []       # all symptom labels the card presented
    selected: List[str] = []      # the subset the patient checked
    factors: Dict = {}            # clinical-history answers (initial card only)


@app.options("/symptom_card/{session_id}")
async def options_symptom_card(session_id: str):  # pylint: disable=unused-argument
    return JSONResponse(content={}, status_code=200)


@app.get("/symptom_card/{session_id}")
async def get_symptom_card(session_id: str, stage: str = "initial"):
    """Generate a symptom-selection card (initial before follow-up, midpoint at Q7, refined after)."""
    session = await get_or_restore_session(session_id, session_store)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    patient_state = session.get("patient_state") if isinstance(session.get("patient_state"), dict) else {}
    stage = stage if stage in ("initial", "midpoint", "refined") else "initial"
    try:
        loop = asyncio.get_event_loop()
        card = await loop.run_in_executor(executor, generate_symptom_card, patient_state, stage)
        return JSONResponse(content={"session_id": session_id, **card}, status_code=200)
    except Exception as e:
        logger.exception("Error generating symptom card for %s: %s", session_id, e)
        # Non-fatal: an empty card lets the frontend skip straight to follow-up.
        return JSONResponse(
            content={"session_id": session_id, "stage": stage, "top_conditions": [],
                     "symptoms": [], "clinical_factors": [], "instruction": ""},
            status_code=200,
        )


@app.post("/symptom_card/{session_id}")
async def submit_symptom_card(session_id: str, payload: SymptomCardSubmission):
    """Merge a submitted symptom card into the session's patient_state."""
    session = await get_or_restore_session(session_id, session_store)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    patient_state = session.get("patient_state") if isinstance(session.get("patient_state"), dict) else {}
    try:
        patient_state = apply_symptom_card(
            patient_state, payload.offered, payload.selected, payload.factors
        )
        symptom_state = patient_state.get("symptom_state", {}) if isinstance(patient_state.get("symptom_state"), dict) else {}
        session["patient_state"] = patient_state
        session["symptom_state"] = symptom_state
        session["symptoms"] = patient_state.get("identified_symptoms", [])
        session["negatives"] = patient_state.get("negatives", [])
        session["last_activity"] = datetime.utcnow().isoformat()
        await save_session(session_id, session)
        return {
            "status": "ok",
            "identified_symptoms": patient_state.get("identified_symptoms", []),
            "negatives_count": len(patient_state.get("negatives", [])),
        }
    except Exception as e:
        logger.exception("Error applying symptom card for %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail="Failed to apply symptom card")


#
# --- Robust WebSocket follow-up handler (single handler) ---
#
@app.websocket("/followup/{session_id}")
async def followup_handler(websocket: WebSocket, session_id: str):
    """
    Symptom-driven websocket follow-up flow (delegates to followup.websocket_handler).
    Min {MIN_FOLLOWUP_QUESTIONS}, max {MAX_FOLLOWUP_QUESTIONS} questions.
    """
    await handle_followup_websocket(websocket, session_id, session_store, executor)


@app.options("/generate_report/{session_id}")
async def options_generate_report(session_id: str):  # pylint: disable=unused-argument
    """Handle OPTIONS requests for /generate_report/{session_id} endpoint"""
    return JSONResponse(content={}, status_code=200)

@app.get("/generate_report/{session_id}")
async def generate_report(
    session_id: str,
    lang: str = "en",
    current_user: Optional[dict] = Depends(optional_user),
    x_anon_id: Optional[str] = Header(None, alias="X-Anon-Id"),
):
    """
    Generate medical report for a session with optional language localization.

    Logged-in users consume one report entitlement (the daily free report or a
    paid credit) via billing/entitlements.py. Anonymous visitors get exactly one
    free report per device (billing/anon_entitlements.py) — the /symptom gate
    already blocks a second anonymous diagnosis before it starts, this is the
    defense-in-depth check at generation time.

    Entitlements are only PEEKED here (read-only — fails fast with a clear
    message before spending an LLM call on someone with nothing left) and
    actually CONSUMED further below, only once the report has been generated
    successfully. A failed, interrupted, or cancelled generation never costs a
    credit. Consumption is idempotent and race-safe per session_id, so
    re-fetching, exporting, switching languages, or double-submitting the same
    diagnosis never double-charges.

    Args:
        session_id: The session ID
        lang: Target language code (en, hi, ta, te, bn, kn). Default: "en"

    Returns:
        Report in requested language (localized if lang != "en")
    """
    try:
        if await get_or_restore_session(session_id, session_store) is None:
            raise HTTPException(status_code=404, detail="Session not found")

        # A session whose report was already generated (for free or via
        # credit) at some point is ALWAYS safe to re-fetch — reloading the
        # report page, exporting to PDF, switching language, or a duplicate
        # in-flight request must never be blocked by a balance/allowance that
        # has since been spent elsewhere. Skip the gates entirely in that case.
        already_unlocked = await billing_entitlements.session_already_unlocked(session_id)

        if current_user:
            # --- Peek only: fail fast if nothing is left, don't consume yet ---
            if not already_unlocked:
                balance_peek = billing_entitlements.get_balance(current_user)
                if not balance_peek.get("reports_available"):
                    raise HTTPException(
                        status_code=402,
                        detail={
                            "code": "no_reports_remaining",
                            "message": "No credits left. Please purchase more credits to generate another diagnosis report.",
                            "balance": balance_peek,
                        },
                    )
        else:
            # --- Anonymous: peek at the one free report per device -----------
            if not already_unlocked and await anon_entitlements.has_used_free_report(x_anon_id, session_id):
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": "anon_free_report_used",
                        "message": "You've used your free report. Please log in or create an account to continue.",
                    },
                )

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

            # --- Consume the entitlement now — only now that the report has ---
            # actually been generated. Nothing above this point ever deducts, so
            # an AI-processing failure, a timeout, or the client cancelling the
            # request never costs the user a credit. Idempotent + race-safe per
            # session_id (see billing/entitlements.py / anon_entitlements.py).
            try:
                if current_user:
                    gate = await billing_entitlements.check_and_consume(current_user, session_id)
                    if not gate.get("allowed"):
                        # Balance was available at the peek above but is gone now
                        # (e.g. a concurrent request drained the last credit).
                        # The report is already generated — deliver it rather than
                        # discard completed work; this is not double-billing since
                        # nothing was decremented for this call.
                        logger.warning(
                            "Report generated for session %s but post-generation credit "
                            "consumption was denied (user=%s) — delivering anyway.",
                            session_id, current_user.get("email"),
                        )
                else:
                    if not await anon_entitlements.try_consume(x_anon_id, session_id):
                        logger.warning(
                            "Report generated for anonymous session %s but post-generation "
                            "free-report consumption was denied — delivering anyway.",
                            session_id,
                        )
            except Exception as consume_err:
                logger.error("Entitlement consumption failed for session %s: %s", session_id, consume_err)

            # Record the diagnosis outcome against the user's report history so it
            # shows up in their profile. Best-effort — must never break the report.
            try:
                def _top_disease(rep):
                    matches = rep.get("TopDiseaseMatches") if isinstance(rep, dict) else None
                    if isinstance(matches, list) and matches:
                        first = matches[0]
                        if isinstance(first, dict):
                            for k in ("Disease", "DiseaseName", "Name", "Condition"):
                                if first.get(k):
                                    return str(first[k])
                            dkey = next((k for k in first.keys() if str(k).startswith("Disease")), None)
                            if dkey and first.get(dkey):
                                return str(first[dkey])
                        elif isinstance(first, str):
                            return first
                    return None
                def _all_diseases(rep):
                    out = []
                    matches = rep.get("TopDiseaseMatches") if isinstance(rep, dict) else None
                    if isinstance(matches, list):
                        for m in matches:
                            if isinstance(m, dict):
                                for k in ("Disease", "DiseaseName", "Name", "Condition"):
                                    if m.get(k):
                                        out.append(str(m[k]))
                                        break
                                else:
                                    dk = next((k for k in m.keys() if str(k).startswith("Disease")), None)
                                    if dk and m.get(dk):
                                        out.append(str(m[dk]))
                            elif isinstance(m, str):
                                out.append(m)
                    return out
                _disease = _top_disease(report)
                _symptoms = symptoms if isinstance(symptoms, list) else None
                _summary = (running_summary_for_report or "").strip() or None
                await billing_entitlements.enrich_usage(
                    session_id,
                    disease=_disease,
                    diseases=_all_diseases(report),
                    symptoms=_symptoms,
                    summary=_summary,
                    age=age,
                    gender=gender,
                )
            except Exception as _enrich_err:
                logger.warning("Report-history enrichment skipped: %s", _enrich_err)

            # NOTE: IndicTrans2 translation service integration disabled
            # Currently using Google/Gemini for all translation (via /api/translate)
            # The lang parameter is kept for frontend compatibility but not used for backend translation
            # Frontend handles translation using existing Google/Gemini infrastructure
            
            # Update session with report status
            session["report_generated"] = True
            session["report_timestamp"] = datetime.utcnow().isoformat()
            session["report_language"] = lang
            await save_session(session_id, session)


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