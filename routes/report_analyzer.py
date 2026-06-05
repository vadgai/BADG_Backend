"""
Medical Report Analyzer route for VADG
Handles PDF/Image upload and analysis using Gemini Flash Multimodal
"""

import os
import json
import logging
import re
import tempfile
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Import centralized Gemini API manager
from utils.gemini_api_manager import get_gemini_model, MODEL_NAME, extract_json_from_text

try:
    from database.connection import (
        get_report_analyzer_submissions_collection,
        is_database_available,
    )
except ImportError:
    def get_report_analyzer_submissions_collection():
        return None

    def is_database_available():
        return False

from in_memory_storage import store_report_analyzer_submission_in_memory

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api", tags=["report-analyzer"])

# Get model from centralized manager (with 15-key fallback support)
model_available, model = get_gemini_model()

if model_available:
    logger.info("="*80)
    logger.info(f"✅ Gemini model available for Report Analyzer (via API manager)")
    logger.info(f"   Model: {MODEL_NAME}")
    logger.info("="*80)
else:
    logger.warning("="*80)
    logger.warning("⚠️ Gemini model not available for Report Analyzer")
    logger.warning("   Report analysis features may be limited")
    logger.warning("="*80)

# Rate limiting storage (simple in-memory, production should use Redis)
rate_limit_store: Dict[str, List[float]] = {}

# Allowed file types
ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class ReportAnalysisResponse(BaseModel):
    """Response model for report analysis"""
    summary: Optional[str] = None
    patient: Dict[str, Optional[Any]] = {
        "name": None,
        "age": None,
        "gender": None
    }
    medicines: List[Dict[str, Any]] = []
    symptoms: List[str] = []
    possible_diseases: List[Dict[str, str]] = []
    severity: Dict[str, str] = {
        "patient": "moderate",
        "medicines": "medium"
    }
    disclaimer: str = "This is AI analysis for educational assistance only. Consult a licensed doctor."


def check_rate_limit(ip_address: str, limit: int = 5, window: int = 60) -> bool:
    """
    Simple rate limiting: 5 requests per minute per IP
    """
    current_time = datetime.now().timestamp()
    
    if ip_address not in rate_limit_store:
        rate_limit_store[ip_address] = []
    
    # Remove timestamps older than the window
    rate_limit_store[ip_address] = [
        timestamp for timestamp in rate_limit_store[ip_address]
        if current_time - timestamp < window
    ]
    
    # Check if limit exceeded
    if len(rate_limit_store[ip_address]) >= limit:
        return False
    
    # Add current timestamp
    rate_limit_store[ip_address].append(current_time)
    return True


def remove_pii(text: str) -> str:
    """
    Remove PII (Personally Identifiable Information) from text before sending to Gemini
    - Remove phone numbers (Indian format)
    - Remove Aadhaar numbers
    - Redact full names (keep only first name)
    """
    # Remove Indian phone numbers (10 digits, with optional country code)
    text = re.sub(r'\+?91[-.\s]?\d{10}', '[PHONE_REDACTED]', text)
    text = re.sub(r'\b\d{10}\b', '[PHONE_REDACTED]', text)
    
    # Remove Aadhaar numbers (12 digits, sometimes with spaces/dashes)
    text = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[AADHAAR_REDACTED]', text)
    
    # Note: We keep patient name/age/gender as they're medically relevant
    # But we'll instruct Gemini to not include them in external sharing
    
    return text


