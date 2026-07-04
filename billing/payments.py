"""
Payments ledger & purchase flow (payments collection).

Current mode is MANUAL/DEV: an order is created, then confirmed directly (no
external gateway charge). Every purchase is recorded so revenue and history are
auditable, and the design is pluggable — when RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET
are configured, create_order/confirm_order can create & verify a real order
instead (see the marked hooks) without changing callers.

On successful confirmation the plan's credits are granted to the user.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from bson import ObjectId
    _BSON = True
except Exception:
    _BSON = False
    class ObjectId:  # type: ignore
        pass

try:
    from database.connection import get_database
except Exception:
    def get_database():
        return None

from billing import entitlements

PAYMENTS_COLLECTION = "payments"

_mem_payments: Dict[str, Dict[str, Any]] = {}


def provider() -> str:
    """Active payment provider. 'razorpay' when keys are set, else 'manual'."""
    if os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET"):
        return "razorpay"
    return "manual"


def _collection():
    db = get_database()
    return db[PAYMENTS_COLLECTION] if db is not None else None


def _to_oid(pid: str):
    if _BSON:
        try:
            return ObjectId(pid)
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Create order
# ---------------------------------------------------------------------------
async def create_order(
    user: Dict[str, Any], plan: Dict[str, Any],
    payment_reference: Optional[str] = None, note: Optional[str] = None,
    status: str = "pending", auto_paid: bool = False, phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a payment record for `plan` and return the order descriptor.

    Default is a `pending` request awaiting admin approval. When `auto_paid` is
    True (admin direct grant), it is recorded as already paid.
    """
    order_id = "vadg_" + uuid.uuid4().hex[:20]
    now = datetime.utcnow()
    doc: Dict[str, Any] = {
        "user_id": str(user["_id"]),
        "user_email": user.get("email"),
        "user_name": user.get("name"),
        "plan_id": str(plan.get("_id")),
        "plan_code": plan.get("code"),
        "plan_name": plan.get("name"),
        "amount_inr": int(plan.get("price_inr", 0)),
        "credits": int(plan.get("credits", 0)),
        "status": "paid" if auto_paid else status,
        "provider": provider(),
        "order_id": order_id,
        "provider_order_id": None,
        "provider_payment_id": None,
        "payment_reference": (payment_reference or "").strip() or None,
        "phone": (phone or "").strip() or user.get("phone") or None,
        "note": (note or "").strip() or None,
        "reviewed_by": None,
        "created_at": now,
        "paid_at": now if auto_paid else None,
    }

    # --- Gateway hook (disabled in manual mode) -----------------------------
    # if provider() == "razorpay":
    #     rp_order = await _razorpay_create_order(doc["amount_inr"], order_id)
    #     doc["provider_order_id"] = rp_order["id"]
    # ------------------------------------------------------------------------

    col = _collection()
    if col is not None:
        res = await col.insert_one(doc)
        doc["_id"] = res.inserted_id
    else:
        doc["_id"] = uuid.uuid4().hex
        _mem_payments[order_id] = doc

    return doc


async def get_payment_by_order(order_id: str) -> Optional[Dict[str, Any]]:
    col = _collection()
    if col is not None:
        return await col.find_one({"order_id": order_id})
    return _mem_payments.get(order_id)


