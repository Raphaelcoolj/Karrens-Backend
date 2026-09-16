import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from pymongo import ASCENDING, DESCENDING
from app.core.database import get_db

logger = logging.getLogger(__name__)

RECOMMENDATION_COLLECTION = "recommendations"

ASSET_CLASS_MAP = {
    "BTCUSD": "crypto", "ETHUSD": "crypto", "SOLUSD": "crypto",
    "EURUSD": "forex", "GBPUSD": "forex", "USDJPY": "forex",
    "AUDUSD": "forex", "USDCAD": "forex", "USDCHF": "forex",
    "NZDUSD": "forex", "EURGBP": "forex", "EURJPY": "forex",
    "XAUUSD": "commodity", "XAGUSD": "commodity",
}

FRESHNESS_TTL = {
    "1m": timedelta(minutes=5),
    "5m": timedelta(minutes=15),
    "15m": timedelta(minutes=30),
    "1H": timedelta(hours=2),
    "4H": timedelta(hours=8),
    "1D": timedelta(days=1),
    "1W": timedelta(days=3),
}


async def ensure_recommendation_indexes():
    db = get_db()
    await db[RECOMMENDATION_COLLECTION].create_index(
        [("recommendation_fingerprint", ASCENDING)], unique=True, name="idx_rec_fingerprint"
    )
    await db[RECOMMENDATION_COLLECTION].create_index(
        [("score", DESCENDING)], name="idx_rec_score"
    )
    await db[RECOMMENDATION_COLLECTION].create_index(
        [("symbol", ASCENDING), ("timeframe", ASCENDING)], name="idx_rec_symbol_tf"
    )
    await db[RECOMMENDATION_COLLECTION].create_index(
        [("status", ASCENDING)], name="idx_rec_status"
    )
    await db[RECOMMENDATION_COLLECTION].create_index(
        [("expires_at", ASCENDING)], expireAfterSeconds=0, name="idx_rec_expiry", partialFilterExpression={"expires_at": {"$type": "date"}}
    )


