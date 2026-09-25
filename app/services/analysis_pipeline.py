import time
import logging
from typing import Optional
from app.services.market_data import MarketDataService
from app.analysis.engine import analyze_market
from app.services.ai_provider import AIProviderService, parse_ai_signal_response
from app.services.prompts import SIGNAL_SYSTEM_PROMPT, build_analysis_prompt
from app.models.signal import Signal, Direction, AnalysisResult
from app.core.database import get_db
from app.models.strategy import StrategyRules
from app.strategies.advanced_smc import AdvancedSMCStrategy, AdvancedSMCConfig, Candle
from app.services.signal_engine import (
    generate_directional_signal,
    STATUS_OK,
    STATUS_MARKET_DATA_UNAVAILABLE,
    STATUS_UPSTREAM_RATE_LIMITED,
    STATUS_INVALID_SYMBOL,
    STATUS_ANALYSIS_ERROR,
)

logger = logging.getLogger(__name__)

market_data_service = MarketDataService()
ai_service = AIProviderService()

_TIMEFRAME_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400,
    "1d": 86400, "1w": 604800,
}


def validate_signal(signal_data: dict, current_price: float) -> dict:
    direction = signal_data.get("direction", "NO SIGNAL")
    if direction == "NO SIGNAL" or direction not in ("LONG", "SHORT"):
        return {
            "valid": False,
            "direction": "NO SIGNAL",
            "confidence": 0,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": None,
            "reasoning": signal_data.get("reasoning", "Insufficient evidence for a signal."),
            "triggered_conditions": signal_data.get("triggered_conditions", []),
            "invalidating_conditions": signal_data.get("invalidating_conditions", []),
            "strategy_alignment": signal_data.get("strategy_alignment"),
            "market_context": signal_data.get("market_context", ""),
        }

    entry = signal_data.get("entry")
    stop_loss = signal_data.get("stop_loss")
    take_profit = signal_data.get("take_profit")

    if entry is None or stop_loss is None or take_profit is None:
        return {
            "valid": False,
            "direction": "NO SIGNAL",
            "confidence": 0,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": None,
            "reasoning": "Missing entry, stop loss, or take profit levels.",
            "triggered_conditions": [],
            "invalidating_conditions": ["Incomplete signal levels"],
            "strategy_alignment": None,
            "market_context": "",
        }

    try:
        entry = float(entry)
        stop_loss = float(stop_loss)
        take_profit = float(take_profit)
    except (ValueError, TypeError):
        return {
            "valid": False,
            "direction": "NO SIGNAL",
            "confidence": 0,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": None,
            "reasoning": "Invalid price format provided.",
            "triggered_conditions": [],
            "invalidating_conditions": ["Invalid price format"],
            "strategy_alignment": None,
            "market_context": "",
        }

    if direction == "LONG":
        if stop_loss >= entry:
            return {
                "valid": False,
                "direction": "NO SIGNAL",
                "confidence": 0,
                "entry": None,
                "stop_loss": None,
                "take_profit": None,
                "risk_reward": None,
                "reasoning": "Invalid signal: Stop loss must be below entry for LONG.",
                "triggered_conditions": [],
                "invalidating_conditions": ["Invalid stop loss placement"],
                "strategy_alignment": None,
                "market_context": "",
            }
        if take_profit <= entry:
            return {
                "valid": False,
                "direction": "NO SIGNAL",
                "confidence": 0,
                "entry": None,
                "stop_loss": None,
                "take_profit": None,
                "risk_reward": None,
                "reasoning": "Invalid signal: Take profit must be above entry for LONG.",
                "triggered_conditions": [],
                "invalidating_conditions": ["Invalid take profit placement"],
                "strategy_alignment": None,
                "market_context": "",
            }
        risk = entry - stop_loss
        reward = take_profit - entry
    else:
        if stop_loss <= entry:
            return {
                "valid": False,
                "direction": "NO SIGNAL",
                "confidence": 0,
                "entry": None,
                "stop_loss": None,
                "take_profit": None,
                "risk_reward": None,
                "reasoning": "Invalid signal: Stop loss must be above entry for SHORT.",
                "triggered_conditions": [],
                "invalidating_conditions": ["Invalid stop loss placement"],
                "strategy_alignment": None,
                "market_context": "",
            }
        if take_profit >= entry:
            return {
                "valid": False,
                "direction": "NO SIGNAL",
                "confidence": 0,
                "entry": None,
                "stop_loss": None,
                "take_profit": None,
                "risk_reward": None,
                "reasoning": "Invalid signal: Take profit must be below entry for SHORT.",
                "triggered_conditions": [],
                "invalidating_conditions": ["Invalid take profit placement"],
                "strategy_alignment": None,
                "market_context": "",
            }
        risk = stop_loss - entry
        reward = entry - take_profit

    if risk <= 0 or reward <= 0:
        return {
            "valid": False,
            "direction": "NO SIGNAL",
            "confidence": 0,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": None,
            "reasoning": "Invalid risk/reward calculation.",
            "triggered_conditions": [],
            "invalidating_conditions": ["Invalid R:R"],
            "strategy_alignment": None,
            "market_context": "",
        }

    rr = round(reward / risk, 2)
    confidence = min(int(signal_data.get("confidence", 50)), 100)

    if rr < 1.5 and confidence >= 50:
        confidence = max(confidence - 20, 0)

    return {
        "valid": True,
        "direction": direction,
        "confidence": confidence,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward": rr,
        "reasoning": signal_data.get("reasoning", ""),
        "triggered_conditions": signal_data.get("triggered_conditions", []),
        "invalidating_conditions": signal_data.get("invalidating_conditions", []),
        "strategy_alignment": signal_data.get("strategy_alignment"),
        "market_context": signal_data.get("market_context", ""),
    }


