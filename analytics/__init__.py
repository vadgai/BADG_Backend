"""
Analytics Module
Core analytics tracking functionality
"""

from .models import (
    EventType,
    DeviceType,
    SessionDocument,
    VisitDocument,
    EventDocument,
    DeviceStatsDocument,
    LocationStatsDocument,
    EventRequest,
    EventResponse,
    # Phase 2 models
    ModelLogDocument,
    AccuracyLogDocument,
    ErrorLogDocument,
    ApiFailureDocument,
    PdfLogDocument,
    WebSocketFailureDocument,
)
from .device_detection import (
    detect_device_type,
    detect_browser,
    detect_os,
    parse_user_agent
)
from .ip_utils import (
    hash_ip,
    anonymize_ip,
    get_client_ip
)
from .bot_filter import (
    is_bot,
    is_crawler,
    should_filter_request
)
from .visitor_dedup import (
    generate_visitor_id,
    is_unique_visitor_24h,
    get_or_create_visitor_id
)
from .session_tracker import (
    create_session,
    get_session,
    update_session_heartbeat,
    increment_session_page_count,
    increment_session_event_count,
    end_session,
    cleanup_inactive_sessions
)
from .event_logger import (
    log_event,
    store_event,
    get_events_by_session
)
# Phase 2: Advanced Analytics
from .model_logger import (
    log_model_call_async,
    store_model_log,
    extract_token_count
)
from .accuracy_logger import (
    log_accuracy,
    store_accuracy_log,
    calculate_accuracy_bucket
)
from .error_logger import (
    log_error,
    log_api_failure,
    store_error_log,
    store_api_failure,
    sanitize_payload
)
from .pdf_logger import (
    log_pdf_generation,
    store_pdf_log
)
from .websocket_logger import (
    log_websocket_failure,
    store_websocket_failure
)
from .model_wrapper import (
    LoggedModelWrapper,
    get_logged_model,
    generate_content_with_logging
)
from .error_middleware import ErrorLoggingMiddleware
# Phase 3: Deep Insights
from .funnel_tracker import (
    track_funnel_step,
    calculate_funnel_metrics,
    FunnelStep,
    STEP_NUMBERS
)
from .disease_aggregator import (
    aggregate_disease_usage,
    get_disease_trends,
    get_top_diseases
)
from .location_analytics import (
    aggregate_location_stats,
    get_location_stats,
    get_top_diseases_for_location
)
from .device_analytics import (
    aggregate_device_stats,
    get_device_stats
)

__all__ = [
    # Models
    "EventType",
    "DeviceType",
    "SessionDocument",
    "VisitDocument",
    "EventDocument",
    "DeviceStatsDocument",
    "LocationStatsDocument",
    "EventRequest",
    "EventResponse",
    # Device detection
    "detect_device_type",
    "detect_browser",
    "detect_os",
    "parse_user_agent",
    # IP utilities
    "hash_ip",
    "anonymize_ip",
    "get_client_ip",
    # Bot filtering
    "is_bot",
    "is_crawler",
    "should_filter_request",
    # Visitor deduplication
    "generate_visitor_id",
    "is_unique_visitor_24h",
    "get_or_create_visitor_id",
    # Session tracking
    "create_session",
    "get_session",
    "update_session_heartbeat",
    "increment_session_page_count",
    "increment_session_event_count",
    "end_session",
    "cleanup_inactive_sessions",
    # Event logging
    "log_event",
    "store_event",
    "get_events_by_session",
    # Phase 2: Advanced Analytics Models
    "ModelLogDocument",
    "AccuracyLogDocument",
    "ErrorLogDocument",
    "ApiFailureDocument",
    "PdfLogDocument",
    "WebSocketFailureDocument",
    # Model logging
    "log_model_call_async",
    "store_model_log",
    "extract_token_count",
    # Accuracy tracking
    "log_accuracy",
    "store_accuracy_log",
    "calculate_accuracy_bucket",
    # Error logging
    "log_error",
    "log_api_failure",
    "store_error_log",
    "store_api_failure",
    "sanitize_payload",
    # PDF logging
    "log_pdf_generation",
    "store_pdf_log",
    # WebSocket logging
    "log_websocket_failure",
    "store_websocket_failure",
    # Model wrapper
    "LoggedModelWrapper",
    "get_logged_model",
    "generate_content_with_logging",
    # Middleware
    "ErrorLoggingMiddleware",
    # Phase 3: Deep Insights Models
    "FunnelStepDocument",
    "DiseaseUsageDocument",
    "LocationAnalyticsDocument",
    "DeviceAnalyticsDocument",
    # Funnel tracking
    "track_funnel_step",
    "calculate_funnel_metrics",
    "FunnelStep",
    "STEP_NUMBERS",
    # Disease aggregation
    "aggregate_disease_usage",
    "get_disease_trends",
    "get_top_diseases",
    # Location analytics
    "aggregate_location_stats",
    "get_location_stats",
    "get_top_diseases_for_location",
    # Device analytics
    "aggregate_device_stats",
    "get_device_stats",
]

