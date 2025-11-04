"""
JWT Authentication for Admin Analytics
Handles JWT token creation, verification, and admin authentication
"""

import os
import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET_KEY = os.getenv("ADMIN_JWT_SECRET", "vadg-admin-secret-key-dev-only-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# Admin credentials (static as per requirements)
ADMIN_EMAIL = "m87.krishna@gmail.com"
ADMIN_PASSWORD = "Vadg@44"

security = HTTPBearer(auto_error=False)


def create_access_token(data: Dict[str, Any]) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None


def authenticate_admin(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate admin credentials."""
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        return {"email": email, "role": "admin"}
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

    return token_data


def require_admin_token(authorization: Optional[str] = Header(default=None)):
    """Legacy token guard for backward compatibility (simple token)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ", 1)[1].strip()
    if token != "admin-session-token":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True