def get_gemini_prompt() -> str:
    """
    Refined Gemini prompt for Indian hospital report analysis
    """
    return """You are a medical AI assistant analyzing Indian hospital reports (PDF or Photo).

CRITICAL: First, check if this is a MEDICAL document. If it's an invoice, receipt, exam paper, non-medical document, or contains NO medical information, return this EXACT JSON:
{
  "error": "not_medical",
  "message": "This document does not appear to be a medical report. Please upload a valid medical report or prescription."
}

If it IS a medical document, respond ONLY in valid JSON using EXACT schema below.
If any field is missing or unclear → return null or empty list. Do NOT hallucinate.

Task:
Extract structured analysis:
- 100-150 word summary (clinical reasoning style, explaining what you see in the report)
- Normalize Indian medicine brand names (Crocin/Dolo = Paracetamol, Brufen = Ibuprofen, etc.)
- List medicines with: 
  * name: normalized medicine name
  * dosage: dosage mentioned in report
  * purpose: brief what condition it treats
  * risk: low/medium/high
  * clinical_uses: Array of top 4 major diseases/conditions this medicine is commonly used for
  * symptoms_for_uses: For each disease in clinical_uses, list 3-4 key symptoms that lead to that disease
- List symptoms mentioned in the report
- Infer possible diseases with confidence (low/medium/high)
- Assess severity:
   * patient severity: mild/moderate/severe/critical (based on symptom complexity and test results)
   * medicine severity: low/medium/high (based on drug type risk - antibiotics/steroids are high)

Rules:
- Never state confirmed diagnosis. Always say "possible" or "may indicate".
- Use simple language for patients, medically correct, India context friendly.
- JSON ONLY. No extra text or markdown.
- If report is unclear or illegible, return minimal data with disclaimer.

Expected JSON format:
{
  "summary": "100-150 word clinical reasoning summary here...",
  "patient": {
    "name": "First Name only (if visible, else null)",
    "age": 30,
    "gender": "Male/Female/Other"
  },
  "medicines": [
    {
      "name": "Paracetamol (normalized from Crocin)",
      "dosage": "500mg twice daily",
      "purpose": "Fever and pain relief",
      "risk": "low",
      "clinical_uses": [
        {
          "disease": "Fever",
          "symptoms": ["elevated body temperature", "chills", "sweating", "weakness"]
        },
        {
          "disease": "Headache",
          "symptoms": ["throbbing pain", "sensitivity to light", "tension", "stress"]
        },
        {
          "disease": "Body Ache/Myalgia",
          "symptoms": ["muscle pain", "stiffness", "soreness", "fatigue"]
        },
        {
          "disease": "Arthritis Pain",
          "symptoms": ["joint pain", "swelling", "stiffness", "reduced mobility"]
        }
      ]
    }
  ],
  "symptoms": ["fever", "headache", "body ache"],
  "possible_diseases": [
    {
      "name": "Viral Fever",
      "confidence": "high"
    },
    {
      "name": "Dengue (early stage)",
      "confidence": "low"
    }
  ],
  "severity": {
    "patient": "moderate",
    "medicines": "low"
  },
  "disclaimer": "This is AI analysis for educational assistance only. Consult a licensed doctor."
}

Analyze the report now:"""


async def analyze_with_gemini(file_path: str, mime_type: str) -> Dict[str, Any]:
    """
    Analyze medical report using Gemini Flash Multimodal
    """
    try:
        # Read file
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Get configured Gemini model
        model_available, model_instance = get_gemini_model()
        if not model_available or model_instance is None:
            raise HTTPException(status_code=503, detail="AI service unavailable. Please try again.")
        
        # Prepare file for Gemini
        file_part = {
            "mime_type": mime_type,
            "data": file_data
        }
        
        # Generate content
        prompt = get_gemini_prompt()
        response = model_instance.generate_content([prompt, file_part])
        
        response_text = response.text.strip() if response and response.text else ""
        logger.info(f"Gemini raw response: {response_text[:500]}...")
        
        # Parse JSON from response
        result = extract_json_from_text(response_text)
        if not result:
            logger.error("JSON parsing error: Unable to extract JSON from response")
            logger.error(f"Raw response: {response_text[:2000]}")
            raise HTTPException(status_code=500, detail="Failed to parse AI response. Please try again.")
        
        # Check if this is a non-medical document
        if result.get("error") == "not_medical":
            raise HTTPException(
                status_code=400, 
                detail=result.get("message", "This document does not appear to be a medical report. Please upload a valid medical report or prescription.")
            )
        
        # Validate and ensure all required fields exist
        validated_result = {
            "summary": result.get("summary"),
            "patient": {
                "name": result.get("patient", {}).get("name"),
                "age": result.get("patient", {}).get("age"),
                "gender": result.get("patient", {}).get("gender")
            },
            "medicines": result.get("medicines", []),
            "symptoms": result.get("symptoms", []),
            "possible_diseases": result.get("possible_diseases", []),
            "severity": {
                "patient": result.get("severity", {}).get("patient", "moderate"),
                "medicines": result.get("severity", {}).get("medicines", "medium")
            },
            "disclaimer": "This is AI analysis for educational assistance only. Consult a licensed doctor."
        }
        
        return validated_result
        
    except HTTPException:
        raise

    except Exception as e:
        # Log full error for debugging
        logger.error(f"Gemini analysis error: {e}")

        # Normalize error text for inspection without leaking provider internals to client
        error_text = str(e)
        error_text_lower = error_text.lower()

        # Handle upstream rate limit / quota errors from Gemini explicitly
        if (
            "429" in error_text
            or "rate limit" in error_text_lower
            or "exceeded your current quota" in error_text_lower
            or "resource has been exhausted" in error_text_lower
        ):
            # Match documentation: treat as temporary unavailability due to rate limits
            raise HTTPException(
                status_code=503,
                detail="AI service temporarily unavailable due to rate limits. Please wait about a minute and try again."
            )

        # For all other errors, return a generic AI failure message
        raise HTTPException(
            status_code=500,
            detail="AI analysis failed due to an internal error. Please try again."
        )


