"""
User authentication & management routes for VADG.

Mounted at /api/auth. Covers registration, email verification, login, token
refresh, logout, profile management, password change/forgot/reset, plus
admin-only user management. Backed by the auth_users collection.
"""

import logging
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from models.user_models import (
    AdminUpdateRoleRequest,
    AdminUpdateStatusRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserListResponse,
    UserPublic,
    VerifyEmailRequest,
)
from auth import email_service, user_service
from auth.dependencies import get_current_user, require_admin
from database.connection import is_database_available
from auth.password import hash_password, verify_password
from auth.tokens import (
    access_token_ttl_seconds,
    create_access_token,
    create_action_token,
    decode_action_token,
    generate_refresh_token,
    is_configured as jwt_configured,
    refresh_token_expiry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])

# Whether an unverified user may log in. Defaults to True (verification required).
REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "true").lower() in (
    "true", "1", "yes", "on",
)

# Persistence must be real in production. Without a database, accounts live only
# in process memory and vanish before the verification link is clicked (which is
# exactly the "Invalid verification link" symptom), so registration is refused.
_IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() in ("production", "prod")

# Permanent admin — cannot be demoted, deactivated, or deleted.
PERMANENT_ADMIN_EMAIL = os.getenv("PERMANENT_ADMIN_EMAIL", "m87.krishna@gmail.com").strip().lower()


# ---------------------------------------------------------------------------
# Lightweight in-memory rate limiter (per-IP, per-action).
# For multi-instance deployments move this to Redis; this bounds abuse per pod.
# ---------------------------------------------------------------------------
_rate_buckets: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)

_RATE_RULES = {
    "login": (10, 300),               # 10 attempts / 5 min
    "register": (5, 3600),            # 5 / hour
    "forgot": (5, 3600),             # 5 / hour
    "resend": (5, 3600),             # 5 / hour
    "reset": (10, 3600),             # 10 / hour
}


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit(action: str, request: Request) -> None:
    limit, window = _RATE_RULES.get(action, (30, 60))
    key = (action, _client_ip(request))
    now = time.time()
    bucket = _rate_buckets[key]
    while bucket and bucket[0] <= now - window:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )
    bucket.append(now)


def _ensure_configured() -> None:
    if not jwt_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on the server",
        )


async def _issue_tokens(user: dict, request: Request) -> TokenResponse:
    """Create access + refresh tokens and persist the session."""
    access = create_access_token(user)
    refresh = generate_refresh_token()
    await user_service.add_session(
        str(user["_id"]),
        refresh,
        refresh_token_expiry(),
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
    )
    return TokenResponse(
        token=access,
        refresh_token=refresh,
        expires_in=access_token_ttl_seconds(),
        user=UserPublic.from_document(user),
    )


