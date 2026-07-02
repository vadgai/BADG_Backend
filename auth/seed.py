"""
Seed / enforce the permanent VADG admin account.

Ensures m87.krishna@gmail.com (override with PERMANENT_ADMIN_EMAIL) always
exists in auth_users as a verified, active admin flagged is_permanent_admin
(so it can never be demoted or deactivated via the API).

Password source, in order of preference:
  PERMANENT_ADMIN_PASSWORD  → explicit permanent-admin password
  ADMIN_PASSWORD            → reuse the legacy env-admin password
If neither is set, a random password is generated and the admin must use the
"forgot password" flow to set one (a warning is logged).
"""

import logging
import os
import secrets

logger = logging.getLogger(__name__)

PERMANENT_ADMIN_EMAIL = os.getenv("PERMANENT_ADMIN_EMAIL", "m87.krishna@gmail.com").strip().lower()
PERMANENT_ADMIN_NAME = os.getenv("PERMANENT_ADMIN_NAME", "VADG Admin")


async def seed_permanent_admin() -> None:
    """Idempotently create or repair the permanent admin account."""
    try:
        from auth import user_service
        from auth.password import hash_password, is_available as pw_available
    except Exception as e:
        logger.error("Cannot seed permanent admin (auth modules unavailable): %s", e)
        return

    if not pw_available():
        logger.error("Cannot seed permanent admin: password hashing unavailable (passlib[bcrypt]).")
        return

    try:
        existing = await user_service.get_user_by_email(PERMANENT_ADMIN_EMAIL)
    except Exception as e:
        logger.error("Permanent admin seed lookup failed: %s", e)
        return

    if existing:
        # Enforce invariants without touching the password.
        repairs = {}
        if existing.get("role") != "admin":
            repairs["role"] = "admin"
        if not existing.get("is_permanent_admin"):
            repairs["is_permanent_admin"] = True
        if not existing.get("is_verified"):
            repairs["is_verified"] = True
        if not existing.get("is_active", True):
            repairs["is_active"] = True
        if repairs:
            await user_service.update_user(str(existing["_id"]), repairs)
            logger.info("Permanent admin invariants repaired: %s", list(repairs.keys()))
        else:
            logger.info("Permanent admin present and correct: %s", PERMANENT_ADMIN_EMAIL)
        return

    # Create fresh.
    password = os.getenv("PERMANENT_ADMIN_PASSWORD") or os.getenv("ADMIN_PASSWORD")
    generated = False
    if not password:
        password = secrets.token_urlsafe(16)
        generated = True

    try:
        await user_service.create_user(
            name=PERMANENT_ADMIN_NAME,
            email=PERMANENT_ADMIN_EMAIL,
            password_hash=hash_password(password),
            role="admin",
            is_verified=True,
            is_permanent_admin=True,
        )
    except Exception as e:
        logger.error("Failed to create permanent admin: %s", e)
        return

    if generated:
        logger.warning(
            "Permanent admin %s created with a RANDOM password. Set "
            "PERMANENT_ADMIN_PASSWORD (or ADMIN_PASSWORD) in the environment, or "
            "use the 'forgot password' flow to set one.",
            PERMANENT_ADMIN_EMAIL,
        )
    else:
        logger.info("Permanent admin %s created from configured password.", PERMANENT_ADMIN_EMAIL)


# ---------------------------------------------------------------------------
# Dummy users (development / demo)
# ---------------------------------------------------------------------------
# Deterministic sample accounts to populate the admin dashboard. All share the
# same password so they are easy to sign in with while testing.
DUMMY_PASSWORD = os.getenv("DUMMY_USER_PASSWORD", "Test@1234")

DUMMY_USERS = [
    # name, email, role, verified, active, credits, total_reports, plan_name
    ("Riya Sharma",   "riya.sharma@example.com",   "user",  True,  True,  5,  3,  "Standard Pack"),
    ("Arjun Verma",   "arjun.verma@example.com",   "user",  True,  True,  0,  1,  None),
    ("Neha Gupta",    "neha.gupta@example.com",    "user",  False, True,  12, 0,  "Standard Pack"),
    ("Vikram Singh",  "vikram.singh@example.com",  "user",  True,  False, 0,  2,  None),
    ("Ananya Rao",    "ananya.rao@example.com",    "admin", True,  True,  0,  8,  None),
    ("Rahul Mehta",   "rahul.mehta@example.com",   "user",  True,  True,  25, 5,  "Premium Pack"),
    ("Priya Nair",    "priya.nair@example.com",    "user",  True,  True,  1,  0,  "Pay As You Go"),
]


async def seed_dummy_users() -> int:
    """
    Create a handful of demo users (idempotent — skips existing emails).
    Returns the number of users created. Intended for dev/demo only.
    """
    try:
        from auth import user_service
        from auth.password import hash_password, is_available as pw_available
    except Exception as e:
        logger.error("Cannot seed dummy users (auth modules unavailable): %s", e)
        return 0

    if not pw_available():
        logger.error("Cannot seed dummy users: password hashing unavailable.")
        return 0

    created = 0
    from datetime import datetime
    for name, email, role, verified, active, credits, total, plan_name in DUMMY_USERS:
        try:
            if await user_service.get_user_by_email(email):
                continue
            user = await user_service.create_user(
                name=name,
                email=email,
                password_hash=hash_password(DUMMY_PASSWORD),
                role=role,
                is_verified=verified,
            )
            updates = {}
            if credits:
                updates["report_credits"] = credits
            if total:
                updates["total_reports"] = total
            if not active:
                updates["is_active"] = False
            if plan_name:
                updates["subscription"] = {
                    "plan_name": plan_name,
                    "credits": credits,
                    "purchased_at": datetime.utcnow(),
                }
            if updates:
                await user_service.update_user(str(user["_id"]), updates)
            created += 1
        except Exception as e:
            logger.error("Failed to seed dummy user %s: %s", email, e)

    if created:
        logger.info("Seeded %d dummy users (password: %s)", created, DUMMY_PASSWORD)
    else:
        logger.info("Dummy users already present — nothing to seed.")
    return created
