"""
Pydantic models for VADG API request/response validation.
Ensures type safety and proper data validation across the application.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Dict, Union, Optional, Any
from datetime import datetime
from enum import Enum


class GenderEnum(str, Enum):
    """Valid gender options for patient data."""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class UrgencyLevel(str, Enum):
    """Medical urgency levels for diagnosis reports."""
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"
    CRITICAL = "Critical"


class DiagnosisRequest(BaseModel):
    """Request model for symptom submission and diagnosis initiation."""
    name: Optional[str] = Field(None, description="Patient name", max_length=100)
    age: Optional[Union[int, str]] = Field(None, description="Patient age", ge=0, le=150)
    gender: Optional[GenderEnum] = Field(None, description="Patient gender")
    symptoms: Optional[Union[List[str], str]] = Field(None, description="Patient symptoms")
    patient_id: Optional[str] = Field(None, description="Optional patient ID", max_length=50)
    notes: Optional[str] = Field(None, description="Additional notes", max_length=1000)

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
                raise ValueError("Age must be a valid number")
        if isinstance(v, (int, float)):
            return int(v)
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

    def symptoms_as_text(self) -> str:
        """Convert symptoms list to text format for legacy functions."""
        if not self.symptoms:
            return ""
        if isinstance(self.symptoms, list):
            return "\n".join(self.symptoms)
        return str(self.symptoms)


class SessionData(BaseModel):
    """Model for session data storage."""
    name: str = Field(..., description="Patient name")
    age: Optional[int] = Field(None, description="Patient age")
    gender: str = Field(..., description="Patient gender")
    symptoms: List[str] = Field(default_factory=list, description="Patient symptoms")
    chat_history: List[Dict[str, Any]] = Field(default_factory=list, description="Chat history")
    question_count: int = Field(default=0, description="Number of questions asked")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Session creation time")
    last_activity: datetime = Field(default_factory=datetime.utcnow, description="Last activity time")


class DiagnosisResponse(BaseModel):
    """Response model for diagnosis submission."""
    message: str = Field(..., description="Response message")
    status: str = Field(..., description="Response status")
    session_id: str = Field(..., description="Generated session ID")


class FollowUpQuestion(BaseModel):
    """Model for follow-up questions."""
    question: str = Field(..., description="Question text")
    options: List[Dict[str, str]] = Field(..., description="Answer options")
    status: str = Field(..., description="Question status")


class MedicalReport(BaseModel):
    """Model for medical report structure."""
    patient_info: Dict[str, Any] = Field(..., description="Patient information")
    recommendation: str = Field(..., description="Medical recommendation")
    urgency: UrgencyLevel = Field(..., description="Urgency level")
    reason_for_consultation: str = Field(..., description="Reason for consultation")
    symptoms_analysis: str = Field(..., description="Symptoms analysis")
    possible_conditions: List[Dict[str, Any]] = Field(..., description="Possible conditions")
    recommended_tests: List[str] = Field(default_factory=list, description="Recommended tests")
    follow_up_instructions: str = Field(..., description="Follow-up instructions")
    disclaimer: str = Field(..., description="Medical disclaimer")


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
    status_code: int = Field(..., description="HTTP status code")


class HealthCheckResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
    version: str = Field(..., description="API version")
    dependencies: Dict[str, str] = Field(..., description="Dependency status")


class ContactSubmissionCreate(BaseModel):
    """Request model for contact form submission."""
    name: str = Field(..., description="Contact person's name", max_length=100)
    email: str = Field(..., description="Contact email address")
    message: str = Field(..., description="Contact message", max_length=2000)
    phone: Optional[str] = Field(None, description="Optional phone number", max_length=20)

    @validator("name")
    def validate_name(cls, v):
        """Validate and clean name field."""
        if not v or not v.strip():
            raise ValueError("Name is required")
        return v.strip()

    @validator("email")
    def validate_email(cls, v):
        """Validate email format."""
        if not v or not v.strip():
            raise ValueError("Email is required")
        return v.strip().lower()

    @validator("message")
    def validate_message(cls, v):
        """Validate message content."""
        if not v or not v.strip():
            raise ValueError("Message is required")
        if len(v.strip()) > 2000:
            raise ValueError("Message must be 2000 characters or less")
        return v.strip()

    @validator("phone")
    def validate_phone(cls, v):
        """Validate phone number format if provided."""
        if v and v.strip():
            # Basic phone validation - allow digits, spaces, hyphens, parentheses, plus
            import re
            if not re.match(r'^[\d\s\-()+]+$', v.strip()):
                raise ValueError("Invalid phone number format")
            return v.strip()
        return None


class ContactSubmission(ContactSubmissionCreate):
    """Complete contact submission model with metadata."""
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Submission timestamp")
    ip_address: Optional[str] = Field(None, description="Submitter's IP address")
    user_agent: Optional[str] = Field(None, description="User agent string")
    email_sent: bool = Field(default=False, description="Whether notification email was sent")