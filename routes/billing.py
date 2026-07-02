"""
User-facing billing routes for VADG (/api/billing).

  GET  /plans      — public plan catalogue + manual-payment instructions
  GET  /balance    — authenticated user's report entitlement
  GET  /history    — authenticated user's payment history
  POST /purchase   — submit a plan request (pending admin approval; emails sent)

Credits are granted only after an admin approves the request (manual payment
verification) — there is intentionally no user-facing self-confirm endpoint.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from models.billing_models import (
    BalanceResponse,
    PaymentListResponse,
    PaymentPublic,
    PlanPublic,
    PurchaseRequest,
)
from auth.dependencies import get_current_user
from auth import email_service
from billing import entitlements, payments, plans

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# Manual-payment instructions shown to users (there is no automated gateway).
PAYMENT_UPI_ID = os.getenv("PAYMENT_UPI_ID", "")
PAYMENT_PAYEE_NAME = os.getenv("PAYMENT_PAYEE_NAME", "VADG")
PAYMENT_INSTRUCTIONS = os.getenv(
    "PAYMENT_INSTRUCTIONS",
    "Pay the plan amount to the UPI ID above, then submit your UPI/UTR reference "
    "below. Your report credits are activated by our team after the payment is "
    "verified — usually within a few hours.",
)


def _payment_info() -> dict:
    return {
        "upi_id": PAYMENT_UPI_ID,
        "payee_name": PAYMENT_PAYEE_NAME,
        "instructions": PAYMENT_INSTRUCTIONS,
        "support_email": os.getenv("SUPPORT_EMAIL", "vadg.office@gmail.com"),
        "manual_approval": True,
    }


@router.get("/plans")
async def get_plans():
    """Public: list active pricing plans (plus the free-tier descriptor)."""
    docs = await plans.list_plans(active_only=True)
    return {
        "success": True,
        "free_per_day": entitlements.FREE_REPORTS_PER_DAY,
        "price_per_report_inr": entitlements.PAY_PER_REPORT_INR,
        "plans": [PlanPublic.from_document(d) for d in docs],
        "payment": _payment_info(),
    }


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(user: dict = Depends(get_current_user)):
    """Authenticated user's current report balance/entitlement."""
    return BalanceResponse(**entitlements.get_balance(user))


@router.get("/reports")
async def get_my_reports(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """The authenticated user's own diagnosis report history + a small summary."""
    items, total = await entitlements.list_user_reports(str(user["_id"]), page=page, limit=limit)
    summary = await entitlements.user_report_summary(str(user["_id"]))
    reports = [
        {
            "session_id": r.get("session_id"),
            "disease": r.get("disease"),
            "diseases": r.get("diseases") or [],
            "symptoms": r.get("symptoms") or [],
            "summary": r.get("summary"),
            "age": r.get("age"),
            "gender": r.get("gender"),
            "source": r.get("source"),
            "created_at": r.get("created_at"),
        }
        for r in items
    ]
    return {"success": True, "total": total, "page": page, "limit": limit, "summary": summary, "reports": reports}


@router.get("/history", response_model=PaymentListResponse)
async def get_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Authenticated user's own payment history."""
    items, total, _rev = await payments.list_payments(page=page, limit=limit, user_id=str(user["_id"]))
    return PaymentListResponse(
        total=total, page=page, limit=limit,
        payments=[PaymentPublic.from_document(p) for p in items],
    )


@router.post("/purchase")
async def purchase(req: PurchaseRequest, user: dict = Depends(get_current_user)):
    """
    Submit a plan purchase REQUEST. Credits are NOT granted here — the request is
    recorded as pending and both the user and the admin are emailed. An admin
    verifies the manual payment and approves it from the dashboard.
    """
    plan = None
    if req.plan_id:
        plan = await plans.get_plan(req.plan_id)
    if not plan and req.plan_code:
        plan = await plans.get_plan_by_code(req.plan_code)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if not plan.get("is_active", True):
        raise HTTPException(status_code=400, detail="This plan is no longer available")

    order = await payments.create_order(
        user, plan, payment_reference=req.payment_reference, note=req.note, status="pending",
    )

    # Notify the admin (to verify) and acknowledge to the user (best-effort).
    try:
        await email_service.send_admin_purchase_request(
            user.get("name", ""), user.get("email", ""), order["plan_name"],
            order["amount_inr"], order["credits"], order["order_id"],
            payment_reference=req.payment_reference or "", note=req.note or "",
        )
    except Exception as e:
        logger.error("Admin purchase-request notification failed: %s", e)
    try:
        await email_service.send_purchase_request_ack(
            user.get("email", ""), user.get("name", ""), order["plan_name"],
            order["amount_inr"], order["order_id"],
        )
    except Exception as e:
        logger.error("User purchase-request ack failed: %s", e)

    return {
        "success": True,
        "status": "pending",
        "order_id": order["order_id"],
        "plan_name": order["plan_name"],
        "amount_inr": order["amount_inr"],
        "credits": order["credits"],
        "message": (
            "Your request has been received. Your report credits will be activated "
            "after our team verifies your payment. You'll get a confirmation email."
        ),
    }
