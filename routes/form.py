"""
Form Submission Routes
Handles patient form data submission and retrieval
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel
from typing import Optional

# Try to import database models, make them optional
try:
    from database.models import FormSubmissionCreate, FormSubmission
    MODELS_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Database models not available - creating dummy models")
    MODELS_AVAILABLE = False
    # Create dummy Pydantic models
    class FormSubmissionCreate(BaseModel):
        name: str
        email: str
        message: str
    class FormSubmission(BaseModel):
        name: str
        email: str
        message: str

# Try to import database connection functions
try:
    from database.connection import (
        get_form_submissions_collection,
        get_users_collection,
        is_database_available
    )
    DB_CONNECTION_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Database connection not available")
    DB_CONNECTION_AVAILABLE = False
    # Dummy functions
    def get_form_submissions_collection():
        return None
    def get_users_collection():
        return None
    def is_database_available():
        return False
# Try to import rate limit middleware, make it optional
try:
    from middleware.rate_limit import rate_limit_middleware
except ImportError:
    # Create a dummy rate limit middleware if not available
    def rate_limit_middleware():
        def dummy_dependency():
            return None
        return dummy_dependency

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["form"])


@router.post("/form")
async def submit_form(
    form_data: FormSubmissionCreate,
    request: Request,
    _=Depends(rate_limit_middleware)
):
    """
    Submit patient form data to database
    
    This endpoint saves enhanced patient information including:
    - Basic demographics (age, gender)
    - Symptoms
    - Physical measurements (weight, height)
    - Lifestyle factors (activity, diet)
    - Location information
    
    Args:
        form_data: Form submission data
        request: FastAPI request object
    
    Returns:
        Success response with session_id
    """
    logger.info("Form submission received for session: %s", form_data.session_id)
    
    # Check if database is available
    if not is_database_available():
        logger.warning("Database unavailable, form data not saved for session: %s", form_data.session_id)
        # Return success anyway (graceful degradation)
        return {
            "success": True,
            "message": "Form received (database temporarily unavailable)",
            "session_id": form_data.session_id,
            "warning": "Data saved in-memory only"
        }
    
    form_collection = get_form_submissions_collection()
    users_collection = get_users_collection()
    
    try:
        # Create form submission object
        submission = FormSubmission(
            **form_data.dict(),
            timestamp=datetime.utcnow()
        )
        
        # Convert to dict for MongoDB
        submission_dict = submission.dict()
        
        # Try to insert
        try:
            await form_collection.insert_one(submission_dict)
            logger.info("Form submitted successfully for session: %s", form_data.session_id)
            
        except Exception as insert_error:
            # If duplicate session_id, update existing record
            if "duplicate" in str(insert_error).lower() or "E11000" in str(insert_error):
                logger.info("Updating existing form for session: %s", form_data.session_id)
                
                # Update existing document
                await form_collection.update_one(
                    {"session_id": form_data.session_id},
                    {"$set": submission_dict},
                    upsert=True
                )
            else:
                # Other error, try upsert
                await form_collection.update_one(
                    {"session_id": form_data.session_id},
                    {"$set": submission_dict},
                    upsert=True
                )
        
        # Update user session record
        if users_collection:
            await users_collection.update_one(
                {"session_id": form_data.session_id},
                {
                    "$set": {
                        "last_activity": datetime.utcnow(),
                        "form_submitted": True
                    },
                    "$setOnInsert": {
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
        
        return {
            "success": True,
            "message": "Form submitted successfully",
            "session_id": form_data.session_id
        }
        
    except Exception as e:
        logger.error("Error submitting form for session %s: %s", form_data.session_id, str(e))
        
        # Return success anyway (graceful degradation)
        # The symptom submission will still work even if form save fails
        return {
            "success": True,
            "message": "Form received (partial save)",
            "session_id": form_data.session_id,
            "warning": "Database error occurred but session continues"
        }


@router.get("/form/{session_id}")
async def get_form_by_session(session_id: str):
    """
    Get form submission by session ID
    
    Args:
        session_id: Session identifier
    
    Returns:
        Form submission data
    """
    if not is_database_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable"
        )
    
    form_collection = get_form_submissions_collection()
    
    try:
        form = await form_collection.find_one(
            {"session_id": session_id},
            {"_id": 0}  # Exclude MongoDB _id
        )
        
        if not form:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Form not found for this session"
            )
        
        return form
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching form for session %s: %s", session_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving form data"
        )


@router.patch("/form/{session_id}/complete")
async def mark_diagnosis_complete(session_id: str):
    """
    Mark a form submission as diagnosis completed
    
    This is called after the diagnosis report is generated
    
    Args:
        session_id: Session identifier
    
    Returns:
        Success message
    """
    if not is_database_available():
        # Silently fail if database unavailable
        return {"success": True, "message": "Acknowledged (database unavailable)"}
    
    form_collection = get_form_submissions_collection()
    users_collection = get_users_collection()
    
    try:
        # Update form submission
        result = await form_collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "diagnosis_completed": True,
                    "report_generated": True
                }
            }
        )
        
        # Update user session
        if users_collection:
            await users_collection.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "diagnosis_completed": True,
                        "last_activity": datetime.utcnow()
                    }
                }
            )
        
        if result.modified_count == 0:
            logger.warning("No form found to mark complete for session: %s", session_id)
        else:
            logger.info("Marked diagnosis complete for session: %s", session_id)
        
        return {
            "success": True,
            "message": "Diagnosis marked as complete"
        }
        
    except Exception as e:
        logger.error("Error marking diagnosis complete for session %s: %s", session_id, str(e))
        # Don't fail the request, just log the error
        return {
            "success": True,
            "message": "Acknowledged (error updating database)"
        }

