"""
API utilities for VADG API.
Provides common functions for request/response handling and data processing.
"""

import json
import asyncio
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from .models import DiagnosisRequest, ErrorResponse
from .logging_config import get_logger
from .exceptions import VADGException, InvalidPatientDataError, AIProcessingError

logger = get_logger("api_utils")


def create_success_response(
    message: str,
    data: Optional[Dict[str, Any]] = None,
    status_code: int = 200
) -> JSONResponse:
    """
    Create a standardized success response.
    
    Args:
        message: Success message
        data: Optional response data
        status_code: HTTP status code
        
    Returns:
        JSONResponse object
    """
    response_data = {
        "success": True,
        "message": message,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if data:
        response_data["data"] = data
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )


def create_error_response(
    error: str,
    detail: Optional[str] = None,
    status_code: int = 400,
    request_id: Optional[str] = None
) -> JSONResponse:
    """
    Create a standardized error response.
    
    Args:
        error: Error message
        detail: Optional error details
        status_code: HTTP status code
        request_id: Optional request ID
        
    Returns:
        JSONResponse object
    """
    response_data = {
        "success": False,
        "error": error,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if detail:
        response_data["detail"] = detail
    
    if request_id:
        response_data["request_id"] = request_id
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )


def validate_patient_data(data: Dict[str, Any]) -> DiagnosisRequest:
    """
    Validate and parse patient data from request.
    
    Args:
        data: Raw patient data from request
        
    Returns:
        Validated DiagnosisRequest object
        
    Raises:
        InvalidPatientDataError: If validation fails
    """
    try:
        # Convert to DiagnosisRequest for validation
        request = DiagnosisRequest(**data)
        
        # Additional validation
        if not request.symptoms:
            raise InvalidPatientDataError("At least one symptom is required", "symptoms")
        
        if request.age is not None and (request.age < 0 or request.age > 150):
            raise InvalidPatientDataError("Age must be between 0 and 150", "age")
        
        return request
        
    except Exception as e:
        if isinstance(e, InvalidPatientDataError):
            raise
        logger.error(f"Error validating patient data: {e}")
        raise InvalidPatientDataError(f"Invalid patient data: {str(e)}")


def sanitize_input(text: str) -> str:
    """
    Sanitize user input to prevent injection attacks.
    
    Args:
        text: Input text to sanitize
        
    Returns:
        Sanitized text
    """
    if not isinstance(text, str):
        return str(text)
    
    # Remove potentially dangerous characters
    dangerous_chars = ['<', '>', '"', "'", '&', '\x00', '\r', '\n']
    for char in dangerous_chars:
        text = text.replace(char, '')
    
    # Limit length
    if len(text) > 1000:
        text = text[:1000] + "..."
    
    return text.strip()


def extract_request_info(request: Request) -> Dict[str, Any]:
    """
    Extract useful information from FastAPI request.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Dictionary with request information
    """
    return {
        "method": request.method,
        "url": str(request.url),
        "path": request.url.path,
        "query_params": dict(request.query_params),
        "client_ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "content_type": request.headers.get("content-type", "unknown"),
        "request_id": getattr(request.state, "request_id", None)
    }


def format_symptoms_for_ai(symptoms: List[str]) -> str:
    """
    Format symptoms list for AI processing.
    
    Args:
        symptoms: List of symptoms
        
    Returns:
        Formatted symptoms string
    """
    if not symptoms:
        return ""
    
    # Clean and format symptoms
    cleaned_symptoms = [sanitize_input(symptom) for symptom in symptoms if symptom.strip()]
    
    if len(cleaned_symptoms) == 1:
        return cleaned_symptoms[0]
    elif len(cleaned_symptoms) == 2:
        return f"{cleaned_symptoms[0]} and {cleaned_symptoms[1]}"
    else:
        return f"{', '.join(cleaned_symptoms[:-1])}, and {cleaned_symptoms[-1]}"


def format_chat_history_for_ai(chat_history: List[Dict[str, Any]]) -> str:
    """
    Format chat history for AI processing.
    
    Args:
        chat_history: List of chat messages
        
    Returns:
        Formatted chat history string
    """
    if not chat_history:
        return ""
    
    formatted_messages = []
    for message in chat_history:
        if "user" in message:
            formatted_messages.append(f"User: {message['user']}")
        elif "bot" in message:
            formatted_messages.append(f"Bot: {message['bot']}")
    
    return "\n".join(formatted_messages)


