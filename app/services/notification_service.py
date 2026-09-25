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
STATE_COLLECTION = "signal_states"

# Notification event types, ordered by priority (highest first).
EVENT_DIRECTION_CHANGE = "DIRECTION_CHANGE"
EVENT_VALIDATED_SETUP = "VALIDATED_SETUP"
EVENT_CONFIDENCE_INCREASE = "CONFIDENCE_INCREASE"
EVENT_NEW_HIGH_CONFIDENCE = "NEW_HIGH_CONFIDENCE"

EVENT_PRIORITY = (
    EVENT_DIRECTION_CHANGE,
    EVENT_VALIDATED_SETUP,
    EVENT_CONFIDENCE_INCREASE,
    EVENT_NEW_HIGH_CONFIDENCE,
)


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
    await db[STATE_COLLECTION].create_index(
        [("symbol", ASCENDING), ("timeframe", ASCENDING)],
        unique=True,
        name="idx_signal_state_symbol_tf",
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


# ---------------------------------------------------------------------------
# Directional signal events (always-on notification policy)
# ---------------------------------------------------------------------------
def signal_snapshot(symbol: str, timeframe: str, signal) -> dict:
    """Serialise a DirectionalSignal into the persisted per-symbol state."""
    entry = getattr(signal, "entry", None)
    sl = getattr(signal, "sl", None)
    tp = getattr(signal, "tp", None)
    levels_fp = ""
    if entry is not None and sl is not None and tp is not None:
        levels_fp = compute_signal_fingerprint(
            symbol, timeframe, getattr(signal, "direction", "NEUTRAL"), entry, sl, tp
        )
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "status": getattr(signal, "status", "OK"),
        "direction": getattr(signal, "direction", "NEUTRAL"),
        "confidence": int(getattr(signal, "confidence", 0) or 0),
        "confidence_label": getattr(signal, "confidence_label", ""),
        "setup_status": getattr(signal, "setup_status", "NONE"),
        "risk": getattr(signal, "risk", "UNKNOWN"),
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": getattr(signal, "rr", None),
        "fingerprint": levels_fp,
        "updated_at": datetime.utcnow().isoformat(),
    }


