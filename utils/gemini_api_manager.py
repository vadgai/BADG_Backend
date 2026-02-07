"""
Centralized Gemini API Key Manager with Fallback Support
Manages up to 15 API keys with automatic fallback when one fails.
Automatically rotates through keys when encountering 429 (quota exceeded) errors.
"""

import os
import json
import logging
import time
from typing import Optional, Tuple
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model configuration
MODEL_NAME = "gemini-2.5-flash"

# Global state
_current_api_key_index = 0
_api_keys = []
_current_model = None
_model_available = False


def _load_api_keys():
    """Load all available API keys from environment variables.
    
    Works in both development (.env file) and production (system environment variables).
    In production, environment variables are set in the deployment platform (e.g., Google Cloud Run).
    """
    global _api_keys
    
    # Try multiple .env file locations (Backend/.env and root/.env)
    import pathlib
    current_file = pathlib.Path(__file__).resolve()
    backend_dir = current_file.parent.parent  # Go up from utils/ to Backend/
    root_dir = backend_dir.parent  # Go up from Backend/ to root/
    
    # Try loading from Backend/.env first, then root/.env
    env_paths = [
        backend_dir / ".env",  # Backend/.env
        root_dir / ".env",     # root/.env
        pathlib.Path(".env"),  # Current directory
    ]
    
    loaded_from = None
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            loaded_from = env_path
            logger.debug(f"Loaded .env from: {env_path}")
            break
    
    # Also try default load_dotenv() if no .env file found in expected locations
    if not loaded_from:
        load_dotenv(override=False)  # Try default location
    
    # Check for individual GEMINI_API_KEY_1 through GEMINI_API_KEY_15 (support up to 15 keys)
    keys = []
    for i in range(1, 16):  # Changed from 21 to 16 to limit to 15 keys
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key:
            key = key.strip()  # Remove whitespace
            # Remove quotes if present (common .env file issue)
            if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
                key = key[1:-1].strip()
            if key:  # Ensure key is not empty after processing
                keys.append(key)
    
    # Also check legacy single key variables as fallbacks
    if not keys:
        legacy_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if legacy_key:
            legacy_key = legacy_key.strip()
            # Remove quotes if present
            if (legacy_key.startswith('"') and legacy_key.endswith('"')) or (legacy_key.startswith("'") and legacy_key.endswith("'")):
                legacy_key = legacy_key[1:-1].strip()
            if legacy_key:
                keys.append(legacy_key)
    
    _api_keys = keys
    
    if not _api_keys:
        logger.warning("="*80)
        logger.warning("⚠️ No Gemini API keys found!")
        logger.warning("   Checked environment variables: GEMINI_API_KEY_1 through GEMINI_API_KEY_15")
        logger.warning("   Also checked legacy: GOOGLE_API_KEY, GEMINI_API_KEY")
        if loaded_from:
            logger.warning(f"   Loaded .env from: {loaded_from}")
        else:
            logger.warning("   No .env file found in Backend/ or root/ directory")
        logger.warning("   Please set at least one API key in .env file or environment variables")
        logger.warning("="*80)
    else:
        logger.info("="*80)
        logger.info(f"✅ Loaded {len(_api_keys)} Gemini API key(s)")
        if loaded_from:
            logger.info(f"   Source: {loaded_from}")
        for idx, key in enumerate(_api_keys, 1):
            logger.info(f"   Key {idx}: {key[:15]}...{key[-5:]}" if len(key) > 20 else f"   Key {idx}: {key}")
        logger.info("="*80)
    
    return _api_keys


