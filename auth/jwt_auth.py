"""
JWT Authentication for Admin Analytics
Handles JWT token creation, verification, and admin authentication
"""

import os
import secrets
import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# JWT Configuration — the signing secret MUST come from the environment.
# There is deliberately NO insecure fallback: if it is unset, admin auth fails closed.
JWT_SECRET_KEY = os.getenv("ADMIN_JWT_SECRET") or os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("ADMIN_JWT_EXPIRY_HOURS", "24"))

# Admin credentials — env-only (previously hardcoded in source). Provide either
# ADMIN_PASSWORD_HASH (bcrypt, preferred) or ADMIN_PASSWORD (plaintext, dev only).
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")

try:
    from passlib.context import CryptContext
    _pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
except Exception:  # passlib/bcrypt not installed
    _pwd_ctx = None

_ADMIN_CONFIGURED = bool(JWT_SECRET_KEY and ADMIN_EMAIL and (ADMIN_PASSWORD or ADMIN_PASSWORD_HASH))
if not _ADMIN_CONFIGURED:
    logger.critical(
        "Admin auth is NOT configured. Set ADMIN_JWT_SECRET (or JWT_SECRET_KEY), ADMIN_EMAIL, "
        "and ADMIN_PASSWORD_HASH (or ADMIN_PASSWORD). Admin login is disabled (fail-closed)."
    )

security = HTTPBearer(auto_error=False)


def create_access_token(data: Dict[str, Any]) -> str:
    """Create JWT access token. Requires a configured signing secret."""
    if not JWT_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Admin authentication is not configured")
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT. Returns None if auth is unconfigured or the token is invalid."""
    if not JWT_SECRET_KEY:
        return None
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None


def _verify_password(password: str, *, plaintext: Optional[str], hashed: Optional[str]) -> bool:
    """Constant-time password check; prefers a bcrypt hash when configured."""
    if hashed:
        if _pwd_ctx is None:
            logger.error("ADMIN_PASSWORD_HASH is set but passlib/bcrypt is unavailable; denying.")
            return False
        try:
            return _pwd_ctx.verify(str(password or ""), hashed)
        except Exception:
            return False
    if plaintext is not None:
        return secrets.compare_digest(str(password or ""), plaintext)
    return False


def authenticate_admin(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate admin credentials. Fail-closed if unconfigured; constant-time comparison."""
    if not _ADMIN_CONFIGURED:
        logger.error("Admin login attempted but admin auth is not configured; denying.")
        return None
    email_ok = secrets.compare_digest(str(email or "").strip().lower(), ADMIN_EMAIL.strip().lower())
    password_ok = _verify_password(password, plaintext=ADMIN_PASSWORD, hashed=ADMIN_PASSWORD_HASH)
    if email_ok and password_ok:
        return {"email": ADMIN_EMAIL, "role": "admin"}
    return None


async def get_current_admin(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[str, Any]:
    """Dependency to get current admin from JWT token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = verify_token(credentials.credentials)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # RBAC: admin dashboard requires the admin role. User-account access tokens
    # are signed with the SAME secret, so without this check any authenticated
    # user could reach admin endpoints. Reject non-admin (and non-access) tokens.
    if token_data.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    if token_data.get("type") not in (None, "access"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    return token_data
