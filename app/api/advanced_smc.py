import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.strategies.advanced_smc import AdvancedSMCStrategy, AdvancedSMCConfig, Candle
from app.strategies.advanced_smc.scoring import calculate_assessment_score
from app.services.market_data import MarketDataService
from app.services.notification_service import dispatch_signal_notification
from app.services.recommendation_engine import (
    compute_recommendation_fingerprint,
    compute_recommendation_score,
    classify_quality,
    classify_asset,
    determine_recommendation_status,
    generate_reasons,
    generate_negative_factors,
    determine_ltf_confirmation,
    upsert_recommendation,
    FRESHNESS_TTL,
)

router = APIRouter(prefix="/api/analysis/advanced-smc", tags=["advanced-smc"])
market_service = MarketDataService()


class AdvancedSMCRequest(BaseModel):
    symbol: str
    htf: str = "1D"
    middle_tf: str = "15m"
    ltf: str = "1m"
    exit_mode: str = "CONSERVATIVE"


class StructureInfo(BaseModel):
    state: str = ""
    bos: list[dict] = []
    choch: list[dict] = []
    idm: list[dict] = []


class LiquidityInfo(BaseModel):
    levels_detected: int = 0
    levels_swept: int = 0
    sweep: Optional[str] = None


class POIInfo(BaseModel):
    type: str = ""
    zone: Optional[dict] = None


class EntryInfo(BaseModel):
    type: str = ""
    scheme: str = ""
    low: Optional[float] = None
    high: Optional[float] = None


class RiskInfo(BaseModel):
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = None


class MarketAssessmentInfo(BaseModel):
    direction: str = "NEUTRAL"
    score: int = 50
    opposing_score: int = 50
    label: str = "BALANCED"
    quality: str = "MODERATE"
    rationale: list[str] = []


class TradeStatusInfo(BaseModel):
    status: str = "NO_SETUP"
    direction: str = "NEUTRAL"
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = None
    confidence_score: Optional[int] = None
    risk_label: str = "UNKNOWN"
    entry_type: Optional[str] = None
    entry_scheme: Optional[str] = None
    reason_code: Optional[str] = None
    reason: str = ""


class DiagnosticsInfo(BaseModel):
    data_valid: bool = False
    candle_count: int = 0
    requested_timeframe: str = ""
    htf_timeframe: str = ""
    middle_timeframe: str = ""
    ltf_timeframe: str = ""
    htf_candle_count: int = 0
    middle_candle_count: int = 0
    ltf_candle_count: int = 0
    htf_bias: str = "NEUTRAL"
    middle_bias: str = "NEUTRAL"
    swing_high_count: int = 0
    swing_low_count: int = 0
    bos_count: int = 0
    choch_count: int = 0
    idm_count: int = 0
    liquidity_level_count: int = 0
    liquidity_sweep_count: int = 0
    fvg_count: int = 0
    order_block_count: int = 0
    ifc_count: int = 0
    entry_candidates: int = 0
    rejection_reasons: list[str] = []


class AdvancedSMCResponse(BaseModel):
    symbol: str
    strategy: str
    timestamp: str
    bias: str
    signal: str
    confidence: float
    assessment: MarketAssessmentInfo
    trade_status: TradeStatusInfo
    diagnostics: DiagnosticsInfo
    structure: StructureInfo
    liquidity: LiquidityInfo
    poi: POIInfo
    entry: EntryInfo
    risk: RiskInfo
    reasons: list[str]
    invalidation_conditions: list[str]
    current_price: Optional[float] = None


INTERVAL_MAP = {
    "1D": "1day", "4H": "4h", "1H": "1h",
    "1W": "1week", "15m": "15min", "1m": "1min", "5m": "5min",
}


