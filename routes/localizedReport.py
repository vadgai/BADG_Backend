"""
Localized Report API Route
Provides endpoints to localize diagnosis reports into Indian languages.
"""

import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, validator

# Import the localized report builder
from utils.localized_report import localize_diagnosis_report

# Initialize logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    tags=["localized-reports"],
    responses={404: {"description": "Not found"}},
)

# Supported languages
SUPPORTED_LANGUAGES = {"hi", "ta", "te", "bn", "kn"}
LANGUAGE_NAMES = {
    "hi": "Hindi (हिंदी)",
    "ta": "Tamil (தமிழ்)",
    "te": "Telugu (తెలుగు)",
    "bn": "Bengali (বাংলা)",
    "kn": "Kannada (ಕನ್ನಡ)"
}


# ============================================================================
# Pydantic Models
# ============================================================================

class LocalizeReportRequest(BaseModel):
    """Request model for localizing a diagnosis report"""
    report: Dict[str, Any] = Field(..., description="English diagnosis report JSON")
    target_lang: str = Field(..., description="Target language code (hi, ta, te, bn, kn)")
    
    @validator('target_lang')
    def validate_target_lang(cls, v):
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"target_lang must be one of: {', '.join(SUPPORTED_LANGUAGES)}"
            )
        return v.lower()
    
    @validator('report')
    def validate_report(cls, v):
        if not v:
            raise ValueError("report cannot be empty")
        if not isinstance(v, dict):
            raise ValueError("report must be a valid JSON object")
        return v


class LocalizeReportResponse(BaseModel):
    """Response model for localized report"""
    localized_report: Dict[str, Any]
    target_lang: str
    language_name: str
    success: bool = True


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("", response_model=LocalizeReportResponse)
async def localize_report(
    request: Request,
    body: LocalizeReportRequest
):
    """
    Localize a diagnosis report from English to target Indian language.
    
    This endpoint:
    1. Accepts an English diagnosis report JSON
    2. Translates all patient-facing text to the target language
    3. Preserves the original structure and non-translatable data (age, numbers)
    4. Returns the localized report
    
    **Supported Languages:**
    - hi: Hindi (हिंदी)
    - ta: Tamil (தமிழ்)
    - te: Telugu (తెలుగు)
    - bn: Bengali (বাংলা)
    - kn: Kannada (ಕನ್ನಡ)
    
    **What gets translated:**
    - Recommendation
    - Urgency level
    - Main symptoms
    - Diagnostic steps
    - Disease names and match levels
    - Pre-hospital care instructions
    - Symptoms to watch
    - Self-care tips
    - Medication suggestions
    
    **What stays in English:**
    - Age (numbers)
    - Medical abbreviations (CBC, ECG, MRI, etc.)
    - Technical medical terms (when appropriate)
    """
    
    try:
        logger.info(
            f"Localizing report to {body.target_lang}",
            extra={
                "target_lang": body.target_lang,
                "client_ip": request.client.host if request.client else "unknown",
            }
        )
        
        # Localize the report using the translation service
        localized = await localize_diagnosis_report(
            report=body.report,
            target_lang=body.target_lang
        )
        
        if not localized:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to localize report"
            )
        
        logger.info(
            f"✅ Report localized successfully to {body.target_lang}",
            extra={
                "target_lang": body.target_lang,
            }
        )
        
        return LocalizeReportResponse(
            localized_report=localized,
            target_lang=body.target_lang,
            language_name=LANGUAGE_NAMES.get(body.target_lang, body.target_lang),
            success=True
        )
    
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except Exception as e:
        logger.error(
            f"Error localizing report: {str(e)}",
            extra={
                "target_lang": body.target_lang,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to localize report. Please try again."
        )


@router.get("/supported-languages")
async def get_supported_languages():
    """
    Get list of supported languages for report localization.
    """
    return {
        "supported_languages": [
            {"code": code, "name": name}
            for code, name in LANGUAGE_NAMES.items()
        ]
    }


@router.get("/health")
async def localized_report_health():
    """Health check for localized report service"""
    from utils.localized_report import get_localized_report_builder
    
    builder = get_localized_report_builder()
    
    return {
        "status": "healthy",
        "translation_service_configured": bool(builder.translation_endpoint and builder.api_key),
        "supported_languages": list(SUPPORTED_LANGUAGES)
    }

