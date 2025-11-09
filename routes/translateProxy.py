"""
Translation Service Proxy Route
Forwards translation requests to the Translation Service microservice (IndicTrans2 200M).
This route is for internal backend use only - NOT for direct patient-facing translations.
"""

import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, validator

# Environment configuration
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize logging
logger = logging.getLogger(__name__)

# Translation Service configuration
TRANSLATION_SERVICE_URL = os.getenv("TRANSLATION_SERVICE_URL", "http://localhost:8080")
TRANSLATION_SERVICE_API_KEY = os.getenv("TRANSLATION_SERVICE_API_KEY", "")
TRANSLATION_SERVICE_TIMEOUT = int(os.getenv("TRANSLATION_SERVICE_TIMEOUT", "15"))

# Validation
if not TRANSLATION_SERVICE_URL:
    logger.warning("⚠️  TRANSLATION_SERVICE_URL not set - proxy will fail")
if not TRANSLATION_SERVICE_API_KEY:
    logger.warning("⚠️  TRANSLATION_SERVICE_API_KEY not set - proxy will fail")

# Create router
router = APIRouter(
    tags=["translation-proxy"],
    responses={404: {"description": "Not found"}},
)


# ============================================================================
# Pydantic Models
# ============================================================================

class TranslationProxyRequest(BaseModel):
    """Request model for translation proxy"""
    source_lang: str = Field(..., min_length=2, max_length=10)
    target_lang: str = Field(..., min_length=2, max_length=10)
    text: str = Field(..., min_length=1, max_length=5000)
    
    @validator('text')
    def validate_text(cls, v):
        if not v or not v.strip():
            raise ValueError("text cannot be empty")
        return v.strip()
    
    @validator('source_lang', 'target_lang')
    def validate_lang_codes(cls, v):
        if not v or len(v) < 2:
            raise ValueError("language code must be at least 2 characters")
        return v.lower()


class TranslationProxyResponse(BaseModel):
    """Response model from translation service"""
    translation: str
    model_used: str
    cached: bool
    latency_ms: int


# ============================================================================
# Proxy Endpoint
# ============================================================================

@router.post("", response_model=TranslationProxyResponse)
async def proxy_translation(
    request: Request,
    body: TranslationProxyRequest
):
    """
    Proxy translation request to Translation Service microservice.
    
    This endpoint:
    1. Validates input (source_lang, target_lang, text)
    2. Forwards to Translation Service with Authorization header
    3. Returns translation or 502 error if service fails
    
    Logs structured data with request_id, languages, latency, and cache status.
    """
    
    # Generate or extract request ID
    request_id = request.headers.get("x-request-id", str(time.time()))
    
    start_time = time.time()
    
    try:
        # Validate configuration
        if not TRANSLATION_SERVICE_URL:
            logger.error(
                "Translation service URL not configured",
                extra={
                    "request_id": request_id,
                    "error": "TRANSLATION_SERVICE_URL not set"
                }
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "translation failed"}
            )
        
        if not TRANSLATION_SERVICE_API_KEY:
            logger.error(
                "Translation service API key not configured",
                extra={
                    "request_id": request_id,
                    "error": "TRANSLATION_SERVICE_API_KEY not set"
                }
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "translation failed"}
            )
        
        # Prepare request to translation service
        translation_service_endpoint = f"{TRANSLATION_SERVICE_URL.rstrip('/')}/translate"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TRANSLATION_SERVICE_API_KEY}",
            "x-request-id": request_id,
        }
        
        payload = {
            "source_lang": body.source_lang,
            "target_lang": body.target_lang,
            "text": body.text,
        }
        
        logger.info(
            "Forwarding translation request to microservice",
            extra={
                "request_id": request_id,
                "source_lang": body.source_lang,
                "target_lang": body.target_lang,
                "text_length": len(body.text),
                "endpoint": translation_service_endpoint,
            }
        )
        
        # Call translation service
        async with httpx.AsyncClient(timeout=TRANSLATION_SERVICE_TIMEOUT) as client:
            response = await client.post(
                translation_service_endpoint,
                json=payload,
                headers=headers,
            )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Handle successful response (200)
        if response.status_code == 200:
            try:
                result = response.json()
                
                # Extract fields from translation service response
                translation = result.get("translation", "")
                model_used = result.get("model_used", "unknown")
                cached = result.get("cached", False)
                service_latency_ms = result.get("latency_ms", latency_ms)
                
                logger.info(
                    "Translation successful",
                    extra={
                        "request_id": request_id,
                        "source_lang": body.source_lang,
                        "target_lang": body.target_lang,
                        "model_used": model_used,
                        "cached": cached,
                        "latency_ms": latency_ms,
                        "service_latency_ms": service_latency_ms,
                    }
                )
                
                return TranslationProxyResponse(
                    translation=translation,
                    model_used=model_used,
                    cached=cached,
                    latency_ms=latency_ms,
                )
                
            except Exception as e:
                logger.error(
                    "Failed to parse translation service response",
                    extra={
                        "request_id": request_id,
                        "error": str(e),
                        "response_text": response.text[:500],
                        "latency_ms": latency_ms,
                    }
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={"error": "translation failed"}
                )
        
        # Handle non-OK responses from translation service
        else:
            logger.warning(
                "Translation service returned non-OK status",
                extra={
                    "request_id": request_id,
                    "source_lang": body.source_lang,
                    "target_lang": body.target_lang,
                    "status_code": response.status_code,
                    "response_text": response.text[:500],
                    "latency_ms": latency_ms,
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "translation failed"}
            )
    
    except httpx.TimeoutException:
        latency_ms = int((time.time() - start_time) * 1000)
        
        logger.error(
            "Translation service timeout",
            extra={
                "request_id": request_id,
                "source_lang": body.source_lang,
                "target_lang": body.target_lang,
                "timeout_seconds": TRANSLATION_SERVICE_TIMEOUT,
                "latency_ms": latency_ms,
            }
        )
        
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "translation failed"}
        )
    
    except httpx.RequestError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        
        logger.error(
            "Translation service network error",
            extra={
                "request_id": request_id,
                "source_lang": body.source_lang,
                "target_lang": body.target_lang,
                "error": str(e),
                "latency_ms": latency_ms,
            }
        )
        
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "translation failed"}
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions (already handled above)
        raise
    
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        
        logger.error(
            "Unexpected error in translation proxy",
            extra={
                "request_id": request_id,
                "source_lang": body.source_lang,
                "target_lang": body.target_lang,
                "error": str(e),
                "error_type": type(e).__name__,
                "latency_ms": latency_ms,
            }
        )
        
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "translation failed"}
        )


@router.get("/health")
async def proxy_health():
    """Health check for translation proxy"""
    return {
        "status": "healthy",
        "service_url": TRANSLATION_SERVICE_URL if TRANSLATION_SERVICE_URL else "not_configured",
        "api_key_configured": bool(TRANSLATION_SERVICE_API_KEY),
    }