def _classify_market_data_error(exc: Exception) -> tuple[str, str]:
    """Map an upstream failure to an explicit non-signal status (no fabrication)."""
    try:
        import httpx
    except Exception:  # pragma: no cover
        httpx = None

    if httpx is not None:
        if isinstance(exc, httpx.HTTPStatusError):
            code = getattr(getattr(exc, "response", None), "status_code", 0)
            if code == 429:
                return STATUS_UPSTREAM_RATE_LIMITED, "Market data provider rate limited the request."
            if 400 <= code < 500:
                return STATUS_INVALID_SYMBOL, "Symbol could not be resolved by the data provider."
            return STATUS_MARKET_DATA_UNAVAILABLE, "Market data provider returned a server error."
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
            return STATUS_MARKET_DATA_UNAVAILABLE, "Market data provider could not be reached."

    if isinstance(exc, ValueError) and "No candle data" in str(exc):
        return STATUS_MARKET_DATA_UNAVAILABLE, str(exc)
    return STATUS_MARKET_DATA_UNAVAILABLE, f"Market data unavailable: {str(exc)[:120]}"


def _is_stale(candles: list, timeframe: str) -> bool:
    if not candles:
        return True
    seconds = _TIMEFRAME_SECONDS.get((timeframe or "").lower())
    if not seconds:
        return False
    try:
        age = (time.time() - candles[-1].timestamp.timestamp())
    except Exception:
        return False
    return age > seconds * 3


async def _ai_narrative(
    pair: str,
    timeframe: str,
    technical_analysis: dict,
    strategy_context: Optional[dict],
    strategy_rules: Optional[dict],
) -> tuple[str, Optional[str]]:
    """Ask the LLM for narrative text only.

    The model never chooses the direction and never proposes trade levels -
    it can only comment on the deterministic analysis.
    """
    try:
        prompt = build_analysis_prompt(
            pair=pair,
            timeframe=timeframe,
            technical_analysis=technical_analysis,
            strategy_context=strategy_context,
            strategy_rules=strategy_rules,
        )
        ai_result = await ai_service.generate(
            system_prompt=SIGNAL_SYSTEM_PROMPT,
            user_prompt=prompt,
        )
    except Exception as exc:
        logger.error(f"AI generation failed: {exc}")
        return "", None

    if not ai_result.get("success"):
        logger.error(f"AI generation failed: {ai_result.get('error')}")
        return "", ai_result.get("provider")

    try:
        parsed = parse_ai_signal_response(ai_result["response"])
        return (parsed.get("reasoning") or "").strip(), ai_result.get("provider")
    except Exception as exc:
        logger.error(f"AI response parse failed: {exc}")
        return "", ai_result.get("provider")