async def _fetch_candles(symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
    td_interval = INTERVAL_MAP.get(timeframe, timeframe)
    snapshot = await market_service.get_full_market_data(symbol, td_interval, limit)
    return [
        Candle(
            timestamp=c.timestamp, open=c.open, high=c.high,
            low=c.low, close=c.close, volume=c.volume,
        )
        for c in snapshot.candles
    ]


@router.post("", response_model=AdvancedSMCResponse)
async def analyze_advanced_smc(req: AdvancedSMCRequest):
    try:
        config = AdvancedSMCConfig(
            htf=req.htf,
            middle_tf=req.middle_tf,
            ltf=req.ltf,
            exit_mode=req.exit_mode,
        )

        if not config.is_valid_combo():
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe combination: {req.htf}/{req.middle_tf}/{req.ltf}",
            )

        symbol = req.symbol.upper()

        htf_candles, middle_candles, ltf_candles = await asyncio.gather(
            _fetch_candles(symbol, config.htf, 200),
            _fetch_candles(symbol, config.middle_tf, 200),
            _fetch_candles(symbol, config.ltf, 200),
        )

        if not middle_candles:
            raise HTTPException(status_code=404, detail=f"No candle data for {symbol} at {config.middle_tf}")

        strategy = AdvancedSMCStrategy(config)
        result = strategy.analyze(htf_candles, middle_candles, ltf_candles)
        result.symbol = symbol

        current_price = middle_candles[-1].close if middle_candles else 0

        bias = result.market_bias
        has_bos = len(result.bos_events) > 0
        has_choch = len(result.choch_events) > 0
        idm_count = len(result.idm_events)
        idm_swept_count = sum(1 for i in result.idm_events if i.swept)
        ifc_count = len(result.ifcs)
        ob_count = len(result.order_blocks)
        fvg_count = len(result.fvgs)
        sweep_count = len(result.liquidity_sweeps)

        direction_for_assessment = result.direction if result.direction != "NO_SIGNAL" else bias

        assessment_score, opposing_score, label, quality = calculate_assessment_score(
            bias=bias,
            has_bos=has_bos,
            has_choch=has_choch,
            idm_count=idm_count,
            idm_swept_count=idm_swept_count,
            ifc_count=ifc_count,
            ob_count=ob_count,
            fvg_count=fvg_count,
            liquidity_sweep_count=sweep_count,
            entry_scheme_found=result.entry_scheme != "",
        )

        if result.direction == "NO_SIGNAL":
            reasons_str = " | ".join(result.reasons) if result.reasons else ""
            has_insufficient = any(
                r.startswith("Insufficient") or "data" in r.lower()
                for r in result.reasons
            )
            has_atr_zero = any("ATR is zero" in r for r in result.reasons)
            has_invalid_config = any("Invalid timeframe" in r for r in result.reasons)

            if has_insufficient or has_atr_zero or has_invalid_config:
                trade_status = "INSUFFICIENT_DATA"
                trade_direction = "NEUTRAL"
                reason_code = result.reasons[0] if result.reasons else "INSUFFICIENT_DATA"
                reason = reasons_str or "Insufficient or invalid market data for analysis."
            elif bias == "NEUTRAL":
                trade_status = "NO_SETUP"
                trade_direction = "NEUTRAL"
                reason_code = "NO_STRUCTURE"
                reason = "Market structure is currently balanced with no dominant directional bias."
            else:
                trade_status = "WAITING_FOR_CONFIRMATION"
                trade_direction = bias
                reason_code = result.reasons[0] if result.reasons else "NO_ENTRY_SCHEME"
                reason = reasons_str or "Directional bias detected, waiting for entry confirmation."
        else:
            has_entry = result.entry_low is not None and result.stop_loss is not None
            if has_entry:
                trade_status = "VALIDATED"
                trade_direction = result.direction
                reason_code = None
                reason = " | ".join(result.reasons) if result.reasons else "Entry validated."
            else:
                trade_status = "WAITING_FOR_CONFIRMATION"
                trade_direction = result.direction
                reason_code = result.reasons[0] if result.reasons else "NO_ENTRY_SCHEME"
                reason = " | ".join(result.reasons) if result.reasons else "Directional bias detected, waiting for entry setup."

        if trade_status == "VALIDATED":
            risk_label = _classify_risk(
                result.risk_reward, result.confidence, has_bos, has_choch,
                idm_swept_count > 0, ifc_count > 0,
            )
        else:
            risk_label = "N/A"

        bos_list = [
            {"direction": e.direction, "price": e.price, "index": e.index, "swept": e.swept}
            for e in result.bos_events
        ]
        choch_list = [
            {"direction": e.direction, "price": e.price, "index": e.index, "swept": e.swept}
            for e in result.choch_events
        ]
        idm_list = [
            {"price": i.price, "direction": i.direction, "swept": i.swept, "index": i.index}
            for i in result.idm_events
        ]

        swept = [l for l in result.liquidity_levels if l.swept]
        sweep_dir = None
        if swept:
            last = swept[-1]
            if last.type in ("EQUAL_LOW", "PDL", "ASIAN_LOW", "LONDON_LOW", "NY_LOW", "SWING_LOW"):
                sweep_dir = "BULLISH"
            elif last.type in ("EQUAL_HIGH", "PDH", "ASIAN_HIGH", "LONDON_HIGH", "NY_HIGH", "SWING_HIGH"):
                sweep_dir = "BEARISH"

        poi_zone = None
        if result.poi_zone:
            poi_zone = {
                "type": result.poi_zone.type,
                "high": result.poi_zone.high,
                "low": result.poi_zone.low,
                "reason": result.poi_zone.reason,
            }

        swings = strategy._determine_bias(result.middle_labels) if hasattr(strategy, '_determine_bias') else "NEUTRAL"

        response = AdvancedSMCResponse(
            symbol=result.symbol,
            strategy="advanced_smc",
            timestamp=datetime.utcnow().isoformat(),
            bias=result.market_bias,
            signal=trade_direction if trade_status != "INSUFFICIENT_DATA" else "NEUTRAL",
            confidence=result.confidence,
            assessment=MarketAssessmentInfo(
                direction=direction_for_assessment if direction_for_assessment != "NO_SIGNAL" else "NEUTRAL",
                score=assessment_score,
                opposing_score=opposing_score,
                label=label,
                quality=quality,
                rationale=result.reasons[:5] if result.reasons else [],
            ),
            trade_status=TradeStatusInfo(
                status=trade_status,
                direction=trade_direction,
                entry=result.entry_low,
                stop_loss=result.stop_loss,
                take_profit_1=result.take_profit_1,
                take_profit_2=result.take_profit_2,
                take_profit_3=result.take_profit_3,
                risk_reward=result.risk_reward,
                confidence_score=int(result.confidence) if result.confidence > 0 else None,
                risk_label=risk_label,
                entry_type=result.entry_type,
                entry_scheme=result.entry_scheme,
                reason_code=reason_code,
                reason=reason,
            ),
            diagnostics=DiagnosticsInfo(
                data_valid=True,
                candle_count=len(middle_candles),
                requested_timeframe=config.middle_tf,
                htf_timeframe=config.htf,
                middle_timeframe=config.middle_tf,
                ltf_timeframe=config.ltf,
                htf_candle_count=len(htf_candles),
                middle_candle_count=len(middle_candles),
                ltf_candle_count=len(ltf_candles),
                htf_bias=result.htf_bias,
                middle_bias=bias,
                swing_high_count=sum(1 for l in result.middle_labels if l.type in ("HH", "LH")),
                swing_low_count=sum(1 for l in result.middle_labels if l.type in ("HL", "LL")),
                bos_count=len(result.bos_events),
                choch_count=len(result.choch_events),
                idm_count=idm_count,
                liquidity_level_count=len(result.liquidity_levels),
                liquidity_sweep_count=sweep_count,
                fvg_count=fvg_count,
                order_block_count=ob_count,
                ifc_count=ifc_count,
                entry_candidates=1 if result.entry_scheme else 0,
                rejection_reasons=result.reasons if result.direction == "NO_SIGNAL" else [],
            ),
            structure=StructureInfo(
                state=result.structure_state,
                bos=bos_list,
                choch=choch_list,
                idm=idm_list,
            ),
            liquidity=LiquidityInfo(
                levels_detected=len(result.liquidity_levels),
                levels_swept=len(swept),
                sweep=sweep_dir,
            ),
            poi=POIInfo(type=result.poi_type, zone=poi_zone),
            entry=EntryInfo(
                type=result.entry_type,
                scheme=result.entry_scheme,
                low=result.entry_low,
                high=result.entry_high,
            ),
            risk=RiskInfo(
                stop_loss=result.stop_loss,
                take_profit_1=result.take_profit_1,
                take_profit_2=result.take_profit_2,
                take_profit_3=result.take_profit_3,
                risk_reward=result.risk_reward,
            ),
            reasons=result.reasons,
            invalidation_conditions=result.invalidation_conditions,
            current_price=current_price,
        )

        if trade_status == "VALIDATED" and result.entry_low and result.stop_loss and result.take_profit_1:
            try:
                await dispatch_signal_notification(
                    symbol=symbol,
                    timeframe=config.middle_tf,
                    direction=trade_direction,
                    entry=result.entry_low,
                    stop_loss=result.stop_loss,
                    take_profit=result.take_profit_1,
                    risk_reward=result.risk_reward or 0,
                    confidence=int(result.confidence),
                    quality=quality,
                    reasons=result.reasons,
                )
            except Exception:
                pass

        ltf_conf = determine_ltf_confirmation(
            result.ltf_choch_count if hasattr(result, 'ltf_choch_count') else 0,
            result.ltf_idm_count if hasattr(result, 'ltf_idm_count') else 0,
            result.ltf_sweep_count if hasattr(result, 'ltf_sweep_count') else 0,
            trade_direction,
        )

        rec_score = compute_recommendation_score(
            trade_status=trade_status,
            direction=trade_direction,
            assessment_score=assessment_score,
            htf_bias=result.htf_bias,
            middle_bias=bias,
            ltf_confirmation=ltf_conf,
            has_bos=has_bos,
            has_choch=has_choch,
            idm_count=idm_count,
            idm_swept=idm_swept_count > 0,
            ifc_count=ifc_count,
            fvg_count=fvg_count,
            ob_count=ob_count,
            liquidity_sweeps=sweep_count,
            entry_scheme_found=bool(result.entry_scheme),
            rr=result.risk_reward,
            last_analysis=datetime.utcnow(),
            timeframe=config.middle_tf,
            has_entry=result.entry_low is not None,
        )

        rec_status = determine_recommendation_status(trade_status, trade_direction, result.entry_low is not None, rec_score)
        rec_quality = classify_quality(rec_score)
        rec_reasons = generate_reasons(
            trade_direction, result.htf_bias, bias, ltf_conf,
            has_bos, has_choch, idm_count, idm_swept_count > 0, ifc_count,
            result.entry_scheme, trade_status, result.entry_low is not None,
        )
        rec_negatives = generate_negative_factors(
            result.htf_bias, bias, ltf_conf, trade_direction,
            has_bos, has_choch, idm_swept_count > 0, ifc_count,
            result.risk_reward, result.entry_low is not None, trade_status,
        )

        fp = compute_recommendation_fingerprint(
            symbol, config.middle_tf, trade_direction, trade_status,
            result.entry_low, result.stop_loss, result.take_profit_1,
            result.structure_state,
        )

        ttl = FRESHNESS_TTL.get(config.middle_tf, FRESHNESS_TTL["4H"])

        rec_doc = {
            "symbol": symbol,
            "asset_class": classify_asset(symbol),
            "timeframe": config.middle_tf,
            "direction": trade_direction,
            "score": rec_score,
            "quality": rec_quality,
            "status": rec_status,
            "trade_status": trade_status,
            "entry": result.entry_low,
            "sl": result.stop_loss,
            "tp": result.take_profit_1,
            "rr": result.risk_reward,
            "strategy": "advanced_smc",
            "reasons": rec_reasons,
            "negative_factors": rec_negatives,
            "confirmation_state": trade_status,
            "structure_summary": result.structure_state,
            "liquidity_summary": f"{sweep_count} sweeps of {len(result.liquidity_levels)} levels",
            "poi_summary": result.poi_type or "None detected",
            "htf_bias": result.htf_bias,
            "middle_bias": bias,
            "ltf_confirmation": ltf_conf,
            "bos_count": len(result.bos_events),
            "choch_count": len(result.choch_events),
            "idm_count": idm_count,
            "idm_swept_count": idm_swept_count,
            "ifc_count": ifc_count,
            "fvg_count": fvg_count,
            "ob_count": ob_count,
            "liquidity_sweep_count": sweep_count,
            "recommendation_fingerprint": fp,
            "last_analysis_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + ttl,
        }

        try:
            upsert_recommendation(rec_doc)
        except Exception:
            pass

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


def _classify_risk(
    rr: float | None,
    confidence: float,
    has_bos: bool,
    has_choch: bool,
    idm_swept: bool,
    ifc_confirms: bool,
) -> str:
    risk_score = 0

    if rr is not None:
        if rr >= 5.0:
            risk_score += 0
        elif rr >= 3.0:
            risk_score += 1
        elif rr >= 2.0:
            risk_score += 2
        else:
            risk_score += 3
    else:
        risk_score += 2

    if confidence >= 70:
        risk_score += 0
    elif confidence >= 50:
        risk_score += 1
    else:
        risk_score += 2

    confirmations = sum([has_bos, has_choch, idm_swept, ifc_confirms])
    if confirmations >= 3:
        risk_score += 0
    elif confirmations >= 2:
        risk_score += 1
    else:
        risk_score += 2

    if risk_score <= 1:
        return "LOW RISK"
    elif risk_score <= 3:
        return "MODERATE RISK"
    elif risk_score <= 5:
        return "HIGH RISK"
    else:
        return "EXTREME RISK"