def _build_submission_record(
    result: Dict[str, Any],
    client_ip: str,
    file_name: str,
    file_size: int,
) -> Dict[str, Any]:
    """Normalize analysis result for admin dashboard persistence."""
    patient = result.get("patient") or {}
    severity = result.get("severity") or {}
    return {
        "_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow(),
        "patient_name": patient.get("name"),
        "patient_age": patient.get("age"),
        "patient_gender": patient.get("gender"),
        "symptoms": result.get("symptoms") or [],
        "medicines": result.get("medicines") or [],
        "possible_diseases": result.get("possible_diseases") or [],
        "severity_patient": severity.get("patient", "moderate"),
        "severity_medicines": severity.get("medicines", "medium"),
        "summary": result.get("summary"),
        "client_ip": client_ip,
        "file_name": file_name,
        "file_size": file_size,
    }


async def save_report_analyzer_submission(
    result: Dict[str, Any],
    client_ip: str,
    file_name: str,
    file_size: int,
) -> None:
    """Persist report analyzer submission to MongoDB or in-memory fallback."""
    submission = _build_submission_record(result, client_ip, file_name, file_size)
    collection = get_report_analyzer_submissions_collection()

    try:
        if is_database_available() and collection is not None:
            await collection.insert_one(submission)
            logger.info("Saved report analyzer submission for file: %s", file_name)
        else:
            await store_report_analyzer_submission_in_memory(submission)
            logger.info("Saved report analyzer submission in memory for file: %s", file_name)
    except Exception as exc:
        logger.warning("Failed to persist report analyzer submission: %s", exc)


@router.post("/analyze-report")
async def analyze_report(request: Request, file: UploadFile = File(...)):
    """
    Analyze medical report (PDF/JPG/PNG) using Gemini Flash Multimodal
    
    Rate limit: 5 requests per minute per IP
    Max file size: 10MB
    Supported formats: PDF, JPG, PNG
    """
    
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    
    # Rate limiting
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429, 
            detail="Rate limit exceeded. Maximum 5 requests per minute."
        )
    
    # Validate file
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    # Check file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Check file size
    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400, 
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    # Reset file pointer
    await file.seek(0)
    
    # Determine MIME type
    mime_type_map = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png'
    }
    mime_type = mime_type_map.get(file_ext, 'application/octet-stream')
    
    # Save to temporary file
    temp_file = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            tmp.write(file_content)
            temp_file = tmp.name
        
        logger.info(f"Processing report: {file.filename} ({len(file_content)} bytes)")
        
        # Analyze with Gemini
        result = await analyze_with_gemini(temp_file, mime_type)
        
        # Persist submission for admin dashboard (non-blocking for user response)
        await save_report_analyzer_submission(
            result,
            client_ip=client_ip,
            file_name=file.filename or "unknown",
            file_size=len(file_content),
        )
        
        # Log successful analysis (without PII)
        logger.info(f"Analysis complete. Diseases found: {len(result.get('possible_diseases', []))}")
        
        return JSONResponse(content=result, status_code=200)
        
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Unexpected error analyzing report: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
                logger.info(f"Temporary file deleted: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {e}")
