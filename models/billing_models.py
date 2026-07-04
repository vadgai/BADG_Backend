"""
Billing & pricing models for VADG.

Credit-based model:
  - Every registered user gets FREE_REPORTS_PER_DAY free diagnosis reports/day.
  - Beyond that, each report consumes 1 non-expiring credit.
  - Credits are bought pay-as-you-go (₹29/report) or in packs (₹399→15, ₹599→25).
  - Admin accounts have unlimited reports.

Collections: pricing_plans, payments, report_usage. Entitlement state lives on
the auth_users document (report_credits, free_report_date, subscription, ...).
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class PlanType(str, Enum):
    PAYG = "payg"   # pay-as-you-go single report
    PACK = "pack"   # bundle of credits


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReportSource(str, Enum):
    FREE = "free"       # daily free allowance
    CREDIT = "credit"   # consumed a paid credit
    ADMIN = "admin"     # admin / unlimited


# ---------------------------------------------------------------------------
# Pricing plans
# ---------------------------------------------------------------------------
class PlanBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=40, description="Stable unique plan code")
    name: str = Field(..., min_length=2, max_length=80)
    description: Optional[str] = Field(None, max_length=280)
    price_inr: int = Field(..., ge=0, description="Price in whole rupees")
    credits: int = Field(..., ge=1, description="Report credits granted on purchase")
    type: PlanType = PlanType.PACK
    is_active: bool = True
    sort_order: int = 0
    highlight: bool = Field(default=False, description="Feature this plan in the UI")


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=80)
    description: Optional[str] = Field(None, max_length=280)
    price_inr: Optional[int] = Field(None, ge=0)
    credits: Optional[int] = Field(None, ge=1)
    type: Optional[PlanType] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    highlight: Optional[bool] = None


class PlanPublic(PlanBase):
    id: str

    @staticmethod
    def from_document(doc: dict) -> "PlanPublic":
        return PlanPublic(
            id=str(doc.get("_id")),
            code=doc.get("code"),
            name=doc.get("name"),
            description=doc.get("description"),
            price_inr=doc.get("price_inr", 0),
            credits=doc.get("credits", 1),
            type=doc.get("type", PlanType.PACK),
            is_active=doc.get("is_active", True),
            sort_order=doc.get("sort_order", 0),
            highlight=doc.get("highlight", False),
        )


# ---------------------------------------------------------------------------
# Balance / entitlements
# ---------------------------------------------------------------------------
class BalanceResponse(BaseModel):
    """A user's current report entitlement snapshot."""
    unlimited: bool = False
    free_per_day: int
    free_used_today: int
    free_available_today: int
    credits: int
    reports_available: bool
    price_per_report_inr: int
    total_reports_used: int = 0
    plan: Optional[dict] = None  # most-recent purchased pack, for display


# ---------------------------------------------------------------------------
# Payments / purchase flow
# ---------------------------------------------------------------------------
class PurchaseRequest(BaseModel):
    plan_id: Optional[str] = None
    plan_code: Optional[str] = None
    # Optional contact number so our team can reach the user about their request.
    phone: Optional[str] = Field(None, max_length=20)
    note: Optional[str] = Field(None, max_length=400)


class ConfirmPaymentRequest(BaseModel):
    order_id: str
    # Gateway fields (used when a real provider is wired in; ignored in manual mode)
    provider_payment_id: Optional[str] = None
    provider_signature: Optional[str] = None


class RejectPaymentRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=300)


class GrantPlanRequest(BaseModel):
    """Admin grants a plan/credits to a user after verifying a manual payment."""
    plan_id: Optional[str] = None
    plan_code: Optional[str] = None
    payment_reference: Optional[str] = Field(None, max_length=120)
    note: Optional[str] = Field(None, max_length=400)


class PaymentPublic(BaseModel):
    id: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    amount_inr: int = 0
    credits: int = 0
    status: PaymentStatus = PaymentStatus.PENDING
    provider: str = "manual"
    order_id: Optional[str] = None
    provider_payment_id: Optional[str] = None
    payment_reference: Optional[str] = None
    phone: Optional[str] = None
    note: Optional[str] = None
    reviewed_by: Optional[str] = None
    created_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None

    @staticmethod
    def from_document(doc: dict) -> "PaymentPublic":
        return PaymentPublic(
            id=str(doc.get("_id")),
            user_id=str(doc.get("user_id")) if doc.get("user_id") else None,
            user_email=doc.get("user_email"),
            plan_code=doc.get("plan_code"),
            plan_name=doc.get("plan_name"),
            amount_inr=doc.get("amount_inr", 0),
            credits=doc.get("credits", 0),
            status=doc.get("status", PaymentStatus.PENDING),
            provider=doc.get("provider", "manual"),
            order_id=doc.get("order_id"),
            provider_payment_id=doc.get("provider_payment_id"),
            payment_reference=doc.get("payment_reference"),
            phone=doc.get("phone"),
            note=doc.get("note"),
            reviewed_by=doc.get("reviewed_by"),
            created_at=doc.get("created_at"),
            paid_at=doc.get("paid_at"),
        )


class OrderResponse(BaseModel):
    success: bool = True
    order_id: str
    amount_inr: int
    credits: int
    plan_name: str
    provider: str
    # When a real gateway is configured these carry its key/order handle.
    provider_order_id: Optional[str] = None
    provider_key: Optional[str] = None
    # True when no gateway is configured and the client should call /confirm directly.
    manual: bool = True


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------
class PaymentListResponse(BaseModel):
    success: bool = True
    total: int
    page: int
    limit: int
    revenue_inr: int = 0
    payments: List[PaymentPublic] = []


class AdjustCreditsRequest(BaseModel):
    delta: int = Field(..., description="Credits to add (positive) or remove (negative)")
    reason: Optional[str] = Field(None, max_length=200)
