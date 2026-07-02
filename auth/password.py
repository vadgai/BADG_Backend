"""
Password hashing utilities for VADG user authentication.
Uses bcrypt via passlib. All hashing/verification is constant-time.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from passlib.context import CryptContext
    _pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    _PASSLIB_AVAILABLE = True
except Exception:  # passlib/bcrypt not installed
    _pwd_ctx = None
    _PASSLIB_AVAILABLE = False
    logger.critical(
        "passlib/bcrypt is unavailable. Install passlib[bcrypt] — password "
        "hashing is REQUIRED and auth will fail closed without it."
    )


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    if not _PASSLIB_AVAILABLE:
        raise RuntimeError("Password hashing unavailable: passlib[bcrypt] not installed")
    # bcrypt has a 72-byte input limit; truncate defensively so long inputs
    # don't raise inside the backend.
    return _pwd_ctx.hash(str(password or "")[:72])


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time verify of a plaintext password against a stored hash."""
    if not _PASSLIB_AVAILABLE or not hashed:
        return False
    try:
        return _pwd_ctx.verify(str(password or "")[:72], hashed)
    except Exception:
        return False


def is_available() -> bool:
    """Whether password hashing is available in this environment."""
    return _PASSLIB_AVAILABLE
