# app_simple.py
"""
Simplified VADG API - Core functionality only
This version works without MongoDB and complex dependencies
"""

import asyncio
import json
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional, Union

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator, EmailStr

# Import core modules
from symptom_processing.symptom import hybrid_symptom_extraction
from Followup_Generation.followup import get_followup_for_diagnosis
from symptom_mapping.mapping import get_disease_symptom_mapping
from diagnosis_report.report import final_report

# Load environment variables
load_dotenv()

# Initialize logging
logger = logging.getLogger("uvicorn.error")

# Create FastAPI app
app = FastAPI(
    title="VADG API - Simplified",
    description="AI-Powered Health Insights and Disease Prediction Platform",
    version="2.0.0"
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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=4)

# In-memory session store
session_store: Dict[str, dict] = {}

# In-memory contact submissions store (for simplified version)
contact_submissions: List[Dict] = []

#
# --- Pydantic Models ---
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


# Contact Form Models
class ContactSubmissionCreate(BaseModel):
    """Request model for contact form submission."""
    name: str
    email: str
    message: str
    phone: Optional[str] = None


class ContactSubmission(ContactSubmissionCreate):
    """Complete contact submission model with metadata."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

#
# --- Routes ---
#

@app.get("/")
async def root():
    """Root endpoint for health checks"""
    return {
        "status": "ok",
        "message": "VADG API is running (Simplified Version)",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "symptom": "/symptom",
            "followup": "/followup/{session_id}"
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
        logger.error("Error getting session %s: %s", session_id, str(e))
        raise HTTPException(status_code=404, detail="Session not found")

@app.websocket("/followup/{session_id}")
async def followup_handler(websocket: WebSocket, session_id: str):
    """
    WebSocket followup handler for enhanced patient data
    """
    await websocket.accept()
    logger.info("WebSocket accepted for session %s", session_id)

    try:
        if session_id not in session_store:
            logger.warning("Invalid session_id on websocket connect: %s", session_id)
            await websocket.send_json({"error": "Invalid session_id"})
            await websocket.close(code=1008, reason="Invalid session_id")
            return

        session = session_store[session_id]
        age = session.get("age")
        gender = session.get("gender")
        symptoms = session.get("symptoms")
        chat_history = session.get("chat_history", [])

        # Get enhanced patient data
        weight = session.get("weight")
        height = session.get("height")
        occupation = session.get("occupation")
        location = session.get("location")
        physical_activity = session.get("physical_activity")
        diet_type = session.get("diet_type")

        # initial ping
        await websocket.send_json({"status": "connected"})

        # helper to run blocking generator in threadpool
        async def run_generator(func, *args, **kwargs):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))

        # Generate initial followup safely
        try:
            raw_response = await run_generator(get_followup_for_diagnosis, age, gender, symptoms, chat_history)
        except Exception as e:
            logger.exception("get_followup_for_diagnosis threw during initial generation for session %s: %s", session_id, e)
            await websocket.send_json({"error": "Failed to generate initial question (server error). Please try again."})
            return

        # Handle response
        if isinstance(raw_response, dict) and "Question" in raw_response:
            session["question_count"] = session.get("question_count", 0) + 1
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
            await websocket.send_json({"message": "Ready for diagnosis", "status": "ready_for_diagnosis"})
            await websocket.close(code=1000, reason="Ready for diagnosis")
            return

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
                user_answer = client_msg_clean

            # Add user answer to chat history
            chat_history.append({"user": user_answer})
            session["chat_history"] = chat_history
            
            # Get updated chat history from session to ensure persistence
            updated_chat_history = session.get("chat_history", [])
            
            # Call generator in threadpool for next response
            try:
                next_raw = await run_generator(get_followup_for_diagnosis, age, gender, symptoms, updated_chat_history)
            except Exception as e:
                logger.exception("get_followup_for_diagnosis error mid-conversation for session %s: %s", session_id, e)
                await websocket.send_json({"error": "Failed to process answer (server error)."})
                await websocket.close(code=1011, reason="Internal processing error")
                break

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
                await websocket.send_json({"error": "Unexpected format from generator. Please try again."})

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

@app.get("/generate_report/{session_id}")
async def generate_report(session_id: str):
    """Generate medical report for a session."""
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
            # Update session with report status
            session["report_generated"] = True
            session["report_timestamp"] = datetime.utcnow().isoformat()
            
            response_data = {
                "patient_details": {
                    "name": name,
                    "age": age,
                    "gender": gender
                },
                "report": report,
                "session_id": session_id,
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


@app.post("/api/contact")
async def submit_contact_form(
    contact_data: ContactSubmissionCreate,
    request: Request
):
    """
    Submit contact form data

    This endpoint:
    1. Validates the contact form data
    2. Stores the submission in memory (simplified version)
    3. Returns success response

    Args:
        contact_data: Contact form submission data
        request: FastAPI request object

    Returns:
        Success response with submission confirmation
    """
    logger.info(f"Contact form submission received from: {contact_data.email}")

    try:
        # Create submission object with metadata
        submission = ContactSubmission(
            **contact_data.dict(),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get('user-agent')
        )

        # Store in memory (simplified version)
        contact_submissions.append(submission.dict())

        logger.info(f"Contact submission stored: {contact_data.email}")

        return {
            "success": True,
            "message": "Thank you for your inquiry! We'll get back to you within 48 hours.",
            "submission_id": submission.id
        }

    except Exception as e:
        logger.error(f"Error processing contact form submission: {str(e)}")

        # Return success anyway (graceful degradation)
        return {
            "success": True,
            "message": "Thank you for your inquiry! We'll get back to you within 48 hours.",
            "warning": "Database temporarily unavailable, but your message has been received"
        }


@app.get("/api/contact/health")
async def contact_health_check():
    """
    Health check for contact form functionality

    Returns:
        Health status of contact form endpoints
    """
    health_status = {
        "contact_endpoint": "available",
        "database": "in_memory",
        "submissions_count": len(contact_submissions),
        "timestamp": datetime.utcnow().isoformat()
    }

    return health_status


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

