"""
Analytics Database Models
TypeScript-like interfaces for analytics data structures
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum


class EventType(str, Enum):
    """Core event types for analytics tracking"""
    VISIT_HOME = "visit_home"
    START_SYMPTOM_ENTRY = "start_symptom_entry"
    SYMPTOM_ENTRY_COMPLETED = "symptom_entry_completed"
    MODEL_REQUEST_SENT = "model_request_sent"
    MODEL_REQUEST_COMPLETED = "model_request_completed"
    FOLLOW_UP_STARTED = "follow_up_started"
    FOLLOW_UP_COMPLETED = "follow_up_completed"
    DIAGNOSIS_COMPLETED = "diagnosis_completed"
    PDF_GENERATED = "pdf_generated"
    SESSION_CLOSED = "session_closed"


class DeviceType(str, Enum):
    """Device type classification"""
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"
    UNKNOWN = "unknown"


class SessionDocument(BaseModel):
    """Session document schema"""
    session_id: str = Field(..., description="Unique session UUID")
    visitor_id: str = Field(..., description="Hashed visitor identifier")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Session start timestamp")
    ended_at: Optional[datetime] = Field(None, description="Session end timestamp")
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow, description="Last heartbeat timestamp")
    is_active: bool = Field(True, description="Whether session is currently active")
    ip_hash: str = Field(..., description="Hashed IP address")
    user_agent: str = Field(..., description="User agent string")
    device_type: DeviceType = Field(..., description="Device type")
    browser: Optional[str] = Field(None, description="Browser name")
    browser_version: Optional[str] = Field(None, description="Browser version")
    os: Optional[str] = Field(None, description="Operating system")
    os_version: Optional[str] = Field(None, description="OS version")
    country: Optional[str] = Field(None, description="Country code")
    city: Optional[str] = Field(None, description="City name")
    user_id: Optional[str] = Field(None, description="User ID if authenticated")
    referrer: Optional[str] = Field(None, description="Referrer URL")
    landing_page: str = Field(..., description="First page visited in session")
    page_count: int = Field(0, description="Number of pages visited")
    event_count: int = Field(0, description="Number of events in session")
    duration_seconds: Optional[int] = Field(None, description="Session duration in seconds")


class VisitDocument(BaseModel):
    """Visit document schema"""
    visit_id: str = Field(..., description="Unique visit ID")
    session_id: str = Field(..., description="Session ID")
    visitor_id: str = Field(..., description="Hashed visitor identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Visit timestamp")
    page: str = Field(..., description="Page path")
    page_title: Optional[str] = Field(None, description="Page title")
    referrer: Optional[str] = Field(None, description="Referrer URL")
    referrer_domain: Optional[str] = Field(None, description="Referrer domain")
    ip_hash: str = Field(..., description="Hashed IP address")
    user_agent: str = Field(..., description="User agent string")
    device_type: DeviceType = Field(..., description="Device type")
    browser: Optional[str] = Field(None, description="Browser name")
    os: Optional[str] = Field(None, description="Operating system")
    country: Optional[str] = Field(None, description="Country code")
    city: Optional[str] = Field(None, description="City name")
    is_unique_visitor: bool = Field(False, description="Is unique visitor (24h window)")
    is_bot: bool = Field(False, description="Is bot traffic")


class EventDocument(BaseModel):
    """Event document schema"""
    event_id: str = Field(..., description="Unique event ID")
    session_id: str = Field(..., description="Session ID")
    visitor_id: Optional[str] = Field(None, description="Visitor ID")
    user_id: Optional[str] = Field(None, description="User ID if authenticated")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    event_name: EventType = Field(..., description="Event type")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Event metadata")
    page: Optional[str] = Field(None, description="Page where event occurred")
    ip_hash: Optional[str] = Field(None, description="Hashed IP address")


class DeviceStatsDocument(BaseModel):
    """Device statistics aggregation document"""
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    device_type: DeviceType = Field(..., description="Device type")
    browser: Optional[str] = Field(None, description="Browser name")
    os: Optional[str] = Field(None, description="Operating system")
    count: int = Field(0, description="Count of sessions/visits")
    unique_visitors: int = Field(0, description="Unique visitors")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class LocationStatsDocument(BaseModel):
    """Location statistics aggregation document"""
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    country: Optional[str] = Field(None, description="Country code")
    city: Optional[str] = Field(None, description="City name")
    count: int = Field(0, description="Count of sessions/visits")
    unique_visitors: int = Field(0, description="Unique visitors")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


# Request/Response models for API
class EventRequest(BaseModel):
    """Event tracking request model"""
    event_name: EventType
    metadata: Dict[str, Any] = Field(default_factory=dict)
    page: Optional[str] = None
    session_id: Optional[str] = None


class EventResponse(BaseModel):
    """Event tracking response model"""
    success: bool
    event_id: Optional[str] = None
    session_id: Optional[str] = None
    message: Optional[str] = None


# Phase 2: Advanced Technical Analytics Models

class ModelLogDocument(BaseModel):
    """Model performance and latency tracking document"""
    log_id: str = Field(..., description="Unique log ID")
    session_id: Optional[str] = Field(None, description="Session ID")
    model_name: str = Field(..., description="Model name (e.g., gemini-2.5-flash)")
    input_timestamp: datetime = Field(..., description="When model request was sent")
    output_timestamp: Optional[datetime] = Field(None, description="When model response was received")
    total_latency_ms: Optional[float] = Field(None, description="Total latency in milliseconds")
    input_token_count: Optional[int] = Field(None, description="Input token count")
    output_token_count: Optional[int] = Field(None, description="Output token count")
    total_token_count: Optional[int] = Field(None, description="Total token count")
    success: bool = Field(True, description="Whether request succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_type: Optional[str] = Field(None, description="Error type/class")
    endpoint: Optional[str] = Field(None, description="API endpoint that triggered model call")
    prompt_length: Optional[int] = Field(None, description="Prompt character length")
    response_length: Optional[int] = Field(None, description="Response character length")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class AccuracyLogDocument(BaseModel):
    """Model accuracy tracking document"""
    accuracy_id: str = Field(..., description="Unique accuracy log ID")
    session_id: Optional[str] = Field(None, description="Session ID")
    model_log_id: Optional[str] = Field(None, description="Reference to model log")
    predicted_disease: str = Field(..., description="Disease predicted by model")
    confirmed_disease: Optional[str] = Field(None, description="Disease confirmed by user/doctor")
    confidence_score: Optional[float] = Field(None, description="Model confidence score (0-1)")
    is_correct: Optional[bool] = Field(None, description="Whether prediction was correct")
    accuracy_bucket: Optional[str] = Field(None, description="Accuracy bucket (exact_match, partial_match, incorrect)")
    confirmed_at: Optional[datetime] = Field(None, description="When disease was confirmed")
    confirmed_by: Optional[str] = Field(None, description="Who confirmed (user, doctor, etc.)")
    notes: Optional[str] = Field(None, description="Additional notes")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Log timestamp")


class ErrorLogDocument(BaseModel):
    """Error logging document"""
    error_id: str = Field(..., description="Unique error ID")
    session_id: Optional[str] = Field(None, description="Session ID")
    error_type: str = Field(..., description="Error type (exception class name)")
    error_message: str = Field(..., description="Error message")
    stack_trace: Optional[str] = Field(None, description="Full stack trace")
    endpoint: Optional[str] = Field(None, description="API endpoint where error occurred")
    method: Optional[str] = Field(None, description="HTTP method")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    payload_snapshot: Optional[Dict[str, Any]] = Field(None, description="Sanitized payload snapshot")
    user_agent: Optional[str] = Field(None, description="User agent")
    ip_hash: Optional[str] = Field(None, description="Hashed IP address")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    severity: str = Field("error", description="Error severity (error, warning, critical)")
    resolved: bool = Field(False, description="Whether error has been resolved")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ApiFailureDocument(BaseModel):
    """API failure tracking document"""
    failure_id: str = Field(..., description="Unique failure ID")
    session_id: Optional[str] = Field(None, description="Session ID")
    endpoint: str = Field(..., description="API endpoint")
    method: str = Field(..., description="HTTP method")
    status_code: int = Field(..., description="HTTP status code")
    error_type: str = Field(..., description="Error type")
    error_message: str = Field(..., description="Error message")
    timeout: bool = Field(False, description="Whether failure was due to timeout")
    retry_count: int = Field(0, description="Number of retries attempted")
    payload_snapshot: Optional[Dict[str, Any]] = Field(None, description="Sanitized payload")
    response_body: Optional[str] = Field(None, description="Response body (truncated)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Failure timestamp")
    duration_ms: Optional[float] = Field(None, description="Request duration in milliseconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class PdfLogDocument(BaseModel):
    """PDF generation logging document"""
    pdf_log_id: str = Field(..., description="Unique PDF log ID")
    session_id: Optional[str] = Field(None, description="Session ID")
    render_start: datetime = Field(..., description="PDF render start timestamp")
    render_end: Optional[datetime] = Field(None, description="PDF render end timestamp")
    render_time_ms: Optional[float] = Field(None, description="Render time in milliseconds")
    success: bool = Field(False, description="Whether PDF generation succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_type: Optional[str] = Field(None, description="Error type")
    pdf_size_bytes: Optional[int] = Field(None, description="Generated PDF size in bytes")
    language: Optional[str] = Field(None, description="PDF language")
    page_count: Optional[int] = Field(None, description="Number of pages in PDF")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class WebSocketFailureDocument(BaseModel):
    """WebSocket failure logging document"""
    ws_failure_id: str = Field(..., description="Unique WebSocket failure ID")
    session_id: Optional[str] = Field(None, description="Session ID")
    failure_type: str = Field(..., description="Failure type (disconnect, error, timeout)")
    error_code: Optional[int] = Field(None, description="WebSocket error code")
    error_message: Optional[str] = Field(None, description="Error message")
    close_code: Optional[int] = Field(None, description="WebSocket close code")
    close_reason: Optional[str] = Field(None, description="Close reason")
    duration_seconds: Optional[float] = Field(None, description="Connection duration before failure")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Failure timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# Phase 3: Deep Insights Models

class FunnelStepDocument(BaseModel):
    """Funnel step tracking document"""
    step_id: str = Field(..., description="Unique step ID")
    session_id: str = Field(..., description="Session ID")
    step_name: str = Field(..., description="Step name (form_start, form_complete, followup_start, followup_complete, report_generated, pdf_generated)")
    step_number: int = Field(..., description="Step number in funnel (1, 2, 3, etc.)")
    entered_at: datetime = Field(..., description="When user entered this step")
    completed_at: Optional[datetime] = Field(None, description="When user completed this step")
    time_spent_seconds: Optional[float] = Field(None, description="Time spent in this step")
    dropped_off: bool = Field(False, description="Whether user dropped off at this step")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class DiseaseUsageDocument(BaseModel):
    """Disease usage statistics document"""
    disease_name: str = Field(..., description="Disease name")
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    prediction_count: int = Field(0, description="Number of predictions")
    confirmation_count: int = Field(0, description="Number of confirmations")
    accuracy_rate: Optional[float] = Field(None, description="Accuracy rate (0-1)")
    avg_confidence: Optional[float] = Field(None, description="Average confidence score")
    outcome_distribution: Dict[str, int] = Field(default_factory=dict, description="Outcome distribution (exact_match, partial_match, incorrect)")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class LocationAnalyticsDocument(BaseModel):
    """Location analytics document"""
    location_id: str = Field(..., description="Unique location ID")
    country: Optional[str] = Field(None, description="Country code")
    country_name: Optional[str] = Field(None, description="Country name")
    state: Optional[str] = Field(None, description="State/Province")
    city: Optional[str] = Field(None, description="City name")
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    session_count: int = Field(0, description="Number of sessions")
    unique_visitors: int = Field(0, description="Unique visitors")
    diagnosis_count: int = Field(0, description="Number of diagnoses")
    drop_off_rate: Optional[float] = Field(None, description="Drop-off rate (0-1)")
    avg_session_duration: Optional[float] = Field(None, description="Average session duration in seconds")
    top_diseases: List[Dict[str, Any]] = Field(default_factory=list, description="Top diseases in this location")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class DeviceAnalyticsDocument(BaseModel):
    """Device analytics document"""
    device_id: str = Field(..., description="Unique device analytics ID")
    device_type: DeviceType = Field(..., description="Device type")
    browser: Optional[str] = Field(None, description="Browser name")
    browser_version: Optional[str] = Field(None, description="Browser version")
    os: Optional[str] = Field(None, description="Operating system")
    os_version: Optional[str] = Field(None, description="OS version")
    screen_size: Optional[str] = Field(None, description="Screen size category")
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    session_count: int = Field(0, description="Number of sessions")
    unique_visitors: int = Field(0, description="Unique visitors")
    avg_load_time: Optional[float] = Field(None, description="Average page load time in ms")
    js_error_count: int = Field(0, description="Number of JavaScript errors")
    conversion_rate: Optional[float] = Field(None, description="Conversion rate (0-1)")
    avg_session_duration: Optional[float] = Field(None, description="Average session duration in seconds")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

