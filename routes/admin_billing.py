"""
Admin dashboard routes for user, subscription, payment, usage and plan
management (/api/admin/billing).

Protected by the admin-token dependency (auth.jwt_auth.get_current_admin) so it
works for both the legacy env admin and DB admin users (e.g. the permanent
admin). Extends the existing admin dashboard.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from models.billing_models import (
    AdjustCreditsRequest,
    GrantPlanRequest,
    PaymentListResponse,
    PaymentPublic,
    PlanCreate,
    PlanPublic,
    PlanUpdate,
    RejectPaymentRequest,
)
from models.user_models import AdminUpdateRoleRequest, AdminUpdateStatusRequest, UserPublic
from auth.jwt_auth import get_current_admin
from auth import user_service, email_service
from billing import entitlements, payments, plans

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/billing", tags=["admin-billing"])

PERMANENT_ADMIN_EMAIL = os.getenv("PERMANENT_ADMIN_EMAIL", "m87.krishna@gmail.com").strip().lower()


def _is_protected(user: dict) -> bool:
    return bool(user.get("is_permanent_admin")) or user.get("email") == PERMANENT_ADMIN_EMAIL


def _safe_int(value, default: int = 0) -> int:
    """Coerce a possibly-dirty stored value to int without raising."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _user_with_billing(doc: dict) -> dict:
    """UserPublic + entitlement balance, for admin tables.

    Fully defensive: it must never raise, so that a single malformed user
    document cannot break the entire admin listing (one bad row ⇒ 500 ⇒ the
    dashboard shows zero users). On unexpected data it returns a minimal, safe
    row and logs the offending id for follow-up.
    """
    doc = doc or {}
    try:
        base = UserPublic.from_document(doc).model_dump()
        base["balance"] = entitlements.get_balance(doc)
        base["report_credits"] = _safe_int(doc.get("report_credits", 0))
        base["total_reports"] = _safe_int(doc.get("total_reports", 0))
        base["subscription"] = doc.get("subscription")
        return base
    except Exception as e:  # pragma: no cover - defensive last resort
        uid = str(doc.get("_id") or doc.get("id") or "")
        logger.error("Failed to serialize user %s for admin listing: %s", uid, e)
        return {
            "id": uid,
            "name": str(doc.get("name") or ""),
            "email": str(doc.get("email") or ""),
            "role": "user",
            "is_active": bool(doc.get("is_active", True)),
            "is_verified": bool(doc.get("is_verified", False)),
            "is_permanent_admin": bool(doc.get("is_permanent_admin", False)),
            "report_credits": _safe_int(doc.get("report_credits", 0)),
            "total_reports": _safe_int(doc.get("total_reports", 0)),
            "subscription": doc.get("subscription"),
            "balance": None,
            "_malformed": True,
        }


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
@router.get("/overview")
async def overview(_admin=Depends(get_current_admin)):
    """High-level metrics for the admin dashboard home."""
    _p, total_payments, revenue = await payments.list_payments(page=1, limit=1, status="paid")
    stats = await entitlements.usage_stats(days=14)
    active_plans = await plans.list_plans(active_only=True)

    # User counts via cheap indexed count queries (no document paging). Best
    # effort: a transient DB blip degrades these KPIs to 0 rather than 500-ing
    # the whole overview card.
    try:
        total_users = await user_service.count_users()
        subscribers = await user_service.count_users(with_credits=True)
    except user_service.DatabaseUnavailable:
        total_users = 0
        subscribers = 0

    return {
        "success": True,
        "total_users": total_users,
        "paid_orders": total_payments,
        "revenue_inr": revenue,
        "subscribers_with_credits": subscribers,
        "reports_total": stats.get("total", 0),
        "reports_today": stats.get("today", 0),
        "reports_by_source": stats.get("by_source", {}),
        "reports_daily": stats.get("daily", []),
        "active_plans": len(active_plans),
        "price_per_report_inr": entitlements.PAY_PER_REPORT_INR,
        "free_per_day": entitlements.FREE_REPORTS_PER_DAY,
    }


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    _admin=Depends(get_current_admin),
):
    try:
        users, total = await user_service.list_users(page=page, limit=limit, search=search)
    except user_service.DatabaseUnavailable:
        raise HTTPException(
            status_code=503,
            detail="User directory is temporarily unavailable. Please retry in a moment.",
        )
    return {
        "success": True,
        "total": total,
        "page": page,
        "limit": limit,
        "users": [_user_with_billing(u) for u in users],
    }