def compute_event_fingerprint(symbol: str, timeframe: str, event: dict) -> str:
    """Fingerprint an event so the same transition is only pushed once.

    * direction change  -> the (from -> to) direction pair
    * validated setup   -> direction + exact levels
    * confidence events -> 10-point confidence bucket
    """
    event_type = event.get("type", "")
    payload: dict = {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "type": event_type,
    }
    if event_type == EVENT_DIRECTION_CHANGE:
        payload["pair"] = f"{event.get('from')}->{event.get('to')}"
    elif event_type == EVENT_VALIDATED_SETUP:
        payload["direction"] = event.get("direction")
        payload["entry"] = round(event["entry"], 8) if event.get("entry") is not None else None
        payload["sl"] = round(event["sl"], 8) if event.get("sl") is not None else None
        payload["tp"] = round(event["tp"], 8) if event.get("tp") is not None else None
    else:
        confidence = int(event.get("confidence") or 0)
        payload["bucket"] = (confidence // 10) * 10
        if event_type == EVENT_CONFIDENCE_INCREASE:
            payload["from_bucket"] = (int(event.get("previous_confidence") or 0) // 10) * 10
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:32]


def evaluate_signal_events(
    current: dict,
    previous: Optional[dict],
    thresholds=None,
) -> Optional[dict]:
    """Return exactly one notification event (highest priority) or ``None``.

    Pure and deterministic: identical snapshots always produce the same event.
    Priority: DIRECTION_CHANGE > VALIDATED_SETUP > CONFIDENCE_INCREASE >
    NEW_HIGH_CONFIDENCE.  No event is ever produced for data-failure
    snapshots (no direction -> nothing to report).
    """
    from app.core.thresholds import get_thresholds

    th = thresholds or get_thresholds()

    if not current or current.get("status") != "OK":
        return None
    direction = current.get("direction")
    if direction not in ("LONG", "SHORT"):
        return None

    confidence = int(current.get("confidence") or 0)
    setup_status = current.get("setup_status") or "NONE"
    levels_present = (
        current.get("entry") is not None
        and current.get("sl") is not None
        and current.get("tp") is not None
    )

    prev = previous if previous and previous.get("status") == "OK" else None

    # 1. Direction change (most important event)
    if (
        th.notify_on_direction_change
        and prev
        and prev.get("direction") in ("LONG", "SHORT")
        and prev.get("direction") != direction
    ):
        return {
            "type": EVENT_DIRECTION_CHANGE,
            "symbol": current.get("symbol"),
            "timeframe": current.get("timeframe"),
            "from": prev.get("direction"),
            "to": direction,
            "direction": direction,
            "confidence": confidence,
            "confidence_label": current.get("confidence_label", ""),
            "setup_status": setup_status,
            "risk": current.get("risk", "UNKNOWN"),
        }

    # 2. New / changed validated setup
    if th.notify_on_validated_setup and setup_status == "VALIDATED" and levels_present:
        fp = current.get("fingerprint") or ""
        already_validated = (
            prev is not None
            and prev.get("setup_status") == "VALIDATED"
            and (prev.get("fingerprint") or "") == fp
        )
        if not already_validated:
            return {
                "type": EVENT_VALIDATED_SETUP,
                "symbol": current.get("symbol"),
                "timeframe": current.get("timeframe"),
                "direction": direction,
                "confidence": confidence,
                "confidence_label": current.get("confidence_label", ""),
                "setup_status": setup_status,
                "risk": current.get("risk", "UNKNOWN"),
                "entry": current.get("entry"),
                "sl": current.get("sl"),
                "tp": current.get("tp"),
                "rr": current.get("rr"),
            }

    # 3. Material confidence increase on an existing signal
    if th.notify_on_confidence_increase and prev is not None:
        previous_confidence = int(prev.get("confidence") or 0)
        delta = confidence - previous_confidence
        if delta >= th.notify_min_confidence_delta:
            return {
                "type": EVENT_CONFIDENCE_INCREASE,
                "symbol": current.get("symbol"),
                "timeframe": current.get("timeframe"),
                "direction": direction,
                "confidence": confidence,
                "previous_confidence": previous_confidence,
                "delta": delta,
                "confidence_label": current.get("confidence_label", ""),
                "setup_status": setup_status,
                "risk": current.get("risk", "UNKNOWN"),
            }

    # 4. First time crossing the configured high-confidence threshold
    if th.notify_on_high_confidence and confidence >= th.notify_min_confidence:
        if prev is None or int(prev.get("confidence") or 0) < th.notify_min_confidence:
            return {
                "type": EVENT_NEW_HIGH_CONFIDENCE,
                "symbol": current.get("symbol"),
                "timeframe": current.get("timeframe"),
                "direction": direction,
                "confidence": confidence,
                "confidence_label": current.get("confidence_label", ""),
                "setup_status": setup_status,
                "risk": current.get("risk", "UNKNOWN"),
            }

    return None


async def load_signal_state(symbol: str, timeframe: str) -> Optional[dict]:
    db = get_db()
    return await db[STATE_COLLECTION].find_one(
        {"symbol": symbol.upper(), "timeframe": timeframe}
    )


async def save_signal_state(symbol: str, timeframe: str, snapshot: dict) -> None:
    db = get_db()
    await db[STATE_COLLECTION].update_one(
        {"symbol": symbol.upper(), "timeframe": timeframe},
        {"$set": snapshot},
        upsert=True,
    )


def build_event_notification_body(event: dict) -> str:
    symbol = event.get("symbol") or ""
    symbol_display = symbol.replace("/", "")
    if len(symbol_display) > 6:
        symbol_display = symbol[:3] + "/" + symbol[3:]
    direction = event.get("direction", "")
    confidence = int(event.get("confidence") or 0)
    label = event.get("confidence_label", "")
    setup_status = event.get("setup_status", "")
    risk = event.get("risk", "UNKNOWN")

    event_type = event.get("type")
    if event_type == EVENT_DIRECTION_CHANGE:
        headline = f"{symbol_display} — Direction changed {event.get('from')} → {direction}"
    elif event_type == EVENT_VALIDATED_SETUP:
        headline = f"{symbol_display} — {direction} setup validated"
    elif event_type == EVENT_CONFIDENCE_INCREASE:
        headline = (
            f"{symbol_display} — {direction} confidence +{event.get('delta')} "
            f"→ {confidence}/100"
        )
    else:
        headline = f"{symbol_display} — {direction} {confidence}/100"

    lines = [headline, "", f"{confidence}/100 · {label}", f"Setup: {setup_status}", f"Risk: {risk}"]
    if event_type == EVENT_VALIDATED_SETUP:
        lines += [
            "",
            f"Entry: {event.get('entry')}",
            f"SL: {event.get('sl')}",
            f"TP: {event.get('tp')}",
            f"RR: 1:{float(event.get('rr') or 0):.1f}",
        ]
    return "\n".join(lines)


async def dispatch_event_notification(
    symbol: str,
    timeframe: str,
    event: dict,
    reasons: Optional[list[str]] = None,
) -> int:
    """Push a non-level (direction/confidence) event to all subscriptions."""
    fp = compute_event_fingerprint(symbol, timeframe, event)
    db = get_db()
    cursor = db[SIGNAL_COLLECTION].find({"active": True})
    subscriptions = await cursor.to_list(length=500)
    if not subscriptions:
        return 0

    body = build_event_notification_body(event)
    direction = event.get("direction", "NEUTRAL")
    confidence = int(event.get("confidence") or 0)

    sent_count = 0
    for sub in subscriptions:
        sub_id = str(sub.get("_id", sub.get("endpoint", "")))
        if await has_notified(fp, sub_id):
            continue

        payload = {
            "type": event.get("type", "SIGNAL_EVENT"),
            "signal_id": fp,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "score": confidence,
            "confidence_label": event.get("confidence_label", ""),
            "setup_status": event.get("setup_status", ""),
            "risk": event.get("risk", ""),
            "event": event.get("type"),
            "reason": " | ".join((reasons or [])[:3]) if reasons else event.get("type", ""),
            "body": body,
        }
        if event.get("type") == EVENT_VALIDATED_SETUP:
            payload["entry"] = str(event.get("entry"))
            payload["sl"] = str(event.get("sl"))
            payload["tp"] = str(event.get("tp"))
            payload["rr"] = str(event.get("rr"))

        success = await send_web_push(sub, payload)
        status = "sent" if success else "failed"
        await record_notification(fp, sub_id, event.get("type", "SIGNAL_EVENT"), symbol, direction, confidence, status)
        if success:
            sent_count += 1
            await db[SIGNAL_COLLECTION].update_one(
                {"endpoint": sub["endpoint"]},
                {"$set": {"last_success_at": datetime.utcnow()}, "$inc": {"failure_count": 0}},
            )

    return sent_count


async def record_signal_and_evaluate(
    symbol: str,
    timeframe: str,
    signal,
    reasons: Optional[list[str]] = None,
) -> Optional[dict]:
    """Persist the latest signal state and push at most one event.

    Failures in state tracking or pushing never break the analysis request.
    """
    current = signal_snapshot(symbol, timeframe, signal)

    # Data failures carry no direction: never notify, never clobber the last
    # known good state (so recovery is still comparable against it).
    if current.get("status") != "OK" or current.get("direction") not in ("LONG", "SHORT"):
        return None

    try:
        previous = await load_signal_state(symbol, timeframe)
    except Exception:
        previous = None

    event = evaluate_signal_events(current, previous)

    try:
        await save_signal_state(symbol, timeframe, current)
    except Exception as ex:
        logger.debug(f"signal state save failed: {ex}")

    if event is None:
        return None

    try:
        if event["type"] == EVENT_VALIDATED_SETUP:
            await dispatch_signal_notification(
                symbol=symbol,
                timeframe=timeframe,
                direction=event["direction"],
                entry=event["entry"],
                stop_loss=event["sl"],
                take_profit=event["tp"],
                risk_reward=event.get("rr") or 0,
                confidence=int(event["confidence"]),
                quality=event.get("confidence_label", ""),
                reasons=reasons or [],
            )
        else:
            await dispatch_event_notification(symbol, timeframe, event, reasons)
    except Exception as ex:
        logger.debug(f"signal event dispatch failed: {ex}")

    return event
