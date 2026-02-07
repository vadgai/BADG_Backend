"""
Model Wrapper with Auto-Logging
Wraps Gemini model calls to automatically log latency and performance
"""

import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .model_logger import log_model_call_async, extract_token_count
from utils.gemini_api_manager import get_gemini_model, generate_content_with_fallback

logger = logging.getLogger(__name__)


class LoggedModelWrapper:
    """
    Wrapper around Gemini model that automatically logs all calls.
    """
    
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self._model = None
        self._model_available = False
    
    def _get_model(self):
        """Get the underlying model instance."""
        if self._model is None:
            self._model_available, self._model = get_gemini_model()
        return self._model_available, self._model
    
    async def generate_content(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Generate content with automatic latency logging.
        
        Args:
            prompt: Prompt text
            session_id: Optional session ID
            endpoint: Optional endpoint that triggered the call
            generation_config: Optional generation config
            metadata: Optional additional metadata
            
        Returns:
            Model response
        """
        input_timestamp = datetime.utcnow()
        start_time = time.time()
        
        model_available, model = self._get_model()
        
        if not model_available or model is None:
            error_msg = "Model not available"
            await log_model_call_async(
                model_name=self.model_name,
                session_id=session_id,
                endpoint=endpoint,
                prompt=prompt,
                success=False,
                error=Exception(error_msg),
                latency_ms=(time.time() - start_time) * 1000,
                metadata=metadata
            )
            raise Exception(error_msg)
        
        try:
            # Generate content
            if generation_config:
                response = model.generate_content(prompt, generation_config=generation_config)
            else:
                response = model.generate_content(prompt)
            
            # Calculate latency
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            
            # Extract token counts
            input_tokens, output_tokens = extract_token_count(response)
            
            # Get response text
            response_text = response.text if hasattr(response, 'text') else str(response)
            
            # Log successful call
            await log_model_call_async(
                model_name=self.model_name,
                session_id=session_id,
                endpoint=endpoint,
                prompt=prompt,
                response=response_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
                latency_ms=latency_ms,
                metadata=metadata
            )
            
            return response
            
        except Exception as e:
            # Calculate latency even on error
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            
            # Log failed call
            await log_model_call_async(
                model_name=self.model_name,
                session_id=session_id,
                endpoint=endpoint,
                prompt=prompt,
                success=False,
                error=e,
                latency_ms=latency_ms,
                metadata=metadata
            )
            
            raise


# Global wrapper instance
_logged_model_wrapper: Optional[LoggedModelWrapper] = None


def get_logged_model(model_name: str = "gemini-2.5-flash") -> LoggedModelWrapper:
    """
    Get a logged model wrapper instance.
    
    Args:
        model_name: Name of the model
        
    Returns:
        LoggedModelWrapper instance
    """
    global _logged_model_wrapper
    
    if _logged_model_wrapper is None or _logged_model_wrapper.model_name != model_name:
        _logged_model_wrapper = LoggedModelWrapper(model_name)
    
    return _logged_model_wrapper


async def generate_content_with_logging(
    prompt: str,
    session_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    model_name: str = "gemini-2.5-flash",
    generation_config: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Generate content with automatic logging using the fallback manager.
    
    This uses the existing generate_content_with_fallback for reliability,
    but also logs the call.
    
    Args:
        prompt: Prompt text
        session_id: Optional session ID
        endpoint: Optional endpoint
        model_name: Model name
        generation_config: Optional generation config
        metadata: Optional metadata
        
    Returns:
        Response text
    """
    input_timestamp = datetime.utcnow()
    start_time = time.time()
    
    try:
        # Use existing fallback manager
        success, response_text, error = generate_content_with_fallback(prompt)
        
        # Calculate latency
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000
        
        # Log the call
        await log_model_call_async(
            model_name=model_name,
            session_id=session_id,
            endpoint=endpoint,
            prompt=prompt,
            response=response_text if success else None,
            success=success,
            error=Exception(error) if error else None,
            latency_ms=latency_ms,
            metadata=metadata
        )
        
        if success:
            return response_text
        else:
            raise Exception(error or "Generation failed")
            
    except Exception as e:
        # Calculate latency
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000
        
        # Log the error
        await log_model_call_async(
            model_name=model_name,
            session_id=session_id,
            endpoint=endpoint,
            prompt=prompt,
            success=False,
            error=e,
            latency_ms=latency_ms,
            metadata=metadata
        )
        
        raise

