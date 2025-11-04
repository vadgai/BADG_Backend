"""
Admin Analytics Models for VADG
MongoDB models for admin analytics with TTL indexes
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class VisitType(str, Enum):
    """Visit type enum for hybrid tracking."""
    PAGE_HIT = "page_hit"
    COMPLETED_DIAGNOSIS = "completed_diagnosis"


class Visit(BaseModel):
    """Visit model for page hits and completed diagnoses."""
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Visit timestamp")
    ipAddress: Optional[str] = Field(None, description="Visitor IP address")
    page: Optional[str] = Field(None, description="Page visited")
    referrer: Optional[str] = Field(None, description="Referrer URL")
    userAgent: Optional[str] = Field(None, description="User agent string")
    sessionId: Optional[str] = Field(None, description="Session identifier")
    isReturningUser: bool = Field(default=False, description="Whether user has visited before")
    type: VisitType = Field(..., description="Type of visit (page_hit or completed_diagnosis)")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PartialReport(BaseModel):
    """Partial report model for last-stage drop-offs."""
    createdAt: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    sessionId: str = Field(..., description="Session identifier")
    formSnapshot: Dict[str, Any] = Field(..., description="Last-step form data snapshot")
    progress: Dict[str, Any] = Field(..., description="Progress information")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AdminLoginRequest(BaseModel):
    """Admin login request model."""
    email: str = Field(..., description="Admin email")
    password: str = Field(..., description="Admin password")


class AdminToken(BaseModel):
    """Admin token response model."""
    token: str = Field(..., description="JWT token")
    token_type: str = Field(default="bearer", description="Token type")


class AnalyticsSummary(BaseModel):
    """Analytics summary for dashboard cards."""
    dau: int = Field(..., description="Daily Active Users (last 24h)")
    wau: int = Field(..., description="Weekly Active Users (last 7 days)")
    mau: int = Field(..., description="Monthly Active Users (last 30 days)")
    totalVisits: int = Field(..., description="Total visits in last 30 days")
    completedDiagnoses: int = Field(..., description="Completed diagnoses in last 30 days")
    completionRate: float = Field(..., description="Completion rate percentage")
    newUsers: int = Field(..., description="New users in last 30 days")
    returningUsers: int = Field(..., description="Returning users in last 30 days")


class VisitorAnalytics(BaseModel):
    """Visitor analytics data."""
    visitsPerDay: List[Dict[str, Any]] = Field(default_factory=list, description="Visits per day for last 30 days")
    topPages: List[Dict[str, Any]] = Field(default_factory=list, description="Top visited pages")
    referrers: List[Dict[str, Any]] = Field(default_factory=list, description="Top referrers")
    devices: List[Dict[str, Any]] = Field(default_factory=list, description="Device/browser breakdown")
    uniqueVisitors: int = Field(..., description="Unique visitors count")
    newUsers: int = Field(..., description="New users count")
    returningUsers: int = Field(..., description="Returning users count")


class FunnelAnalytics(BaseModel):
    """Funnel analytics data."""
    pageHits: int = Field(..., description="Total page hits on diagnosis pages")
    started: int = Field(..., description="Users who started diagnosis")
    lastStagePartials: int = Field(..., description="Users who reached last stage but didn't complete")
    completed: int = Field(..., description="Completed diagnoses")
    conversion: float = Field(..., description="Conversion rate")


class DiseaseAnalytics(BaseModel):
    """Disease analytics data."""
    topDiseases: List[Dict[str, Any]] = Field(default_factory=list, description="Top diseases in last 30 days")
    trend: List[Dict[str, Any]] = Field(default_factory=list, description="Disease trend over last 30 days")


class LanguageAnalytics(BaseModel):
    """Language usage analytics."""
    byLanguage: List[Dict[str, Any]] = Field(default_factory=list, description="Language usage breakdown")
