"""
Translation Proxy Route
Provides safe translation via Google Cloud Translation API (with Gemini fallback) and caching
"""

import hashlib
import logging
import os
import re
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, validator

# Try to import Google Cloud Translation (v3)
try:
    from google.cloud import translate_v3 as translate
    TRANSLATE_CLIENT = translate.TranslationServiceClient()
    TRANSLATE_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("✅ Google Cloud Translation API initialized")
except ImportError:
    TRANSLATE_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️  Google Cloud Translation not available - will use Gemini fallback")
except Exception as e:
    TRANSLATE_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"⚠️  Google Cloud Translation init failed - will use Gemini fallback: {e}")

# Try to import Gemini as fallback (optional)
try:
    import google.generativeai as genai
    # Check for API key in multiple env var names
    GOOGLE_API_KEY = (
        os.getenv("GEMINI_API_KEY_1") or 
        os.getenv("GOOGLE_API_KEY") or 
        os.getenv("GEMINI_API_KEY")
    )
    if GOOGLE_API_KEY and len(GOOGLE_API_KEY) > 20:  # Basic validation
        try:
            genai.configure(api_key=GOOGLE_API_KEY)
            GEMINI_AVAILABLE = True
            logger.info("✅ Gemini API initialized for translation")
        except Exception as e:
            GEMINI_AVAILABLE = False
            logger.warning(f"⚠️  Gemini configuration failed: {e}")
    else:
        GEMINI_AVAILABLE = False
        logger.warning("⚠️  Gemini API key not set or invalid - translation unavailable")
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("⚠️  Gemini not available")

# Initialize logging
logger = logging.getLogger(__name__)

# Google Cloud Project ID from environment
GCLOUD_PROJECT_ID = os.getenv("GCLOUD_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", ""))
if not GCLOUD_PROJECT_ID and TRANSLATE_AVAILABLE:
    logger.warning("⚠️  GCLOUD_PROJECT_ID not set - will use Gemini fallback")

# Constants
SUPPORTED_LANGUAGES = {"hi", "ta", "te", "bn", "kn"}
LANGUAGE_NAMES = {
    "hi": "Hindi (हिंदी)",
    "ta": "Tamil (தமிழ்)",
    "te": "Telugu (తెలుగు)",
    "bn": "Bengali (বাংলা)",
    "kn": "Kannada (ಕನ್ನಡ)"
}
MAX_TEXT_LENGTH = 6000
MAX_BATCH_SIZE = 20
CACHE_TTL_HOURS = 24
MAX_CACHE_ENTRIES = 2000
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 30


# ============================================================================
# Cache Implementation (TTL + LRU)
# ============================================================================

class TranslationCache:
    """In-memory cache with TTL and simple LRU eviction"""
    
    def __init__(self, max_size: int = MAX_CACHE_ENTRIES, ttl_hours: int = CACHE_TTL_HOURS):
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size
        self.ttl = timedelta(hours=ttl_hours)
    
    def _make_key(self, text: str, target_lang: str) -> str:
        """Create cache key from text and language"""
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
        return f"{target_lang}::{text_hash}"
    
    def get(self, text: str, target_lang: str) -> Optional[str]:
        """Retrieve cached translation if valid"""
        key = self._make_key(text, target_lang)
        
        if key in self.cache:
            entry = self.cache[key]
            
            # Check if expired
            if datetime.now() < entry['expires_at']:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return entry['value']
            else:
                # Remove expired entry
                del self.cache[key]
        
        return None
    
    def set(self, text: str, target_lang: str, value: str):
        """Store translation in cache"""
        key = self._make_key(text, target_lang)
        
        # Evict oldest if at capacity
        if len(self.cache) >= self.max_size and key not in self.cache:
            self.cache.popitem(last=False)  # Remove oldest
        
        self.cache[key] = {
            'value': value,
            'expires_at': datetime.now() + self.ttl
        }
        self.cache.move_to_end(key)


# Global cache instance
translation_cache = TranslationCache()


# ============================================================================
# Rate Limiting (Simple IP-based)
# ============================================================================

class SimpleRateLimiter:
    """Simple IP-based rate limiter"""
    
    def __init__(self, window_seconds: int = RATE_LIMIT_WINDOW, max_requests: int = RATE_LIMIT_MAX_REQUESTS):
        self.window = window_seconds
        self.max_requests = max_requests
        self.requests: Dict[str, List[float]] = {}
    
    def is_allowed(self, ip: str) -> bool:
        """Check if request is allowed for IP"""
        now = time.time()
        
        # Clean old entries
        if ip in self.requests:
            self.requests[ip] = [ts for ts in self.requests[ip] if now - ts < self.window]
        else:
            self.requests[ip] = []
        
        # Check limit
        if len(self.requests[ip]) >= self.max_requests:
            return False
        
        # Record request
        self.requests[ip].append(now)
        return True
    
    def cleanup_old_entries(self):
        """Periodic cleanup of old IP records"""
        now = time.time()
        expired_ips = []
        
        for ip, timestamps in self.requests.items():
            # Remove timestamps older than window
            self.requests[ip] = [ts for ts in timestamps if now - ts < self.window]
            
            # Mark for deletion if no recent requests
            if not self.requests[ip]:
                expired_ips.append(ip)
        
        for ip in expired_ips:
            del self.requests[ip]