@router.get("/users/{user_id}")
async def get_user(user_id: str, _admin=Depends(get_current_admin)):
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    payments_list, total, _rev = await payments.list_payments(page=1, limit=20, user_id=user_id)
    return {
        "success": True,
        "user": _user_with_billing(user),
        "payments": [PaymentPublic.from_document(p).model_dump() for p in payments_list],
        "payments_total": total,
    }


@router.patch("/users/{user_id}/status")
async def set_user_status(user_id: str, payload: AdminUpdateStatusRequest, _admin=Depends(get_current_admin)):
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if _is_protected(user):
        raise HTTPException(status_code=403, detail="The permanent admin account cannot be modified")
    updates = {"is_active": payload.is_active}
    if not payload.is_active:
        updates["sessions"] = []  # force logout on deactivation
    await user_service.update_user(user_id, updates)
    fresh = await user_service.get_user_by_id(user_id)
    return {"success": True, "user": _user_with_billing(fresh)}


@router.patch("/users/{user_id}/role")
async def set_user_role(user_id: str, payload: AdminUpdateRoleRequest, _admin=Depends(get_current_admin)):
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if _is_protected(user):
        raise HTTPException(status_code=403, detail="The permanent admin account cannot be modified")
    await user_service.update_user(user_id, {"role": payload.role.value})
    fresh = await user_service.get_user_by_id(user_id)
    return {"success": True, "user": _user_with_billing(fresh)}


@router.post("/users/{user_id}/credits")
async def adjust_credits(user_id: str, payload: AdjustCreditsRequest, _admin=Depends(get_current_admin)):
    """Manually add/remove report credits (support, refunds, comps)."""
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    updated = await user_service.adjust_credits_atomic(user_id, int(payload.delta))
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    logger.info("Admin adjusted credits for %s: %+d -> %d (%s)",
                user.get("email"), payload.delta, int(updated.get("report_credits", 0) or 0), payload.reason or "")

    # Only a genuine grant (positive delta) is a "congratulations" moment for
    # the user — a negative delta is a deduction/correction, which does not
    # warrant one. Best-effort: an email hiccup must never fail the credit
    # adjustment itself, which has already been committed above.
    if payload.delta > 0:
        try:
            await email_service.send_credits_granted(
                updated.get("email", ""), updated.get("name", ""),
                int(payload.delta), int(updated.get("report_credits", 0) or 0),
                reason=payload.reason,
            )
        except Exception as e:
            logger.error("Credit-grant congratulations email failed: %s", e)

    return {"success": True, "user": _user_with_billing(updated)}


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
@router.get("/payments", response_model=PaymentListResponse)
async def list_all_payments(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    _admin=Depends(get_current_admin),
):
    items, total, revenue = await payments.list_payments(page=page, limit=limit, status=status)
    return PaymentListResponse(
        total=total, page=page, limit=limit, revenue_inr=revenue,
        payments=[PaymentPublic.from_document(p) for p in items],
    )


def _admin_email(admin: dict) -> Optional[str]:
    return admin.get("email") if isinstance(admin, dict) else None


def _admin_name(admin: dict) -> Optional[str]:
    # The legacy env-admin token only carries `email`/`role` claims (no `name`),
    # while a DB admin user's token includes `name` — handle both.
    return admin.get("name") if isinstance(admin, dict) else None


@router.post("/payments/{order_id}/approve")
async def approve_payment(order_id: str, admin=Depends(get_current_admin)):
    """Approve a pending request: grant credits and email the user."""
    ok, message, payment = await payments.approve_order(order_id, admin_email=_admin_email(admin))
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    # Email the user their plan is active (best-effort).
    try:
        buyer = await user_service.get_user_by_id(str(payment.get("user_id")))
        new_balance = int((buyer or {}).get("report_credits", 0) or 0)
        await email_service.send_purchase_approved(
            payment.get("user_email", ""), (buyer or {}).get("name", ""),
            payment.get("plan_name", "plan"), int(payment.get("credits", 0)), new_balance,
        )
    except Exception as e:
        logger.error("Approval email failed: %s", e)
    return {"success": True, "message": message, "payment": PaymentPublic.from_document(payment).model_dump()}


