"""
User & Authentication Models for VADG
Pydantic schemas for registration, login, password management, profile,
and role-based access control. Backed by the `auth_users` MongoDB collection.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class UserRole(str, Enum):
    """Supported user roles for role-based access control."""
    USER = "user"
    ADMIN = "admin"


# ---------------------------------------------------------------------------
# Shared password validation
# ---------------------------------------------------------------------------
# Password policy: >= 8 chars, at least one lowercase, one uppercase, one digit.
_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,128}$")


def validate_password_strength(password: str) -> str:
    """Raise ValueError if the password does not meet the strength policy."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if len(password) > 128:
        raise ValueError("Password must be at most 128 characters long")
    if not _PASSWORD_RE.match(password):
        raise ValueError(
            "Password must contain at least one uppercase letter, one lowercase "
            "letter, and one number"
        )
    return password


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    """Payload for creating a new user account."""
    name: str = Field(..., min_length=2, max_length=80, description="Full name")
    email: EmailStr = Field(..., description="Account email address")
    password: str = Field(..., description="Account password")

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = " ".join(str(v).split())
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters long")
        return v

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class LoginRequest(BaseModel):
    """Payload for authenticating a user."""
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Payload for exchanging a refresh token for a new access token."""
    refresh_token: str = Field(..., min_length=10)


class LogoutRequest(BaseModel):
    """Optional payload for logout (revokes a specific refresh token)."""
    refresh_token: Optional[str] = Field(None, description="Refresh token to revoke")
    all_devices: bool = Field(default=False, description="Revoke all sessions")


class VerifyEmailRequest(BaseModel):
    """Payload for confirming an email verification token."""
    token: str = Field(..., min_length=10)


class ResendVerificationRequest(BaseModel):
    """Payload for requesting a fresh verification email."""
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    """Payload for initiating a password reset."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Payload for completing a password reset with a token."""
    token: str = Field(..., min_length=10)
    password: str = Field(..., description="New password")

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class ChangePasswordRequest(BaseModel):
    """Payload for an authenticated user changing their own password."""
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., description="New password")

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UpdateProfileRequest(BaseModel):
    """Payload for updating the authenticated user's profile."""
    name: Optional[str] = Field(None, min_length=2, max_length=80)
    phone: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = Field(None, max_length=500)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = " ".join(str(v).split())
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters long")
        return v

    @field_validator("phone")
    @classmethod
    def _clean_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not re.match(r"^[0-9+\-\s()]{6,20}$", v):
            raise ValueError("Invalid phone number format")
        return v


# ---------------------------------------------------------------------------
# Admin user-management models
# ---------------------------------------------------------------------------
class AdminUpdateRoleRequest(BaseModel):
    """Admin action: change a user's role."""
    role: UserRole


class AdminUpdateStatusRequest(BaseModel):
    """Admin action: activate or deactivate a user."""
    is_active: bool


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class UserPublic(BaseModel):
    """Safe, public-facing representation of a user (never exposes secrets)."""
    id: str
    name: str
    email: EmailStr
    role: UserRole = UserRole.USER
    is_active: bool = True
    is_verified: bool = False
    is_permanent_admin: bool = False
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    @staticmethod
    def from_document(doc: Dict[str, Any]) -> "UserPublic":
        """Build a UserPublic from a raw MongoDB document."""
        return UserPublic(
            id=str(doc.get("_id")),
            name=doc.get("name", ""),
            email=doc.get("email", ""),
            role=doc.get("role", UserRole.USER),
            is_active=doc.get("is_active", True),
            is_verified=doc.get("is_verified", False),
            is_permanent_admin=doc.get("is_permanent_admin", False),
            phone=doc.get("phone"),
            avatar_url=doc.get("avatar_url"),
            created_at=doc.get("created_at"),
            last_login=doc.get("last_login"),
        )


class TokenResponse(BaseModel):
    """Access + refresh token pair returned on login/refresh."""
    success: bool = True
    token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Opaque refresh token")
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    user: UserPublic


class MessageResponse(BaseModel):
    """Generic success message."""
    success: bool = True
    message: str


class UserListResponse(BaseModel):
    """Paginated list of users for the admin dashboard."""
    success: bool = True
    total: int
    page: int
    limit: int
    users: List[UserPublic]