def compute_recommendation_fingerprint(
    symbol: str,
    timeframe: str,
    direction: str,
    trade_status: str,
    entry: Optional[float],
    sl: Optional[float],
    tp: Optional[float],
    structure_state: str = "",
) -> str:
    raw = json.dumps({
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "direction": direction,
        "trade_status": trade_status,
        "entry": round(entry, 8) if entry else None,
        "sl": round(sl, 8) if sl else None,
        "tp": round(tp, 8) if tp else None,
        "structure": structure_state,
    }, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def classify_asset(symbol: str) -> str:
    return ASSET_CLASS_MAP.get(symbol.upper(), "unknown")


def compute_multi_tf_score(htf_bias: str, middle_bias: str, ltf_confirmation: str, direction: str) -> int:
    if direction == "NEUTRAL":
        return 0

    aligned = 0
    if htf_bias == direction:
        aligned += 35
    if middle_bias == direction:
        aligned += 30
    if ltf_confirmation == direction:
        aligned += 20

    if aligned >= 70:
        aligned += 15

    return min(aligned, 100)


def compute_structure_score(
    has_bos: bool, has_choch: bool, idm_count: int, idm_swept: bool,
    ifc_count: int, fvg_count: int, ob_count: int, liquidity_sweeps: int,
    entry_scheme_found: bool,
) -> int:
    score = 0
    if has_bos:
        score += 15
    if has_choch:
        score += 12
    if idm_count > 0:
        score += 8
    if idm_swept:
        score += 15
    if ifc_count > 0:
        score += 10
    if fvg_count > 0:
        score += 5
    if ob_count > 0:
        score += 5
    if liquidity_sweeps > 0:
        score += 10
    if entry_scheme_found:
        score += 20
    return min(score, 100)


def compute_rr_score(rr: Optional[float]) -> int:
    if rr is None or rr < 1.0:
        return 0
    if rr >= 5.0:
        return 100
    if rr >= 3.0:
        return 80
    if rr >= 2.0:
        return 60
    return 40


def compute_freshness_penalty(last_analysis: Optional[datetime], timeframe: str) -> float:
    if last_analysis is None:
        return 0.5
    ttl = FRESHNESS_TTL.get(timeframe, timedelta(hours=2))
    age = datetime.utcnow() - last_analysis
    if age < ttl * 0.5:
        return 1.0
    if age < ttl:
        return 0.8
    if age < ttl * 2:
        return 0.5
    return 0.2


def compute_setup_completeness(
    has_htf_bias: bool, has_bos: bool, has_choch: bool, has_idm: bool,
    has_ifc: bool, has_entry: bool, has_rr: bool,
) -> int:
    components = [has_htf_bias, has_bos or has_choch, has_idm, has_ifc, has_entry, has_rr]
    present = sum(components)
    return int((present / len(components)) * 100)


def compute_recommendation_score(
    trade_status: str,
    direction: str,
    assessment_score: int,
    htf_bias: str,
    middle_bias: str,
    ltf_confirmation: str,
    has_bos: bool,
    has_choch: bool,
    idm_count: int,
    idm_swept: bool,
    ifc_count: int,
    fvg_count: int,
    ob_count: int,
    liquidity_sweeps: int,
    entry_scheme_found: bool,
    rr: Optional[float],
    last_analysis: Optional[datetime],
    timeframe: str,
    has_entry: bool,
) -> int:
    if direction == "NEUTRAL" and trade_status in ("NO_SETUP", "INSUFFICIENT_DATA"):
        return 0

    tf_score = compute_multi_tf_score(htf_bias, middle_bias, ltf_confirmation, direction)
    struct_score = compute_structure_score(
        has_bos, has_choch, idm_count, idm_swept,
        ifc_count, fvg_count, ob_count, liquidity_sweeps, entry_scheme_found,
    )
    rr_sc = compute_rr_score(rr) if has_entry else 0
    completeness = compute_setup_completeness(
        direction != "NEUTRAL", has_bos, has_choch, idm_count > 0,
        ifc_count > 0, has_entry, rr is not None and rr >= 1.0,
    )
    freshness = compute_freshness_penalty(last_analysis, timeframe)

    raw = (
        tf_score * 0.30
        + struct_score * 0.25
        + rr_sc * 0.15
        + completeness * 0.15
        + assessment_score * 0.15
    )
    final = int(raw * freshness)
    return min(max(final, 0), 100)


def classify_quality(score: int) -> str:
    if score >= 80:
        return "EXTREME CONVICTION"
    if score >= 65:
        return "HIGH CONVICTION"
    if score >= 50:
        return "MODERATE"
    if score >= 35:
        return "FAVOURED"
    return "LOW"


def determine_recommendation_status(
    trade_status: str,
    direction: str,
    has_entry: bool,
    score: int,
) -> str:
    if trade_status == "VALIDATED" and has_entry and direction in ("LONG", "SHORT"):
        return "VALIDATED"
    if trade_status == "INVALIDATED":
        return "INVALIDATED"
    if trade_status in ("WAITING_FOR_CONFIRMATION", "VALIDATED") and direction in ("LONG", "SHORT") and not has_entry:
        return "WAITING_FOR_CONFIRMATION"
    if direction in ("LONG", "SHORT") and score >= 20:
        return "WATCH"
    return "WATCH"


def generate_reasons(
    direction: str,
    htf_bias: str,
    middle_bias: str,
    ltf_confirmation: str,
    has_bos: bool,
    has_choch: bool,
    idm_count: int,
    idm_swept: bool,
    ifc_count: int,
    entry_scheme: str,
    trade_status: str,
    has_entry: bool,
) -> list[str]:
    reasons = []
    if htf_bias == direction:
        reasons.append(f"HTF {htf_bias.lower()} structure")
    elif htf_bias != "NEUTRAL":
        reasons.append(f"HTF bias {htf_bias.lower()} (conflicting)")
    if middle_bias == direction:
        reasons.append(f"Middle-TF {middle_bias.lower()} structure")
    if ltf_confirmation == direction:
        reasons.append("LTF confirmation present")
    elif direction in ("LONG", "SHORT"):
        reasons.append("LTF confirmation pending")
    if has_bos:
        reasons.append("BOS detected")
    if has_choch:
        reasons.append("CHoCH confirmed")
    if idm_count > 0:
        if idm_swept:
            reasons.append("IDM liquidity swept")
        else:
            reasons.append(f"{idm_count} IDM(s) pending sweep")
    if ifc_count > 0:
        reasons.append("IFC confirmation present")
    if entry_scheme:
        reasons.append(f"Entry scheme {entry_scheme}")
    if trade_status == "VALIDATED" and has_entry:
        reasons.append("Entry validated")
    elif trade_status == "WAITING_FOR_CONFIRMATION":
        reasons.append("Awaiting entry confirmation")
    return reasons[:10]


def generate_negative_factors(
    htf_bias: str,
    middle_bias: str,
    ltf_confirmation: str,
    direction: str,
    has_bos: bool,
    has_choch: bool,
    idm_swept: bool,
    ifc_count: int,
    rr: Optional[float],
    has_entry: bool,
    trade_status: str,
) -> list[str]:
    negatives = []
    if direction != "NEUTRAL" and htf_bias != direction and htf_bias != "NEUTRAL":
        negatives.append("HTF/Middle timeframe disagreement")
    if direction != "NEUTRAL" and middle_bias != direction and middle_bias != "NEUTRAL":
        negatives.append("Middle-TF structure conflicting")
    if direction != "NEUTRAL" and ltf_confirmation != direction:
        negatives.append("LTF confirmation missing")
    if not has_bos and not has_choch:
        negatives.append("No confirmed BOS/CHoCH")
    if not idm_swept:
        negatives.append("IDM not swept")
    if ifc_count == 0:
        negatives.append("No IFC confirmation")
    if rr is not None and rr < 1.0:
        negatives.append("Invalid risk/reward")
    if not has_entry:
        negatives.append("No validated entry")
    if trade_status == "WAITING_FOR_CONFIRMATION":
        negatives.append("Awaiting confirmation")
    return negatives[:6]


def determine_ltf_confirmation(
    ltf_choch: int, ltf_idm: int, ltf_sweep: int, direction: str,
) -> str:
    if ltf_choch > 0 or (ltf_idm > 0 and ltf_sweep > 0):
        return direction
    return "NONE"


def upsert_recommendation(rec_data: dict) -> None:
    db = get_db()
    fp = rec_data.get("recommendation_fingerprint", "")
    now = datetime.utcnow()

    existing = db[RECOMMENDATION_COLLECTION].find_one({"recommendation_fingerprint": fp})
    if existing:
        update_fields = {k: v for k, v in rec_data.items() if k != "_id"}
        update_fields["updated_at"] = now
        db[RECOMMENDATION_COLLECTION].update_one(
            {"_id": existing["_id"]}, {"$set": update_fields}
        )
    else:
        rec_data["created_at"] = now
        rec_data["updated_at"] = now
        db[RECOMMENDATION_COLLECTION].insert_one(rec_data)


def get_recommendations(
    limit: int = 20,
    asset_class: Optional[str] = None,
    timeframe: Optional[str] = None,
    status: Optional[str] = None,
    direction: Optional[str] = None,
) -> list[dict]:
    db = get_db()
    query: dict = {}
    if asset_class:
        query["asset_class"] = asset_class
    if timeframe:
        query["timeframe"] = timeframe
    if status:
        query["status"] = status
    if direction:
        query["direction"] = direction

    cursor = db[RECOMMENDATION_COLLECTION].find(query).sort("score", DESCENDING).limit(limit)
    return list(cursor)


def get_top_recommendation() -> Optional[dict]:
    db = get_db()
    return db[RECOMMENDATION_COLLECTION].find_one(
        {"status": {"$in": ["VALIDATED", "WAITING_FOR_CONFIRMATION", "WATCH"]}},
        sort=[("score", DESCENDING)],
    )


def delete_recommendation(fingerprint: str) -> None:
    db = get_db()
    db[RECOMMENDATION_COLLECTION].delete_one({"recommendation_fingerprint": fingerprint})