@router.post("/payments/{order_id}/reject")
async def reject_payment(order_id: str, payload: RejectPaymentRequest, admin=Depends(get_current_admin)):
    """Reject a pending request and email the user."""
    ok, message, payment = await payments.reject_order(order_id, reason=payload.reason, admin_email=_admin_email(admin))
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    try:
        buyer = await user_service.get_user_by_id(str(payment.get("user_id")))
        await email_service.send_purchase_rejected(
            payment.get("user_email", ""), (buyer or {}).get("name", ""),
            payment.get("plan_name", "plan"), payload.reason or "",
        )
    except Exception as e:
        logger.error("Rejection email failed: %s", e)
    return {"success": True, "message": message, "payment": PaymentPublic.from_document(payment).model_dump()}


# ---------------------------------------------------------------------------
# Direct grant (admin gives a plan/credits after a verified manual payment)
# ---------------------------------------------------------------------------
@router.post("/users/{user_id}/grant")
async def grant_plan(user_id: str, payload: GrantPlanRequest, admin=Depends(get_current_admin)):
    """Grant a plan's credits to a user directly, recording a paid payment."""
    target = await user_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    plan = None
    if payload.plan_id:
        plan = await plans.get_plan(payload.plan_id)
    if not plan and payload.plan_code:
        plan = await plans.get_plan_by_code(payload.plan_code)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    note = (payload.note or "") + f" | Granted by admin {_admin_email(admin) or ''}".rstrip()
    order = await payments.create_order(
        target, plan, payment_reference=payload.payment_reference, note=note, auto_paid=True,
    )
    await payments.get_payment_by_order(order["order_id"])
    new_balance = await entitlements.grant_credits(
        user_id, int(plan.get("credits", 0)),
        plan_code=plan.get("code"), plan_name=plan.get("name"),
    )
    try:
        await email_service.send_purchase_approved(
            target.get("email", ""), target.get("name", ""),
            plan.get("name", "plan"), int(plan.get("credits", 0)), int(new_balance or 0),
        )
    except Exception as e:
        logger.error("Grant email failed: %s", e)

    # Confirmation receipt to the admin who performed the grant — kept in a
    # separate try/except so a failure here never masks or blocks the
    # user-facing email above (the grant itself has already been committed).
    try:
        admin_email_addr = _admin_email(admin)
        if admin_email_addr:
            await email_service.send_admin_grant_confirmation(
                admin_email_addr, _admin_name(admin),
                target.get("name", ""), target.get("email", ""),
                plan.get("name", "plan"), int(plan.get("credits", 0)),
                order["order_id"],
            )
    except Exception as e:
        logger.error("Grant admin-confirmation email failed: %s", e)

    fresh = await user_service.get_user_by_id(user_id)
    return {"success": True, "user": _user_with_billing(fresh), "order_id": order["order_id"]}


# ---------------------------------------------------------------------------
# Usage / diagnosis activity
# ---------------------------------------------------------------------------
@router.get("/usage")
async def usage(days: int = Query(14, ge=1, le=90), limit: int = Query(50, ge=1, le=200),
                _admin=Depends(get_current_admin)):
    stats = await entitlements.usage_stats(days=days)
    activity = await entitlements.recent_activity(limit=limit)
    for a in activity:
        a["_id"] = str(a.get("_id", ""))
    return {"success": True, "stats": stats, "activity": activity}


# ---------------------------------------------------------------------------
# Pricing plan management
# ---------------------------------------------------------------------------
@router.get("/plans")
async def admin_list_plans(_admin=Depends(get_current_admin)):
    docs = await plans.list_plans(active_only=False)
    return {"success": True, "plans": [PlanPublic.from_document(d).model_dump() for d in docs]}


@router.post("/plans")
async def admin_create_plan(payload: PlanCreate, _admin=Depends(get_current_admin)):
    existing = await plans.get_plan_by_code(payload.code)
    if existing:
        raise HTTPException(status_code=409, detail="A plan with this code already exists")
    doc = await plans.create_plan(payload.model_dump())
    return {"success": True, "plan": PlanPublic.from_document(doc).model_dump()}


@router.patch("/plans/{plan_id}")
async def admin_update_plan(plan_id: str, payload: PlanUpdate, _admin=Depends(get_current_admin)):
    updates = payload.model_dump(exclude_unset=True)
    # Serialize enum values for storage.
    if "type" in updates and updates["type"] is not None:
        updates["type"] = updates["type"].value if hasattr(updates["type"], "value") else updates["type"]
    doc = await plans.update_plan(plan_id, updates)
    if not doc:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"success": True, "plan": PlanPublic.from_document(doc).model_dump()}


@router.delete("/plans/{plan_id}")
async def admin_delete_plan(plan_id: str, _admin=Depends(get_current_admin)):
    ok = await plans.delete_plan(plan_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"success": True, "message": "Plan deactivated"}
