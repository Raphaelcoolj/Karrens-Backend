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

logger = logging.getLogger(__name__)

market_data_service = MarketDataService()
ai_service = AIProviderService()


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


async def run_analysis(
    pair: str,
    timeframe: str,
    strategy_id: Optional[str] = None,
) -> AnalysisResult:
    start_time = time.time()

    snapshot = await market_data_service.get_full_market_data(pair, timeframe)

    klines_for_ta = [
        {
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in snapshot.candles
    ]
    technical_analysis = analyze_market(klines_for_ta)

    strategy_context = None
    strategy_rules = None
    if strategy_id:
        db = get_db()
        rules_doc = await db.strategy_rules.find_one({"strategy_id": strategy_id})
        if rules_doc:
            strategy_rules = {k: v for k, v in rules_doc.items() if k != "_id" and k != "strategy_id"}
            strategy_context = {"rules": strategy_rules}

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

    if not ai_result["success"]:
        logger.error(f"AI generation failed: {ai_result.get('error')}")
        signal = Signal(
            pair=pair,
            timeframe=timeframe,
            direction=Direction.NO_SIGNAL,
            reasoning="AI provider unavailable. Please try again.",
            strategy_used=strategy_id,
        )
    else:
        parsed = parse_ai_signal_response(ai_result["response"])
        logger.info(f"AI raw response (first 500): {ai_result['response'][:500]}")
        logger.info(f"Parsed signal: direction={parsed.get('direction')}, confidence={parsed.get('confidence')}, entry={parsed.get('entry')}")
        current_price = technical_analysis.get("current_price", 0)
        validated = validate_signal(parsed, current_price)
        logger.info(f"Validation: valid={validated['valid']}, direction={validated['direction']}")

        signal = Signal(
            pair=pair,
            timeframe=timeframe,
            direction=Direction(validated["direction"]),
            entry=validated["entry"],
            stop_loss=validated["stop_loss"],
            take_profit=validated["take_profit"],
            risk_reward=validated["risk_reward"],
            confidence=validated["confidence"],
            reasoning=validated["reasoning"],
            triggered_conditions=validated["triggered_conditions"],
            invalidating_conditions=validated["invalidating_conditions"],
            strategy_alignment=validated["strategy_alignment"],
            market_context=validated["market_context"],
            strategy_used=strategy_id,
            model_provider=ai_result["provider"],
        )

    processing_time = int((time.time() - start_time) * 1000)

    analysis = AnalysisResult(
        pair=pair,
        timeframe=timeframe,
        strategy_id=strategy_id,
        market_data_snapshot={
            "current_price": technical_analysis.get("current_price"),
            "data_provider": snapshot.data_provider,
            "data_timestamp": snapshot.data_timestamp.isoformat() if snapshot.data_timestamp else None,
            "quote": {
                "bid": snapshot.quote.bid,
                "ask": snapshot.quote.ask,
                "spread": snapshot.quote.spread,
            } if snapshot.quote else None,
        },
        technical_analysis=technical_analysis,
        strategy_context=strategy_context,
        ai_reasoning=signal.reasoning if signal else "",
        signal=signal,
        model_provider=ai_result.get("provider"),
        processing_time_ms=processing_time,
    )

    db = get_db()
    await db.analyses.insert_one(analysis.model_dump(by_alias=True))

    return analysis