def _try_configure_model(api_key: str, key_index: int) -> Tuple[bool, Optional[object]]:
    """
    Try to configure and create a model with the given API key.
    Returns (success: bool, model: Optional[GenerativeModel])
    """
    try:
        logger.info(f"🔧 Attempting to configure with API key #{key_index + 1}...")
        logger.info(f"   Model name: {MODEL_NAME}")
        logger.info(f"   API key prefix: {api_key[:10]}..." if len(api_key) > 10 else "   API key: [too short]")
        
        # Configure the API key
        genai.configure(api_key=api_key)
        
        # Try to create the model - this will fail if the model name is invalid
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            logger.info(f"✅ Model '{MODEL_NAME}' created successfully")
        except Exception as model_error:
            error_msg = str(model_error)
            logger.error(f"❌ Failed to create model '{MODEL_NAME}': {error_msg}")
            
            # Check for common errors
            if "404" in error_msg or "not found" in error_msg.lower():
                logger.error(f"   Model '{MODEL_NAME}' not found. This might indicate:")
                logger.error(f"   - The model name is incorrect")
                logger.error(f"   - The SDK version doesn't support this model")
                logger.error(f"   - The API key doesn't have access to this model")
            elif "403" in error_msg or "permission" in error_msg.lower():
                logger.error(f"   Permission denied. Check API key permissions.")
            elif "401" in error_msg or "invalid" in error_msg.lower():
                logger.error(f"   API key authentication failed. Check if the key is valid.")
            
            return False, None
        
        # Optionally verify the model is accessible
        try:
            genai.get_model(MODEL_NAME)
            logger.info(f"✅ Model '{MODEL_NAME}' verified and accessible")
        except Exception as e:
            # Some SDK versions don't support get_model, that's OK
            logger.debug(f"⚠️ Model verification skipped: {e}")
        
        logger.info(f"✅ Successfully configured with API key #{key_index + 1}")
        return True, model
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Failed to configure with API key #{key_index + 1}: {error_msg}")
        logger.error(f"   Error type: {type(e).__name__}")
        
        # Provide helpful error messages
        if "API key" in error_msg or "401" in error_msg:
            logger.error("   Issue: API key authentication failed")
        elif "404" in error_msg or "not found" in error_msg:
            logger.error(f"   Issue: Model '{MODEL_NAME}' not found")
        elif "403" in error_msg or "permission" in error_msg.lower():
            logger.error("   Issue: Permission denied")
        
        return False, None


def _validate_production_keys():
    """Validate that API keys are set in production environment."""
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    
    if not is_production:
        return True  # Skip validation in development
    
    keys = _load_api_keys()
    
    if not keys:
        error_msg = (
            "=" * 80 + "\n"
            "❌ PRODUCTION ERROR: No Gemini API keys found!\n"
            "=" * 80 + "\n"
            "In production, you MUST set at least one Gemini API key:\n"
            "  - GEMINI_API_KEY_1 through GEMINI_API_KEY_15 (recommended)\n"
            "  - Or legacy: GOOGLE_API_KEY or GEMINI_API_KEY\n"
            "\n"
            "Set them in your deployment platform:\n"
            "  - Google Cloud Run: Environment Variables section\n"
            "  - Or via gcloud: --set-env-vars=\"GEMINI_API_KEY_1=your-key\"\n"
            "\n"
            "The application will not function properly without API keys.\n"
            "=" * 80
        )
        logger.error(error_msg)
        raise RuntimeError(
            "PRODUCTION ERROR: Gemini API keys are required but not configured. "
            "Set GEMINI_API_KEY_1 in environment variables."
        )
    
    return True