async def run_analysis(
    pair: str,
    timeframe: str,
    strategy_id: Optional[str] = None,
) -> AnalysisResult:
    """Produce Karren's deterministic signal for one pair/timeframe.

    Direction, confidence, setup status, risk and trade levels all come from
    the candle analysis (Advanced SMC + technical analysis + signal engine).
    The AI provider is consulted only for narrative text; if it is down the
    signal is still returned.
    """
    start_time = time.time()

    status = STATUS_OK
    detail = ""
    snapshot = None
    candles: list[Candle] = []
    technical_analysis: dict = {}

    try:
        snapshot = await market_data_service.get_full_market_data(pair, timeframe)
    except Exception as exc:
        status, detail = _classify_market_data_error(exc)
        logger.warning(f"market data failure for {pair} {timeframe}: {detail}")

    if snapshot is not None:
        candles = [
            Candle(
                timestamp=c.timestamp, open=c.open, high=c.high,
                low=c.low, close=c.close, volume=c.volume,
            )
            for c in snapshot.candles
        ]
        if not candles:
            status = STATUS_MARKET_DATA_UNAVAILABLE
            detail = f"No candle data returned for {pair} at {timeframe}"

    if status == STATUS_OK and candles:
        try:
            technical_analysis = analyze_market(
                [
                    {
                        "timestamp": c.timestamp,
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                    }
                    for c in candles
                ]
            )
        except Exception:
            technical_analysis = {}

    strategy_context = None
    strategy_rules = None
    if strategy_id:
        try:
            db = get_db()
            rules_doc = await db.strategy_rules.find_one({"strategy_id": strategy_id})
            if rules_doc:
                strategy_rules = {k: v for k, v in rules_doc.items() if k != "_id" and k != "strategy_id"}
                strategy_context = {"rules": strategy_rules}
        except Exception:
            strategy_context = None

    # --- Deterministic signal -------------------------------------------
    setup = None
    if status == STATUS_OK and candles:
        try:
            smc_config = AdvancedSMCConfig()
            smc_strategy = AdvancedSMCStrategy(smc_config)
            # Single-timeframe request: there is no distinct HTF/LTF data, so
            # the HTF bias is neutralised afterwards instead of being faked
            # from a duplicate of the middle timeframe.
            setup = smc_strategy.analyze(htf_candles=candles, middle_candles=candles)
            setup.symbol = pair
            setup.htf_bias = "NEUTRAL"
            setup.htf_labels = []
        except Exception as exc:
            logger.error(f"SMC analysis failed for {pair}: {exc}")
            setup = None

    if status != STATUS_OK:
        directional = generate_directional_signal(status=status)
    else:
        min_candles = getattr(AdvancedSMCConfig(), "swing_left", 2) + getattr(AdvancedSMCConfig(), "swing_right", 2) + 10
        directional = generate_directional_signal(
            setup=setup,
            technical_analysis=technical_analysis,
            data_quality_ok=len(candles) >= min_candles,
            freshness_degraded=_is_stale(candles, timeframe),
        )

    # --- Narrative (non-fatal) ------------------------------------------
    ai_reasoning = ""
    model_provider = None
    if directional.status == STATUS_OK:
        ai_reasoning, model_provider = await _ai_narrative(
            pair, timeframe, technical_analysis, strategy_context, strategy_rules
        )

    # --- Trade levels: only from a fully validated canonical setup -------
    entry = stop_loss = take_profit = risk_reward = None
    current_price = technical_analysis.get("current_price") or 0
    if directional.status == STATUS_OK and directional.setup_status == "VALIDATED":
        if None not in (directional.entry, directional.sl, directional.tp):
            validated = validate_signal(
                {
                    "direction": directional.direction,
                    "entry": directional.entry,
                    "stop_loss": directional.sl,
                    "take_profit": directional.tp,
                    "confidence": directional.confidence,
                    "reasoning": "",
                },
                current_price,
            )
            if validated["valid"]:
                entry = validated["entry"]
                stop_loss = validated["stop_loss"]
                take_profit = validated["take_profit"]
                risk_reward = validated["risk_reward"]
            else:
                logger.warning(f"{pair}: validated setup failed level geometry check, levels dropped")

    if directional.status == STATUS_OK and directional.direction in ("LONG", "SHORT"):
        direction = Direction(directional.direction)
    else:
        direction = Direction.NO_SIGNAL

    reasons_text = " | ".join(directional.reasons) if directional.reasons else ""
    if directional.status != STATUS_OK:
        reasoning = reasons_text or f"Signal unavailable: {directional.status}"
    elif ai_reasoning:
        reasoning = f"{reasons_text} | AI view: {ai_reasoning}" if reasons_text else ai_reasoning
    else:
        reasoning = reasons_text or "No directional evidence available."

    signal = Signal(
        pair=pair,
        timeframe=timeframe,
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=risk_reward,
        confidence=directional.confidence,
        reasoning=reasoning,
        triggered_conditions=directional.reasons,
        invalidating_conditions=directional.invalidation_conditions,
        strategy_alignment=directional.setup_status,
        market_context=ai_reasoning,
        strategy_used=strategy_id,
        model_provider=model_provider,
    )

    processing_time = int((time.time() - start_time) * 1000)

    analysis = AnalysisResult(
        pair=pair,
        timeframe=timeframe,
        strategy_id=strategy_id,
        market_data_snapshot={
            "current_price": technical_analysis.get("current_price"),
            "data_provider": snapshot.data_provider if snapshot else None,
            "data_timestamp": snapshot.data_timestamp.isoformat() if snapshot and snapshot.data_timestamp else None,
            "quote": {
                "bid": snapshot.quote.bid,
                "ask": snapshot.quote.ask,
                "spread": snapshot.quote.spread,
            } if snapshot and snapshot.quote else None,
            "data_status": directional.status,
            "data_status_detail": detail,
        },
        technical_analysis=technical_analysis,
        strategy_context=strategy_context,
        ai_reasoning=ai_reasoning,
        signal=signal,
        model_provider=model_provider,
        processing_time_ms=processing_time,
        data_status=directional.status,
        directional=directional.model_dump(),
    )

    try:
        db = get_db()
        await db.analyses.insert_one(analysis.model_dump(by_alias=True))
    except Exception as exc:
        logger.debug(f"analysis persistence skipped: {exc}")

    return analysis