# ---------------------------------------------------------------------------
# Registration & verification
# ---------------------------------------------------------------------------
@router.post("/register", response_model=MessageResponse, status_code=201)
async def register(payload: RegisterRequest, request: Request):
    """Create a new account and send a verification email."""
    _ensure_configured()
    _rate_limit("register", request)

    # Refuse to create an account that cannot persist: an in-memory user disappears
    # before verification, producing a permanent "Invalid verification link".
    if not is_database_available():
        logger.critical(
            "Registration blocked: database unavailable (set MONGO_URI to a live "
            "MongoDB). Accounts cannot persist or be verified without it."
        )
        if _IS_PRODUCTION:
            raise HTTPException(
                status_code=503,
                detail="Sign-up is temporarily unavailable. Please try again shortly.",
            )

    if await user_service.email_exists(payload.email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = await user_service.create_user(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="user",
        is_verified=False,
    )

    token = create_action_token(str(user["_id"]), "verify_email")
    try:
        sent = await email_service.send_verification_email(user["email"], user["name"], token)
        if not sent:
            # Delivery was skipped (SMTP not configured) or failed. Registration
            # still succeeds, but flag it so the missing email is diagnosable.
            logger.warning(
                "Verification email NOT delivered to %s (email_configured=%s). "
                "User created but cannot verify until email works.",
                user["email"], email_service.is_configured(),
            )
    except Exception as e:  # email failure must not break registration
        logger.error("Verification email failed for %s: %s", user["email"], e)

    # Notify admin of the new registration (best-effort).
    try:
        await email_service.send_admin_new_user(user["name"], user["email"])
    except Exception as e:
        logger.error("Admin new-user notification failed: %s", e)

    return MessageResponse(
        message="Account created. Please check your email to verify your account."
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(payload: VerifyEmailRequest):
    """Confirm an email verification token."""
    _ensure_configured()
    claims = decode_action_token(payload.token, "verify_email")
    if not claims:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    user = await user_service.get_user_by_id(claims["sub"])
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification link")

    if not user.get("is_verified"):
        await user_service.mark_verified(str(user["_id"]))
        try:
            await email_service.send_welcome_email(user["email"], user.get("name", ""))
        except Exception:
            pass

    return MessageResponse(message="Email verified successfully. You can now sign in.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(payload: ResendVerificationRequest, request: Request):
    """Re-send the verification email. Always returns a generic response."""
    _ensure_configured()
    _rate_limit("resend", request)

    user = await user_service.get_user_by_email(payload.email)
    if user and not user.get("is_verified"):
        token = create_action_token(str(user["_id"]), "verify_email")
        try:
            await email_service.send_verification_email(user["email"], user.get("name", ""), token)
        except Exception as e:
            logger.error("Resend verification failed: %s", e)

    return MessageResponse(
        message="If an unverified account exists for that email, a verification link has been sent."
    )


# ---------------------------------------------------------------------------
# Login / refresh / logout
# ---------------------------------------------------------------------------
@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request):
    """Authenticate and issue an access + refresh token pair."""
    _ensure_configured()
    _rate_limit("login", request)

    user = await user_service.get_user_by_email(payload.email)
    # Uniform error to avoid user enumeration.
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="This account has been deactivated")

    if REQUIRE_EMAIL_VERIFICATION and not user.get("is_verified", False):
        raise HTTPException(
            status_code=403,
            detail={"code": "email_not_verified", "message": "Please verify your email before signing in."},
        )

    await user_service.set_last_login(str(user["_id"]))
    return await _issue_tokens(user, request)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request):
    """Exchange a valid refresh token for a new access + rotated refresh token."""
    _ensure_configured()

    # We don't know the user from an opaque token alone; require the access-token
    # subject via the Authorization header OR look up by scanning is expensive.
    # Instead, the client sends the refresh token; we find the owning session.
    # To keep this O(1) we accept the (optional) current access token to scope
    # the lookup, falling back to a full check is unnecessary because refresh
    # tokens are unique — but we still need the user id. The client therefore
    # includes the user id via the still-decodable (possibly expired) access
    # token is not reliable; so we store refresh->user mapping implicitly by
    # requiring the client to also present it. Simplest robust approach: the
    # refresh token is validated against the user identified by the expired
    # access token's `sub` claim, sent in the Authorization header.
    auth_header = request.headers.get("authorization", "")
    user_id: Optional[str] = None
    if auth_header.lower().startswith("bearer "):
        from auth.tokens import JWT_SECRET_KEY, JWT_ALGORITHM
        import jwt as _jwt
        try:
            # Decode WITHOUT expiry verification just to read the subject.
            claims = _jwt.decode(
                auth_header[7:], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM],
                options={"verify_exp": False},
            )
            user_id = claims.get("sub")
        except Exception:
            user_id = None

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid session")

    if not await user_service.verify_session(user_id, payload.refresh_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    user = await user_service.get_user_by_id(user_id)
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Invalid session")

    # Rotate the refresh token to limit replay.
    new_refresh = generate_refresh_token()
    await user_service.rotate_session(user_id, payload.refresh_token, new_refresh, refresh_token_expiry())

    access = create_access_token(user)
    return TokenResponse(
        token=access,
        refresh_token=new_refresh,
        expires_in=access_token_ttl_seconds(),
        user=UserPublic.from_document(user),
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(payload: LogoutRequest, user: dict = Depends(get_current_user)):
    """Revoke the current refresh token, or all sessions."""
    if payload.all_devices:
        await user_service.revoke_all_sessions(str(user["_id"]))
    elif payload.refresh_token:
        await user_service.revoke_session(str(user["_id"]), payload.refresh_token)
    return MessageResponse(message="Logged out successfully")


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@router.get("/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return UserPublic.from_document(user)


@router.patch("/profile", response_model=UserPublic)
async def update_profile(payload: UpdateProfileRequest, user: dict = Depends(get_current_user)):
    """Update the authenticated user's editable profile fields."""
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if updates:
        await user_service.update_user(str(user["_id"]), updates)
    fresh = await user_service.get_user_by_id(str(user["_id"]))
    return UserPublic.from_document(fresh or user)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(payload: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    """Change password for an authenticated user (requires current password)."""
    if not verify_password(payload.current_password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await user_service.set_password(str(user["_id"]), hash_password(payload.new_password))
    try:
        await email_service.send_password_changed_email(user["email"], user.get("name", ""))
    except Exception:
        pass
    return MessageResponse(message="Password changed successfully. Please sign in again.")


# ---------------------------------------------------------------------------
# Forgot / reset password
# ---------------------------------------------------------------------------
@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest, request: Request):
    """Send a password reset link. Always returns a generic response."""
    _ensure_configured()
    _rate_limit("forgot", request)

    user = await user_service.get_user_by_email(payload.email)
    if user and user.get("is_active", True):
        token = create_action_token(str(user["_id"]), "reset_password")
        claims = decode_action_token(token, "reset_password")
        if claims:
            await user_service.set_reset_jti(str(user["_id"]), claims["jti"])
        try:
            await email_service.send_password_reset_email(user["email"], user.get("name", ""), token)
        except Exception as e:
            logger.error("Password reset email failed: %s", e)

    return MessageResponse(
        message="If an account exists for that email, a password reset link has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, request: Request):
    """Complete a password reset using a single-use token."""
    _ensure_configured()
    _rate_limit("reset", request)

    claims = decode_action_token(payload.token, "reset_password")
    if not claims:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user = await user_service.get_user_by_id(claims["sub"])
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset link")

    # Enforce single use via the stored jti.
    if not await user_service.consume_reset_jti(str(user["_id"]), claims.get("jti", "")):
        raise HTTPException(status_code=400, detail="This reset link has already been used or is no longer valid")

    await user_service.set_password(str(user["_id"]), hash_password(payload.password))
    try:
        await email_service.send_password_changed_email(user["email"], user.get("name", ""))
    except Exception:
        pass
    return MessageResponse(message="Password reset successfully. You can now sign in.")


# ---------------------------------------------------------------------------
# Admin user management (RBAC-protected)
# ---------------------------------------------------------------------------
@router.get("/users", response_model=UserListResponse)
async def admin_list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    _admin: dict = Depends(require_admin),
):
    """List users (admin only)."""
    try:
        users, total = await user_service.list_users(page=page, limit=limit, search=search)
    except user_service.DatabaseUnavailable:
        raise HTTPException(
            status_code=503,
            detail="User directory is temporarily unavailable. Please retry in a moment.",
        )
    return UserListResponse(
        total=total,
        page=page,
        limit=limit,
        users=[UserPublic.from_document(u) for u in users],
    )


@router.patch("/users/{user_id}/role", response_model=UserPublic)
async def admin_update_role(
    user_id: str, payload: AdminUpdateRoleRequest, admin: dict = Depends(require_admin)
):
    """Change a user's role (admin only). The permanent admin cannot be demoted."""
    target = await user_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("is_permanent_admin") or target.get("email") == PERMANENT_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="The permanent admin account cannot be modified")
    await user_service.update_user(user_id, {"role": payload.role.value})
    fresh = await user_service.get_user_by_id(user_id)
    return UserPublic.from_document(fresh)


@router.patch("/users/{user_id}/status", response_model=UserPublic)
async def admin_update_status(
    user_id: str, payload: AdminUpdateStatusRequest, admin: dict = Depends(require_admin)
):
    """Activate/deactivate a user (admin only). The permanent admin is protected."""
    target = await user_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("is_permanent_admin") or target.get("email") == PERMANENT_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="The permanent admin account cannot be modified")
    updates = {"is_active": payload.is_active}
    if not payload.is_active:
        updates["sessions"] = []  # force logout on deactivation
    await user_service.update_user(user_id, updates)
    fresh = await user_service.get_user_by_id(user_id)
    return UserPublic.from_document(fresh)