def _initialize_model():
    """Initialize the Gemini model with fallback support."""
    global _current_api_key_index, _current_model, _model_available
    
    # Validate keys in production before attempting initialization
    _validate_production_keys()
    
    # Load API keys
    keys = _load_api_keys()
    
    if not keys:
        logger.error("❌ No API keys available for initialization")
        _model_available = False
        return False
    
    # Try each key in sequence
    for idx, key in enumerate(keys):
        success, model = _try_configure_model(key, idx)
        if success and model:
            _current_api_key_index = idx
            _current_model = model
            _model_available = True
            logger.info("="*80)
            logger.info(f"🎉 GEMINI API INITIALIZED SUCCESSFULLY")
            logger.info(f"   Using API key #{idx + 1} of {len(keys)}")
            logger.info(f"   Model: {MODEL_NAME}")
            logger.info("="*80)
            return True
    
    # If we get here, all keys failed with SDK
    # Try direct HTTP test on first key to diagnose if it's an SDK issue
    if keys:
        logger.warning("="*80)
        logger.warning("⚠️ SDK initialization failed for all keys")
        logger.warning("   Testing first API key with direct HTTP request (curl-like)...")
        logger.warning("="*80)
        direct_success, direct_error = test_api_key_direct(keys[0])
        if direct_success:
            logger.error("="*80)
            logger.error("❌ DIAGNOSIS: API key works with direct HTTP, but SDK fails!")
            logger.error(f"   This suggests an SDK compatibility issue.")
            logger.error(f"   - SDK version might be too old")
            logger.error(f"   - Model name '{MODEL_NAME}' might not be supported by current SDK")
            logger.error(f"   - Try upgrading: pip install --upgrade google-generativeai")
            logger.error("="*80)
        else:
            logger.error("="*80)
            logger.error("❌ DIAGNOSIS: API key also fails with direct HTTP request")
            logger.error(f"   Error: {direct_error}")
            logger.error(f"   This suggests an API key or model access issue.")
            logger.error("="*80)
    
    logger.error("="*80)
    logger.error("❌ ALL API KEYS FAILED!")
    logger.error(f"   Tried {len(keys)} API key(s)")
    logger.error("   Please check your API keys and quotas")
    logger.error("="*80)
    _model_available = False
    return False


def _try_next_api_key() -> bool:
    """
    Try the next available API key when the current one fails.
    Returns True if a new working key was found, False otherwise.
    """
    global _current_api_key_index, _current_model, _model_available
    
    if not _api_keys:
        return False
    
    # Calculate starting point (next key after current)
    start_index = (_current_api_key_index + 1) % len(_api_keys)
    
    # Try all remaining keys
    for offset in range(len(_api_keys)):
        idx = (start_index + offset) % len(_api_keys)
        
        # Skip if this is the current failing key
        if idx == _current_api_key_index:
            continue
        
        logger.info(f"🔄 Trying fallback API key #{idx + 1}...")
        success, model = _try_configure_model(_api_keys[idx], idx)
        
        if success and model:
            _current_api_key_index = idx
            _current_model = model
            _model_available = True
            logger.info(f"✅ Successfully failed over to API key #{idx + 1}")
            return True
    
    # All keys exhausted
    logger.error("❌ All API keys exhausted. No working keys available.")
    _model_available = False
    return False


def try_next_api_key() -> bool:
    """
    Public wrapper for trying the next available API key.
    Use this when you want to manually trigger a fallback to the next API key.
    
    Returns:
        True if a new working key was found, False otherwise
    """
    return _try_next_api_key()


def get_gemini_model(retry_on_failure: bool = True) -> Tuple[bool, Optional[object]]:
    """
    Get the current Gemini model instance with automatic fallback support.
    
    Args:
        retry_on_failure: If True, will attempt to use next API key on failure
    
    Returns:
        Tuple of (model_available: bool, model: Optional[GenerativeModel])
    
    Example:
        model_available, model = get_gemini_model()
        if model_available:
            response = model.generate_content(prompt)
    """
    global _current_model, _model_available
    
    # Initialize on first call
    if _current_model is None and not _model_available:
        _initialize_model()
    
    return _model_available, _current_model


