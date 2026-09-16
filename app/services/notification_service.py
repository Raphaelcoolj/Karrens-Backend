import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from pymongo import ASCENDING, DESCENDING
from app.core.database import get_db

logger = logging.getLogger(__name__)

SIGNAL_COLLECTION = "push_subscriptions"
NOTIFICATION_COLLECTION = "notification_logs"


async def ensure_notification_indexes():
    db = get_db()
    await db[SIGNAL_COLLECTION].create_index(
        [("endpoint", ASCENDING)], unique=True, name="idx_subscription_endpoint"
    )
    await db[SIGNAL_COLLECTION].create_index(
        [("active", ASCENDING)], name="idx_subscription_active"
    )
    await db[NOTIFICATION_COLLECTION].create_index(
        [("signal_fingerprint", ASCENDING), ("subscription_id", ASCENDING)],
        name="idx_notification_fingerprint_sub",
    )
    await db[NOTIFICATION_COLLECTION].create_index(
        [("sent_at", DESCENDING)], name="idx_notification_sent_at"
    )


def compute_signal_fingerprint(
    symbol: str,
    timeframe: str,
    direction: str,
    entry: Optional[float],
    stop_loss: Optional[float],
    take_profit: Optional[float],
    strategy: str = "advanced_smc",
) -> str:
    raw = json.dumps(
        {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "direction": direction,
            "entry": round(entry, 8) if entry else None,
            "sl": round(stop_loss, 8) if stop_loss else None,
            "tp": round(take_profit, 8) if take_profit else None,
            "strategy": strategy,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def should_notify(
    trade_status: str,
    direction: str,
    entry: Optional[float],
    stop_loss: Optional[float],
    take_profit: Optional[float],
    risk_reward: Optional[float],
) -> bool:
    if trade_status != "VALIDATED":
        return False
    if direction not in ("LONG", "SHORT"):
        return False
    if entry is None or stop_loss is None or take_profit is None:
        return False
    if risk_reward is None or risk_reward < 1.0:
        return False
    return True


def build_notification_body(
    symbol: str,
    direction: str,
    score: int,
    quality: str,
    entry: float,
    sl: float,
    tp: float,
    rr: float,
) -> str:
    symbol_display = symbol.replace("/", "")
    if len(symbol_display) > 6:
        symbol_display = symbol[:3] + "/" + symbol[3:]
    return (
        f"{symbol_display} — {direction}\n\n"
        f"{score}/100 · {quality}\n\n"
        f"Entry: {entry}\n"
        f"SL: {sl}\n"
        f"TP: {tp}\n"
        f"RR: 1:{rr:.1f}"
    )


async def has_notified(signal_fingerprint: str, subscription_id: str) -> bool:
    db = get_db()
    existing = await db[NOTIFICATION_COLLECTION].find_one(
        {"signal_fingerprint": signal_fingerprint, "subscription_id": subscription_id}
    )
    return existing is not None


async def record_notification(
    signal_fingerprint: str,
    subscription_id: str,
    notification_type: str,
    symbol: str,
    direction: str,
    score: int,
    status: str = "sent",
) -> str:
    db = get_db()
    doc = {
        "signal_fingerprint": signal_fingerprint,
        "subscription_id": subscription_id,
        "notification_type": notification_type,
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "sent_at": datetime.utcnow(),
        "status": status,
    }
    result = await db[NOTIFICATION_COLLECTION].insert_one(doc)
    return str(result.inserted_id)


async def send_web_push(subscription_doc: dict, payload: dict) -> bool:
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        logger.warning("VAPID keys not configured, skipping push")
        return False

    try:
        from pywebpush import webpush, WebPushException

        subscription_info = {
            "endpoint": subscription_doc["endpoint"],
            "keys": {
                "p256dh": subscription_doc["keys"]["p256dh"],
                "auth": subscription_doc["keys"]["auth"],
            },
        }

        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=86400,
        )
        return True
    except Exception as ex:
        error_msg = str(ex)
        if "410" in error_msg or "404" in error_msg or "expired" in error_msg.lower():
            logger.info("Subscription expired/invalid, deactivating")
            db = get_db()
            await db[SIGNAL_COLLECTION].update_one(
                {"endpoint": subscription_doc["endpoint"]},
                {"$set": {"active": False, "last_failure_at": datetime.utcnow()}},
            )
        else:
            logger.error(f"Push send failed: {error_msg[:100]}")
        return False


async def dispatch_signal_notification(
    symbol: str,
    timeframe: str,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    risk_reward: float,
    confidence: int,
    quality: str,
    reasons: list[str],
) -> int:
    if not should_notify("VALIDATED", direction, entry, stop_loss, take_profit, risk_reward):
        return 0

    fp = compute_signal_fingerprint(symbol, timeframe, direction, entry, stop_loss, take_profit)
    db = get_db()
    cursor = db[SIGNAL_COLLECTION].find({"active": True})
    subscriptions = await cursor.to_list(length=500)

    if not subscriptions:
        return 0

    sent_count = 0
    for sub in subscriptions:
        sub_id = str(sub.get("_id", sub.get("endpoint", "")))
        if await has_notified(fp, sub_id):
            continue

        rr_display = f"{risk_reward:.1f}"
        body = build_notification_body(symbol, direction, confidence, quality, entry, stop_loss, take_profit, risk_reward)

        payload = {
            "type": "TRADING_SIGNAL",
            "signal_id": fp,
            "symbol": symbol,
            "direction": direction,
            "score": confidence,
            "quality": quality,
            "entry": str(entry),
            "sl": str(stop_loss),
            "tp": str(take_profit),
            "rr": rr_display,
            "timeframe": timeframe,
            "reason": " | ".join(reasons[:3]) if reasons else "Validated setup",
            "body": body,
        }

        success = await send_web_push(sub, payload)
        status = "sent" if success else "failed"
        await record_notification(fp, sub_id, "NEW_VALIDATED_SIGNAL", symbol, direction, confidence, status)

        if success:
            sent_count += 1
            db = get_db()
            await db[SIGNAL_COLLECTION].update_one(
                {"endpoint": sub["endpoint"]},
                {"$set": {"last_success_at": datetime.utcnow()}, "$inc": {"failure_count": 0}},
            )

    return sent_count
