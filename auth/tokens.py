"""
Token utilities for VADG user authentication.

- Access tokens: short-lived JWTs (default 60 min) carrying identity + role.
- Refresh tokens: opaque high-entropy strings; only their SHA-256 hash is stored
  server-side so a database leak cannot be replayed.
- Action tokens: single-purpose JWTs used for email verification and password
  reset links (carry a `purpose` claim and short expiry).

All JWTs are signed with the same secret used by the admin auth module
(auth/jwt_auth.py) so that admin-role access tokens are accepted by the
existing admin dashboard endpoints without a second login.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import jwt

logger = logging.getLogger(__name__)

# Shared signing secret — MUST match auth/jwt_auth.py. Fail-closed if unset.
JWT_SECRET_KEY = os.getenv("ADMIN_JWT_SECRET") or os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"

def _safe_int(name: str, default: int) -> int:
    """Parse an int env var; fall back to default on a malformed value so a bad
    env var can never crash module import / container startup."""
    try:
        return int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        logger.warning("Invalid %s env value; using default %s", name, default)
        return default


# Access token lifetime (minutes). Kept short; refresh token extends the session.
ACCESS_TOKEN_EXPIRE_MINUTES = _safe_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60)
# Refresh token lifetime (days).
REFRESH_TOKEN_EXPIRE_DAYS = _safe_int("REFRESH_TOKEN_EXPIRE_DAYS", 30)
# Email verification link lifetime (hours).
VERIFY_TOKEN_EXPIRE_HOURS = _safe_int("VERIFY_TOKEN_EXPIRE_HOURS", 48)
# Password reset link lifetime (minutes).
RESET_TOKEN_EXPIRE_MINUTES = _safe_int("RESET_TOKEN_EXPIRE_MINUTES", 30)

if not JWT_SECRET_KEY:
    logger.critical(
        "JWT signing secret not configured (set ADMIN_JWT_SECRET or JWT_SECRET_KEY). "
        "User authentication is disabled (fail-closed)."
    )


def is_configured() -> bool:
    """Whether a JWT signing secret is available."""
    return bool(JWT_SECRET_KEY)


# ---------------------------------------------------------------------------
# Access tokens
# ---------------------------------------------------------------------------
def create_access_token(user: Dict[str, Any]) -> str:
    """
    Create a signed JWT access token for a user document.

    Claims: sub (user id), email, role, name, type=access, exp, iat.
    """
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT secret not configured")
    now = datetime.utcnow()
    payload = {
        "sub": str(user.get("_id") or user.get("id") or ""),
        "email": user.get("email"),
        "role": user.get("role", "user"),
        "name": user.get("name"),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode & verify an access token. Returns claims or None if invalid."""
    if not JWT_SECRET_KEY:
        return None
    try:
        claims = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.info("Access token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid access token: %s", e)
        return None
    # Reject non-access tokens presented as access tokens (defence in depth).
    if claims.get("type") not in (None, "access"):
        return None
    return claims


# ---------------------------------------------------------------------------
# Refresh tokens (opaque)
# ---------------------------------------------------------------------------
def generate_refresh_token() -> str:
    """Generate a high-entropy opaque refresh token (URL-safe)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hash of a refresh token for at-rest storage."""
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    """Absolute expiry timestamp for a newly-issued refresh token."""
    return datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)


# ---------------------------------------------------------------------------
# Action tokens (email verification / password reset)
# ---------------------------------------------------------------------------
def create_action_token(user_id: str, purpose: str, minutes: Optional[int] = None) -> str:
    """
    Create a short-lived single-purpose JWT.

    purpose: "verify_email" or "reset_password".
    A random `jti` is embedded so reset tokens can be single-use when combined
    with a stored value (see user_service.set_reset_token).
    """
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT secret not configured")
    if purpose == "verify_email":
        ttl = timedelta(hours=VERIFY_TOKEN_EXPIRE_HOURS)
    elif purpose == "reset_password":
        ttl = timedelta(minutes=minutes or RESET_TOKEN_EXPIRE_MINUTES)
    else:
        ttl = timedelta(minutes=minutes or 30)
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "purpose": purpose,
        "jti": secrets.token_urlsafe(16),
        "type": purpose,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_action_token(token: str, expected_purpose: str) -> Optional[Dict[str, Any]]:
    """Decode & verify an action token, enforcing the expected purpose."""
    if not JWT_SECRET_KEY:
        return None
    try:
        claims = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.info("Action token expired (%s)", expected_purpose)
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid action token: %s", e)
        return None
    if claims.get("purpose") != expected_purpose:
        logger.warning("Action token purpose mismatch")
        return None
    return claims


def access_token_ttl_seconds() -> int:
    """Access token lifetime in seconds (for expires_in responses)."""
    return ACCESS_TOKEN_EXPIRE_MINUTES * 60