def generate_content_with_fallback(
    prompt: str, 
    max_retries: int = None,
    system_instruction: Optional[str] = None,
    temperature: float = 0.3,
    max_output_tokens: int = 4000
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Generate content with automatic API key fallback on failure.
    Optimized for fast failure handling: 0.1s sleep between keys, 10s hard timeout.
    
    Args:
        prompt: The prompt/user content to send to the model
        max_retries: Maximum number of API keys to try (default: try all keys)
        system_instruction: Optional system instruction to guide model behavior
        temperature: Temperature for generation (default: 0.3 for more deterministic output)
        max_output_tokens: Maximum tokens in response (default: 4000 for comprehensive reports)
    
    Returns:
        Tuple of (success: bool, response_text: Optional[str], error: Optional[str])
    
    Example:
        success, response, error = generate_content_with_fallback("What is AI?")
        if success:
            print(response)
        else:
            print(f"Error: {error}")
    """
    # Hard timeout: 30 seconds maximum for entire generation process (increased to allow trying all 15 keys)
    HARD_TIMEOUT_SECONDS = 30.0
    start_time = time.time()
    
    # Always try ALL available keys (up to 15) when one fails
    # If max_retries is None or 0, use all available keys (max 15)
    # Even if max_retries is specified, we should try all keys sequentially until one works
    available_keys = min(len(_api_keys), 15) if _api_keys else 1
    if max_retries is None or max_retries == 0:
        max_retries = available_keys
    else:
        # Force trying all available keys (up to 15) regardless of max_retries parameter
        # This ensures if first key fails, we try all remaining keys until one works
        if max_retries < available_keys:
            logger.info(f"🔧 max_retries ({max_retries}) specified, but will try all available keys ({available_keys}) for fallback.")
            max_retries = available_keys
    
    attempts = 0
    
    while attempts < max_retries:
        # Check hard timeout before each attempt
        elapsed_time = time.time() - start_time
        if elapsed_time >= HARD_TIMEOUT_SECONDS:
            timeout_error = f"Hard timeout exceeded ({HARD_TIMEOUT_SECONDS}s). Tried {attempts} key(s)."
            logger.error(f"❌ {timeout_error}")
            return False, None, timeout_error
        
        # Calculate remaining time for this attempt
        remaining_time = HARD_TIMEOUT_SECONDS - elapsed_time
        model_available, model = get_gemini_model()
        
        if not model_available or model is None:
            return False, None, "No working API keys available"
        
        try:
            logger.debug(f"Attempting generation with API key #{_current_api_key_index + 1}")
            if system_instruction:
                logger.debug(f"System instruction length: {len(system_instruction)} chars")
            logger.debug(f"User prompt length: {len(prompt)} chars")
            
            # Build generation config with proper settings for strict rule following
            try:
                generation_config = genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    top_p=0.95,
                    top_k=40,
                    response_mime_type="application/json",
                )
            except (ImportError, AttributeError, TypeError):
                # Fallback to dict if types not available
                generation_config = {
                    "temperature": temperature,
                    "max_output_tokens": max_output_tokens,
                    "top_p": 0.95,
                    "top_k": 40,
                    "response_mime_type": "application/json",
                }
            
            # Generate with timeout configuration (use remaining time from hard timeout, max 9s per request)
            # system_instruction should be passed as a separate parameter, not in config
            try:
                import google.api_core.timeout as timeout_lib
                # Use remaining time or max 9 seconds (leaving 1s buffer for processing)
                request_timeout = min(remaining_time, 9.0) if remaining_time > 0 else 1.0
                timeout = timeout_lib.Timeout(timeout=request_timeout)
                
                # Try passing system_instruction as a direct parameter
                if system_instruction:
                    try:
                        response = model.generate_content(
                            prompt,
                            system_instruction=system_instruction,
                            generation_config=generation_config,
                            request_options={"timeout": timeout}
                        )
                        logger.debug("✅ Used system_instruction as direct parameter")
                    except (TypeError, AttributeError) as si_error:
                        # If system_instruction parameter not supported, prepend to prompt
                        logger.warning(f"⚠️ system_instruction parameter not supported, prepending to prompt: {si_error}")
                        full_prompt = f"SYSTEM INSTRUCTION:\n{system_instruction}\n\nUSER REQUEST:\n{prompt}"
                        response = model.generate_content(
                            full_prompt,
                            generation_config=generation_config,
                            request_options={"timeout": timeout}
                        )
                else:
                    response = model.generate_content(
                        prompt,
                        generation_config=generation_config,
                        request_options={"timeout": timeout}
                    )
            except (ImportError, AttributeError):
                # Fallback if timeout configuration is not available
                if system_instruction:
                    try:
                        response = model.generate_content(
                            prompt,
                            system_instruction=system_instruction,
                            generation_config=generation_config
                        )
                        logger.debug("✅ Used system_instruction as direct parameter (no timeout)")
                    except (TypeError, AttributeError):
                        # If system_instruction parameter not supported, prepend to prompt
                        logger.warning("⚠️ system_instruction parameter not supported, prepending to prompt")
                        full_prompt = f"SYSTEM INSTRUCTION:\n{system_instruction}\n\nUSER REQUEST:\n{prompt}"
                        response = model.generate_content(full_prompt, generation_config=generation_config)
                else:
                    response = model.generate_content(prompt, generation_config=generation_config)
                    
            logger.debug(f"✅ Generation successful with API key #{_current_api_key_index + 1}")
            logger.debug(f"Response length: {len(response.text) if response.text else 0} chars")
            return True, response.text, None
            
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            logger.error(f"❌ Generation failed with API key #{_current_api_key_index + 1}")
            logger.error(f"   Error type: {error_type}")
            logger.error(f"   Error message: {error_msg}")
            
            # Log more details for debugging
            if hasattr(e, '__dict__'):
                logger.debug(f"   Error details: {e.__dict__}")
            
            # Check for rate limiting (429 Quota Exceeded) or other errors
            is_rate_limit = "429" in error_msg or "quota" in error_msg.lower() or "ResourceExhausted" in error_type
            
            # Check if we have more keys to try
            keys_tried = attempts + 1
            keys_remaining = max(0, max_retries - keys_tried)
            
            # If we have more keys available, switch immediately with minimal delay (0.1s)
            # Only use long backoff if retrying the same key (which we don't do for 429s)
            if keys_remaining > 0:
                # Fast key switching: only 0.1s delay when moving to next key
                if is_rate_limit:
                    logger.warning(f"⚠️ Rate limit (429) detected with key #{_current_api_key_index + 1}. Rotating to next API key (attempt {keys_tried + 1}/{max_retries})...")
                else:
                    logger.warning(f"⚠️ Error with key #{_current_api_key_index + 1}. Switching to next key in 0.1s...")
                time.sleep(0.1)  # Minimal delay for key switching
            else:
                # No more keys available - this is the last attempt
                logger.error(f"❌ Last key failed. No more keys to try (tried {keys_tried} keys).")
            
            # Check hard timeout before trying next key
            elapsed_time = time.time() - start_time
            if elapsed_time >= HARD_TIMEOUT_SECONDS:
                timeout_error = f"Hard timeout exceeded ({HARD_TIMEOUT_SECONDS}s). Tried {keys_tried} key(s). Last error ({error_type}): {error_msg}"
                logger.error(f"❌ {timeout_error}")
                return False, None, timeout_error
            
            # Try next API key (if available and within timeout)
            # Always try to switch to next key if we haven't exhausted all keys
            if attempts < max_retries - 1:
                success = _try_next_api_key()
                if not success:
                    logger.error(f"❌ Could not switch to next API key. All keys may be exhausted.")
                    return False, None, f"All API keys exhausted. Last error ({error_type}): {error_msg}"
                # Continue loop to try next key
            else:
                # We've tried all keys, no more to try
                error_summary = f"All {max_retries} API key(s) exhausted. Last error ({error_type}): {error_msg}"
                logger.error(f"❌ {error_summary}")
                
                # Provide more detailed error message for user
                if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    detailed_error = f"All {max_retries} API keys timed out. Request exceeded 30s timeout. This might indicate network issues or API is slow."
                elif "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower() or "ResourceExhausted" in error_type:
                    detailed_error = f"All {max_retries} API keys hit rate limits or quota exhausted. Please try again later or check API key quotas."
                elif "401" in error_msg or "403" in error_msg or "invalid" in error_msg.lower() or "unauthorized" in error_msg.lower():
                    detailed_error = f"All {max_retries} API keys appear to be invalid, expired, or unauthorized. Please verify your API keys are correct and active."
                elif "404" in error_msg or "not found" in error_msg.lower():
                    detailed_error = f"API endpoint or model not found. This might indicate an SDK version issue. Error: {error_msg[:200]}"
                else:
                    detailed_error = f"All {max_retries} API keys failed with error: {error_type}: {error_msg[:200]}"
                
                return False, None, detailed_error
        
        attempts += 1
    
    return False, None, "Max retries reached without success"


def extract_json_from_text(text: str) -> Optional[dict]:
    """
    Robustly extract and parse JSON from text that might contain markdown or extra text.
    """
    if not text:
        return None
        
    text = text.strip()
    
    # 1. Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
        
    # 2. Try to find JSON block with regex
    import re
    # Look for ```json ... ``` or just ``` ... ```
    code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass
            
    # 3. Try to find first { and last }
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1:
        try:
            return json.loads(text[first_brace:last_brace+1])
        except json.JSONDecodeError:
            pass
            
    return None


def test_all_api_keys() -> dict:
    """
    Test all configured API keys and return their status.
    
    Returns:
        Dictionary with test results for each key
    """
    results = {
        "total_keys": 0,
        "working_keys": 0,
        "failed_keys": 0,
        "keys": []
    }
    
    keys = _load_api_keys()
    results["total_keys"] = len(keys)
    
    for idx, key in enumerate(keys):
        key_result = {
            "index": idx + 1,
            "key_prefix": key[:10] + "..." if len(key) > 10 else key,
            "status": "unknown",
            "error": None
        }
        
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(MODEL_NAME)
            
            # Try a simple generation to verify the key works
            test_response = model.generate_content("Say 'API key works'")
            
            if test_response and test_response.text:
                key_result["status"] = "working"
                results["working_keys"] += 1
                logger.info(f"✅ API Key #{idx + 1}: WORKING")
            else:
                key_result["status"] = "failed"
                key_result["error"] = "No response from API"
                results["failed_keys"] += 1
                logger.error(f"❌ API Key #{idx + 1}: FAILED (no response)")
                
        except Exception as e:
            key_result["status"] = "failed"
            key_result["error"] = str(e)
            results["failed_keys"] += 1
            logger.error(f"❌ API Key #{idx + 1}: FAILED ({e})")
        
        results["keys"].append(key_result)
    
    return results


def get_current_key_info() -> dict:
    """
    Get information about the currently active API key.
    
    Returns:
        Dictionary with current key information
    """
    return {
        "current_index": _current_api_key_index + 1 if _api_keys else 0,
        "total_keys": len(_api_keys),
        "model_available": _model_available,
        "model_name": MODEL_NAME
    }


def test_api_key_direct(api_key: str) -> Tuple[bool, Optional[str]]:
    """
    Test an API key directly with a simple HTTP request to verify it works.
    This mimics what curl does - direct API call using the REST endpoint.
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        import httpx
        
        # Use the same endpoint that curl uses: v1beta endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": "Say 'API key works'"
                }]
            }]
        }
        
        params = {
            "key": api_key
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            if "candidates" in data and len(data["candidates"]) > 0:
                logger.info(f"✅ Direct API test successful (curl-like request to v1beta endpoint)")
                return True, None
            else:
                return False, "Invalid response format"
        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            logger.error(f"❌ Direct API test failed: {error_msg}")
            return False, error_msg
            
    except ImportError:
        logger.warning("⚠️ httpx library not available for direct API test")
        return False, "httpx library not available"
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Direct API test exception: {error_msg}")
        return False, error_msg


# Initialize on module import
logger.info("🚀 Initializing Gemini API Manager...")
_initialize_model()

