from __future__ import annotations
from app.strategies.swing_smc.models import Candle, StructureEvent, OrderBlock


def detect_order_blocks(
    candles: list[Candle],
    structure_events: list[StructureEvent],
    atr: float,
    body_atr_mult: float = 1.2,
    body_ratio_min: float = 0.65,
) -> list[OrderBlock]:
    if len(candles) < 3:
        return []

    obs: list[OrderBlock] = []

    for event in structure_events:
        if event.type != "BOS":
            continue

        if event.direction == "BULLISH":
            ob = _find_bullish_ob(candles, event, atr, body_atr_mult, body_ratio_min)
            if ob:
                obs.append(ob)
        else:
            ob = _find_bearish_ob(candles, event, atr, body_atr_mult, body_ratio_min)
            if ob:
                obs.append(ob)

    return obs


def _find_bullish_ob(
    candles: list[Candle],
    event: StructureEvent,
    atr: float,
    body_atr_mult: float,
    body_ratio_min: float,
) -> OrderBlock | None:
    idx = event.broken_swing_index
    if idx < 1 or idx >= len(candles):
        return None

    for i in range(idx - 1, max(idx - 5, 0), -1):
        c = candles[i]
        body = abs(c.close - c.open)
        rng = c.high - c.low

        if rng <= 0:
            continue

        is_bearish = c.close < c.open
        has_displacement = body >= atr * body_atr_mult
        good_ratio = (body / rng) >= body_ratio_min

        if is_bearish and has_displacement and good_ratio:
            return OrderBlock(
                direction="BULLISH",
                high=c.high,
                low=c.low,
                timestamp=c.timestamp,
                source_candle_index=i,
                strength=body / atr if atr > 0 else 0,
            )

    return None


def _find_bearish_ob(
    candles: list[Candle],
    event: StructureEvent,
    atr: float,
    body_atr_mult: float,
    body_ratio_min: float,
) -> OrderBlock | None:
    idx = event.broken_swing_index
    if idx < 1 or idx >= len(candles):
        return None

    for i in range(idx - 1, max(idx - 5, 0), -1):
        c = candles[i]
        body = abs(c.close - c.open)
        rng = c.high - c.low

        if rng <= 0:
            continue

        is_bullish = c.close > c.open
        has_displacement = body >= atr * body_atr_mult
        good_ratio = (body / rng) >= body_ratio_min

        if is_bullish and has_displacement and good_ratio:
            return OrderBlock(
                direction="BEARISH",
                high=c.high,
                low=c.low,
                timestamp=c.timestamp,
                source_candle_index=i,
                strength=body / atr if atr > 0 else 0,
            )

    return None


def check_ob_mitigation(
    ob: OrderBlock,
    candles: list[Candle],
    start_index: int,
) -> OrderBlock:
    if start_index >= len(candles):
        return ob

    for i in range(start_index, len(candles)):
        c = candles[i]
        if ob.direction == "BULLISH":
            if c.close < ob.low:
                ob.mitigated = True
                break
        else:
            if c.close > ob.high:
                ob.mitigated = True
                break

    return ob