# ---------------------------------------------------------------------------
# Confirm order
# ---------------------------------------------------------------------------
async def confirm_order(
    user: Dict[str, Any], order_id: str,
    provider_payment_id: Optional[str] = None, provider_signature: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Confirm a pending order and grant credits.
    Returns (ok, message, payment_doc). Idempotent: confirming an already-paid
    order does not double-grant credits.
    """
    payment = await get_payment_by_order(order_id)
    if not payment:
        return False, "Order not found", None
    if str(payment.get("user_id")) != str(user["_id"]):
        return False, "Order does not belong to this account", None
    if payment.get("status") == "paid":
        return True, "Order already confirmed", payment
    if payment.get("status") != "pending":
        return False, f"Order cannot be confirmed (status: {payment.get('status')})", payment

    # --- Gateway verification hook (disabled in manual mode) ----------------
    # if provider() == "razorpay":
    #     if not _razorpay_verify(payment["provider_order_id"], provider_payment_id, provider_signature):
    #         await _set_status(order_id, "failed")
    #         return False, "Payment signature verification failed", payment
    # ------------------------------------------------------------------------

    now = datetime.utcnow()
    updates = {
        "status": "paid",
        "paid_at": now,
        "provider_payment_id": provider_payment_id or ("manual_" + uuid.uuid4().hex[:16]),
    }
    await _apply_updates(order_id, updates)
    payment.update(updates)

    # Grant credits for the purchased plan.
    await entitlements.grant_credits(
        str(user["_id"]),
        int(payment.get("credits", 0)),
        plan_code=payment.get("plan_code"),
        plan_name=payment.get("plan_name"),
    )

    return True, "Payment successful", payment


async def _apply_updates(order_id: str, updates: Dict[str, Any]) -> None:
    col = _collection()
    if col is not None:
        await col.update_one({"order_id": order_id}, {"$set": updates})
    elif order_id in _mem_payments:
        _mem_payments[order_id].update(updates)


# ---------------------------------------------------------------------------
# Admin approve / reject (manual verification flow)
# ---------------------------------------------------------------------------
async def approve_order(order_id: str, admin_email: Optional[str] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Admin approves a pending order: mark paid and grant credits to its owner.
    Idempotent — approving an already-paid order does not double-grant.
    Returns (ok, message, payment_doc).
    """
    payment = await get_payment_by_order(order_id)
    if not payment:
        return False, "Order not found", None
    if payment.get("status") == "paid":
        return True, "Order already approved", payment
    if payment.get("status") not in ("pending",):
        return False, f"Order cannot be approved (status: {payment.get('status')})", payment

    now = datetime.utcnow()
    updates = {
        "status": "paid",
        "paid_at": now,
        "reviewed_by": admin_email,
        "provider_payment_id": payment.get("provider_payment_id") or ("manual_" + uuid.uuid4().hex[:16]),
    }
    await _apply_updates(order_id, updates)
    payment.update(updates)

    await entitlements.grant_credits(
        str(payment.get("user_id")),
        int(payment.get("credits", 0)),
        plan_code=payment.get("plan_code"),
        plan_name=payment.get("plan_name"),
    )
    return True, "Payment approved", payment


async def reject_order(order_id: str, reason: Optional[str] = None, admin_email: Optional[str] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Admin rejects a pending order (no credits granted)."""
    payment = await get_payment_by_order(order_id)
    if not payment:
        return False, "Order not found", None
    if payment.get("status") == "paid":
        return False, "Cannot reject an already-approved order", payment

    note = payment.get("note") or ""
    if reason:
        note = (note + " | " if note else "") + f"Rejected: {reason}"
    updates = {"status": "cancelled", "reviewed_by": admin_email, "note": note}
    await _apply_updates(order_id, updates)
    payment.update(updates)
    return True, "Payment rejected", payment


# ---------------------------------------------------------------------------
# Listing / history
# ---------------------------------------------------------------------------
async def list_payments(
    page: int = 1, limit: int = 20, status: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Return (payments, total, paid_revenue_inr)."""
    page = max(1, page)
    limit = max(1, min(limit, 100))
    skip = (page - 1) * limit
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if user_id:
        query["user_id"] = str(user_id)

    col = _collection()
    if col is not None:
        total = await col.count_documents(query)
        cursor = col.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        rev_cursor = col.aggregate([
            {"$match": {"status": "paid"}},
            {"$group": {"_id": None, "sum": {"$sum": "$amount_inr"}}},
        ])
        rev_docs = await rev_cursor.to_list(length=1)
        revenue = rev_docs[0]["sum"] if rev_docs else 0
        return items, total, revenue

    items = list(_mem_payments.values())
    if status:
        items = [p for p in items if p.get("status") == status]
    if user_id:
        items = [p for p in items if str(p.get("user_id")) == str(user_id)]
    items.sort(key=lambda p: p.get("created_at") or datetime.min, reverse=True)
    revenue = sum(p.get("amount_inr", 0) for p in _mem_payments.values() if p.get("status") == "paid")
    return items[skip:skip + limit], len(items), revenue