# Global rate limiter instance
rate_limiter = SimpleRateLimiter()


# ============================================================================
# Pydantic Models
# ============================================================================

class SingleTranslationRequest(BaseModel):
    """Request model for single text translation"""
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    targetLang: str = Field(..., alias="targetLang")
    
    @validator('targetLang')
    def validate_target_lang(cls, v):
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"targetLang must be one of: {', '.join(SUPPORTED_LANGUAGES)}")
        return v
    
    @validator('text')
    def validate_text(cls, v):
        if not v or not v.strip():
            raise ValueError("text cannot be empty")
        return v.strip()


class BatchTranslationRequest(BaseModel):
    """Request model for batch translation"""
    items: List[str] = Field(..., min_items=1, max_items=MAX_BATCH_SIZE)
    targetLang: str = Field(..., alias="targetLang")
    
    @validator('targetLang')
    def validate_target_lang(cls, v):
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"targetLang must be one of: {', '.join(SUPPORTED_LANGUAGES)}")
        return v
    
    @validator('items')
    def validate_items(cls, v):
        if not v:
            raise ValueError("items cannot be empty")
        
        cleaned = []
        for item in v:
            if item and isinstance(item, str):
                cleaned_item = item.strip()
                if cleaned_item and len(cleaned_item) <= MAX_TEXT_LENGTH:
                    cleaned.append(cleaned_item)
        
        if not cleaned:
            raise ValueError("No valid items to translate")
        
        return cleaned


class TranslationResponse(BaseModel):
    """Response model for translations"""
    translated: Union[str, List[str]]


# ============================================================================
# PII Sanitization
# ============================================================================

def sanitize_pii(text: str) -> str:
    """Remove potential PII (emails, phones) from text"""
    # Remove email addresses
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
    
    # Remove phone numbers (various Indian formats)
    text = re.sub(r'(\+91[\-\s]?)?[6-9]\d{9}', '[PHONE]', text)
    text = re.sub(r'\b\d{10}\b', '[PHONE]', text)
    
    return text


# ============================================================================
# Translation Functions (Google Cloud primary, Gemini fallback)
# ============================================================================

def translate_with_gemini_fallback(text: str, target_lang: str) -> str:
    """
    Translate using Gemini (fallback when Google Cloud unavailable)
    """
    try:
        if not GEMINI_AVAILABLE:
            return text
        
        logger.info("Using Gemini fallback for %s", target_lang)
        
        # Sanitize PII
        sanitized_text = sanitize_pii(text)
        
        # Build simple, direct prompt
        lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)
        prompt = f"""Translate this text into SIMPLE conversational {lang_name} used in India.

DO NOT return English sentences. DO NOT mix English words except medical abbreviations (CBC, ECG, MRI, CT).

Use very easy language spoken by normal Indian people.

Keep the medical meaning EXACT.

Return ONLY the translated sentence. No explanation. No quotes.

TEXT TO TRANSLATE:
{sanitized_text}"""
        
        # Call Gemini
        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=8000,
            )
        )
        
        if response and response.text:
            translated = response.text.strip()
            if translated and len(translated) > 0:
                logger.info("Gemini translation: %s...", translated[:80])
                return translated
        
        return text
        
    except Exception as e:
        logger.error("Gemini translation error: %s", e)
        return text