def safe_json_parse(json_string: str, default: Any = None) -> Any:
    """
    Safely parse JSON string with error handling.
    
    Args:
        json_string: JSON string to parse
        default: Default value if parsing fails
        
    Returns:
        Parsed JSON or default value
    """
    try:
        return json.loads(json_string)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse JSON: {e}")
        return default


def validate_ai_response(response: str, expected_keys: List[str] = None) -> Dict[str, Any]:
    """
    Validate AI response format and content.
    
    Args:
        response: AI response string
        expected_keys: List of expected keys in response
        
    Returns:
        Parsed and validated response dictionary
        
    Raises:
        AIProcessingError: If validation fails
    """
    try:
        # Try to parse as JSON
        parsed_response = safe_json_parse(response)
        
        if not isinstance(parsed_response, dict):
            raise AIProcessingError("AI response is not a valid JSON object", "response_parsing")
        
        # Check for expected keys
        if expected_keys:
            missing_keys = [key for key in expected_keys if key not in parsed_response]
            if missing_keys:
                raise AIProcessingError(f"Missing required keys: {missing_keys}", "response_validation")
        
        return parsed_response
        
    except AIProcessingError:
        raise
    except Exception as e:
        logger.error(f"Error validating AI response: {e}")
        raise AIProcessingError(f"Failed to validate AI response: {str(e)}", "response_validation")


def create_ai_prompt(
    prompt_type: str,
    patient_data: Dict[str, Any],
    additional_context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create standardized AI prompts based on type.
    
    Args:
        prompt_type: Type of prompt (symptom_extraction, diagnosis, followup, report)
        patient_data: Patient information
        additional_context: Additional context for the prompt
        
    Returns:
        Formatted prompt string
    """
    base_context = {
        "patient_name": patient_data.get("name", "Unknown"),
        "patient_age": patient_data.get("age", "Unknown"),
        "patient_gender": patient_data.get("gender", "Unknown"),
        "symptoms": format_symptoms_for_ai(patient_data.get("symptoms", [])),
        "chat_history": format_chat_history_for_ai(patient_data.get("chat_history", []))
    }
    
    if additional_context:
        base_context.update(additional_context)
    
    prompts = {
        "symptom_extraction": f"""
        Extract medical symptoms from the following patient information:
        Name: {base_context['patient_name']}
        Age: {base_context['patient_age']}
        Gender: {base_context['patient_gender']}
        Symptoms: {base_context['symptoms']}
        
        Return a JSON array of symptoms: ["symptom1", "symptom2", ...]
        """,
        
        "diagnosis": f"""
        Based on the following patient information, provide a medical diagnosis:
        Name: {base_context['patient_name']}
        Age: {base_context['patient_age']}
        Gender: {base_context['patient_gender']}
        Symptoms: {base_context['symptoms']}
        Chat History: {base_context['chat_history']}
        
        Return a JSON object with diagnosis information.
        """,
        
        "followup": f"""
        Generate follow-up questions for this patient:
        Name: {base_context['patient_name']}
        Age: {base_context['patient_age']}
        Gender: {base_context['patient_gender']}
        Symptoms: {base_context['symptoms']}
        Chat History: {base_context['chat_history']}
        
        Return a JSON object with follow-up questions.
        """,
        
        "report": f"""
        Generate a medical report for this patient:
        Name: {base_context['patient_name']}
        Age: {base_context['patient_age']}
        Gender: {base_context['patient_gender']}
        Symptoms: {base_context['symptoms']}
        Chat History: {base_context['chat_history']}
        
        Return a JSON object with the medical report.
        """
    }
    
    return prompts.get(prompt_type, "")


def handle_ai_error(error: Exception, component: str) -> AIProcessingError:
    """
    Handle AI processing errors with proper logging and error creation.
    
    Args:
        error: Original error
        component: Component where error occurred
        
    Returns:
        AIProcessingError object
    """
    logger.error(f"AI processing error in {component}: {error}", exc_info=True)
    
    # Map common errors to user-friendly messages
    error_messages = {
        "timeout": "AI processing timed out. Please try again.",
        "rate_limit": "AI service is temporarily unavailable. Please try again later.",
        "invalid_key": "AI service configuration error. Please contact support.",
        "network": "Network error occurred. Please check your connection and try again."
    }
    
    error_str = str(error).lower()
    for key, message in error_messages.items():
        if key in error_str:
            return AIProcessingError(message, component)
    
    return AIProcessingError(f"AI processing failed: {str(error)}", component)


async def run_in_thread_pool(func, *args, **kwargs):
    """
    Run a blocking function in a thread pool.
    
    Args:
        func: Function to run
        *args: Function arguments
        **kwargs: Function keyword arguments
        
    Returns:
        Function result
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args, **kwargs)
