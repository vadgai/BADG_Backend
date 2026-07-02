"""
FastAPI auth dependencies for VADG user routes.

Provides:
  get_current_user   — require a valid access token, return the user document
  require_verified   — additionally require a verified email
  require_role(...)  — require one of the given roles (RBAC)
  require_admin      — shorthand for the admin role
  optional_user      — resolve the user if a token is present, else None
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.tokens import decode_access_token
from auth import user_service

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def _resolve_user(credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[Dict[str, Any]]:
    if not credentials or not credentials.credentials:
        return None
    claims = decode_access_token(credentials.credentials)
    if not claims:
        return None
    user_id = claims.get("sub")
    if not user_id:
        return None
    user = await user_service.get_user_by_id(user_id)
    if not user or not user.get("is_active", True):
        return None
    return user


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Dict[str, Any]:
    """Require a valid access token for an active user."""
    user = await _resolve_user(credentials)
    if not user:
        raise _UNAUTH
    return user


async def optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[Dict[str, Any]]:
    """Resolve the user if authenticated, else None (no error)."""
    return await _resolve_user(credentials)


async def require_verified(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Require the authenticated user to have a verified email."""
    if not user.get("is_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address not verified",
        )
    return user


def require_role(*roles: str) -> Callable:
    """Dependency factory: require the user's role to be one of `roles`."""
    allowed: List[str] = [r for r in roles]

    async def _dep(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dep


# Convenience: admin-only dependency
require_admin = require_role("admin")