def translate_text_smart(text: str, target_lang: str) -> str:
    """
    Smart translation: Google Cloud (primary) → Gemini (fallback)
    Returns original text on failure (safe fallback)
    """
    
    # Try Google Cloud Translation FIRST (if configured)
    if TRANSLATE_AVAILABLE and GCLOUD_PROJECT_ID:
        try:
            logger.info("[Google Cloud] Translating to %s: %s...", target_lang, text[:100])
            
            # Sanitize PII
            sanitized_text = sanitize_pii(text)
            
            # Preserve medical abbreviations
            medical_abbrevs = ['CBC', 'ECG', 'MRI', 'CT', 'BP', 'HR', 'RR', 'BMI', 'WBC', 'RBC', 'ESR', 'CRP']
            abbrev_map = {}
            protected_text = sanitized_text
            
            for i, abbrev in enumerate(medical_abbrevs):
                placeholder = f"__MED{i}__"
                if abbrev in protected_text:
                    abbrev_map[placeholder] = abbrev
                    protected_text = protected_text.replace(abbrev, placeholder)
            
            # Build request with EXPLICIT source language
            parent = f"projects/{GCLOUD_PROJECT_ID}/locations/global"
            request = translate.TranslateTextRequest(
                parent=parent,
                contents=[protected_text],
                mime_type="text/plain",
                source_language_code="en",  # FORCE source as English
                target_language_code=target_lang,  # FORCE target language
            )
            
            response = TRANSLATE_CLIENT.translate_text(request=request)
            
            if response and response.translations:
                translated = response.translations[0].translated_text.strip()
                
                # Restore medical abbreviations
                for placeholder, abbrev in abbrev_map.items():
                    translated = translated.replace(placeholder, abbrev)
                
                logger.info(
                    "[Google Cloud] Translation successful: %s -> %s",
                    sanitized_text[:60],
                    translated[:60],
                )
                return translated
            
        except Exception as e:
            logger.warning("Google Cloud failed: %s, trying Gemini...", e)
    
    # Fall back to Gemini if Google Cloud fails
    if GEMINI_AVAILABLE:
        try:
            logger.info("[Gemini] Translating to %s: %s...", target_lang, text[:100])
            
            # Sanitize PII
            sanitized_text = sanitize_pii(text)
            lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)
            
            prompt = f"""Translate this text into SIMPLE conversational {lang_name} used in India.

DO NOT return English sentences. DO NOT mix English words except medical abbreviations (CBC, ECG, MRI, CT).

Use very easy language spoken by normal Indian people.

Keep the medical meaning EXACT.

Return ONLY the translated sentence. No explanation. No quotes.

TEXT TO TRANSLATE:
{sanitized_text}"""
            
            model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=8000,
                )
            )
            
            if response and response.text:
                translated = response.text.strip()
                if translated and len(translated) > 0:
                    logger.info(
                        "[Gemini] Translation successful: %s -> %s",
                        text[:60],
                        translated[:60],
                    )
                    return translated
            
            logger.warning("Gemini returned empty response")
            return text
            
        except Exception as e:
            logger.error("Gemini translation failed: %s", e)
            return text
    else:
        logger.warning("No translation service available")
        return text


# ============================================================================
# Router and Endpoints
# ============================================================================

router = APIRouter(
    tags=["translation"],
    responses={404: {"description": "Not found"}},
)


@router.post("", response_model=TranslationResponse)
async def translate_text(
    request: Request,
    body: Union[SingleTranslationRequest, BatchTranslationRequest]
):
    """
    Translate text or batch of texts to target language
    
    Accepts either:
    - { "text": "...", "targetLang": "hi" }
    - { "items": ["...", "..."], "targetLang": "ta" }
    
    Returns:
    - { "translated": "..." } for single
    - { "translated": ["...", "..."] } for batch
    """
    
    # Get client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"
    
    # Rate limit check
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    
    try:
        # Determine if single or batch
        if isinstance(body, SingleTranslationRequest):
            # Single text translation
            text = body.text
            target_lang = body.targetLang
            
            # Check cache
            cached = translation_cache.get(text, target_lang)
            if cached:
                logger.info("Cache hit for language: %s", target_lang)
                return TranslationResponse(translated=cached)
            
            logger.info("Translation request: lang=%s text=%s...", target_lang, text[:100])
            translated = translate_text_smart(text, target_lang)
            logger.info(
                "Translation result: original=%s... translated=%s... unchanged=%s",
                text[:100],
                translated[:100],
                text == translated,
            )
            
            # Cache result
            translation_cache.set(text, target_lang, translated)
            
            return TranslationResponse(translated=translated)
        
        elif isinstance(body, BatchTranslationRequest):
            # Batch translation
            items = body.items
            target_lang = body.targetLang
            
            translated_items = []
            
            for item in items:
                # Check cache first
                cached = translation_cache.get(item, target_lang)
                if cached:
                    logger.info("Cache hit for batch item %s", len(translated_items) + 1)
                    translated_items.append(cached)
                else:
                    # Translate using smart translation (Google Cloud or Gemini)
                    translated = translate_text_smart(item, target_lang)
                    
                    # Cache result
                    translation_cache.set(item, target_lang, translated)
                    
                    translated_items.append(translated)
            
            return TranslationResponse(translated=translated_items)
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid request format"
            )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Translation endpoint error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Translation service temporarily unavailable"
        )


@router.get("/health")
async def translation_health():
    """Health check for translation service"""
    return {
        "status": "healthy",
        "cache_size": len(translation_cache.cache),
        "supported_languages": list(SUPPORTED_LANGUAGES)
    }

