"""
Pricing plan management (pricing_plans collection).

Plans are data, not code — the admin can create/edit/deactivate them, so the
pricing model scales to future tiers without code changes. Default plans are
seeded on startup if the collection is empty.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

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

COLLECTION = "pricing_plans"

# In-memory fallback store.
_mem_plans: Dict[str, Dict[str, Any]] = {}

# Default catalogue — matches the product pricing:
#   free 1/day (handled by entitlements, not a plan), ₹29/report, ₹399→12, ₹599→25.
DEFAULT_PLANS: List[Dict[str, Any]] = [
    {
        "code": "payg",
        "name": "Pay As You Go",
        "description": "One extra diagnosis report whenever you need it.",
        "price_inr": 29,
        "credits": 1,
        "type": "payg",
        "is_active": True,
        "sort_order": 1,
        "highlight": False,
    },
    {
        "code": "pack12",
        "name": "Standard Pack",
        "description": "12 diagnosis reports. Best for regular check-ins.",
        "price_inr": 399,
        "credits": 12,
        "type": "pack",
        "is_active": True,
        "sort_order": 2,
        "highlight": True,
    },
    {
        "code": "pack25",
        "name": "Premium Pack",
        "description": "25 diagnosis reports. Best value per report.",
        "price_inr": 599,
        "credits": 25,
        "type": "pack",
        "is_active": True,
        "sort_order": 3,
        "highlight": False,
    },
]


def _collection():
    db = get_database()
    return db[COLLECTION] if db is not None else None


def _to_oid(plan_id: str):
    if _BSON:
        try:
            return ObjectId(plan_id)
        except Exception:
            return None
    return None


async def seed_default_plans() -> None:
    """Insert the default catalogue if no plans exist yet (idempotent)."""
    col = _collection()
    now = datetime.utcnow()
    if col is not None:
        try:
            count = await col.count_documents({})
            if count == 0:
                docs = [{**p, "created_at": now, "updated_at": now} for p in DEFAULT_PLANS]
                await col.insert_many(docs)
                logger.info("Seeded %d default pricing plans", len(docs))
        except Exception as e:
            logger.error("Failed to seed pricing plans: %s", e)
        return
    # In-memory fallback
    if not _mem_plans:
        for p in DEFAULT_PLANS:
            pid = uuid.uuid4().hex
            _mem_plans[pid] = {**p, "_id": pid, "created_at": now, "updated_at": now}


async def list_plans(active_only: bool = False) -> List[Dict[str, Any]]:
    col = _collection()
    if col is not None:
        query = {"is_active": True} if active_only else {}
        cursor = col.find(query).sort("sort_order", 1)
        return await cursor.to_list(length=200)
    plans = list(_mem_plans.values())
    if active_only:
        plans = [p for p in plans if p.get("is_active", True)]
    plans.sort(key=lambda p: p.get("sort_order", 0))
    return plans


async def get_plan(plan_id: str) -> Optional[Dict[str, Any]]:
    col = _collection()
    if col is not None:
        oid = _to_oid(plan_id)
        return await col.find_one({"_id": oid}) if oid else None
    return _mem_plans.get(str(plan_id))


async def get_plan_by_code(code: str) -> Optional[Dict[str, Any]]:
    col = _collection()
    if col is not None:
        return await col.find_one({"code": code})
    for p in _mem_plans.values():
        if p.get("code") == code:
            return p
    return None


async def create_plan(data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow()
    doc = {**data, "created_at": now, "updated_at": now}
    col = _collection()
    if col is not None:
        res = await col.insert_one(doc)
        doc["_id"] = res.inserted_id
        return doc
    pid = uuid.uuid4().hex
    doc["_id"] = pid
    _mem_plans[pid] = doc
    return doc


async def update_plan(plan_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    updates = {k: v for k, v in updates.items() if v is not None}
    updates["updated_at"] = datetime.utcnow()
    col = _collection()
    if col is not None:
        oid = _to_oid(plan_id)
        if not oid:
            return None
        await col.update_one({"_id": oid}, {"$set": updates})
        return await col.find_one({"_id": oid})
    p = _mem_plans.get(str(plan_id))
    if not p:
        return None
    p.update(updates)
    return p


async def delete_plan(plan_id: str) -> bool:
    """Soft-delete by deactivating (keeps payment history references intact)."""
    updated = await update_plan(plan_id, {"is_active": False})
    return updated is not None
