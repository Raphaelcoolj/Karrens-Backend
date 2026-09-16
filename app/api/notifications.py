from fastapi import APIRouter, HTTPException, Request
from pymongo import ASCENDING
from datetime import datetime
from app.core.config import get_settings
from app.core.database import get_db
from app.models.notification import (
    PushSubscriptionCreate,
    PushSubscription,
    VAPIDKeyResponse,
    SubscribeResponse,
    NotificationStatusResponse,
)
from app.services.notification_service import SIGNAL_COLLECTION, ensure_notification_indexes

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

settings = get_settings()


@router.on_event("startup")
async def startup_notifications():
    await ensure_notification_indexes()


@router.get("/vapid-public-key", response_model=VAPIDKeyResponse)
async def get_vapid_public_key():
    if not settings.VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="VAPID keys not configured")
    return VAPIDKeyResponse(public_key=settings.VAPID_PUBLIC_KEY)


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(req: PushSubscriptionCreate, request: Request):
    db = get_db()
    user_agent = request.headers.get("user-agent", "")
    now = datetime.utcnow()

    existing = await db[SIGNAL_COLLECTION].find_one({"endpoint": req.endpoint})
    if existing:
        if existing.get("active"):
            return SubscribeResponse(
                status="already_subscribed",
                subscription_id=str(existing["_id"]),
            )
        await db[SIGNAL_COLLECTION].update_one(
            {"endpoint": req.endpoint},
            {
                "$set": {
                    "keys.p256dh": req.keys.p256dh,
                    "keys.auth": req.keys.auth,
                    "active": True,
                    "updated_at": now,
                    "failure_count": 0,
                    "user_agent": user_agent,
                }
            },
        )
        updated = await db[SIGNAL_COLLECTION].find_one({"endpoint": req.endpoint})
        return SubscribeResponse(
            status="reactivated",
            subscription_id=str(updated["_id"]),
        )

    doc = {
        "endpoint": req.endpoint,
        "keys": {"p256dh": req.keys.p256dh, "auth": req.keys.auth},
        "user_agent": user_agent,
        "created_at": now,
        "updated_at": now,
        "last_success_at": None,
        "last_failure_at": None,
        "failure_count": 0,
        "active": True,
    }
    result = await db[SIGNAL_COLLECTION].insert_one(doc)
    return SubscribeResponse(status="subscribed", subscription_id=str(result.inserted_id))


@router.delete("/subscribe", response_model=SubscribeResponse)
async def unsubscribe(req: PushSubscriptionCreate):
    db = get_db()
    existing = await db[SIGNAL_COLLECTION].find_one({"endpoint": req.endpoint})
    if not existing:
        return SubscribeResponse(status="not_found")

    await db[SIGNAL_COLLECTION].update_one(
        {"endpoint": req.endpoint},
        {"$set": {"active": False, "updated_at": datetime.utcnow()}},
    )
    return SubscribeResponse(status="unsubscribed", subscription_id=str(existing["_id"]))


@router.get("/status", response_model=NotificationStatusResponse)
async def notification_status(endpoint: str = ""):
    supported = True
    subscribed = False
    sub_id = None

    if endpoint:
        db = get_db()
        existing = await db[SIGNAL_COLLECTION].find_one(
            {"endpoint": endpoint, "active": True}
        )
        if existing:
            subscribed = True
            sub_id = str(existing["_id"])

    return NotificationStatusResponse(
        supported=supported,
        permission="default",
        subscribed=subscribed,
        subscription_id=sub_id,
    )
