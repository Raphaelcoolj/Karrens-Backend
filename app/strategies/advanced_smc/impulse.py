from __future__ import annotations
from app.strategies.advanced_smc.models import Candle


def is_impulse(candle: Candle, prev_candle: Candle | None, atr: float) -> str | None:
    if prev_candle is None:
        return None

    body = abs(candle.close - candle.open)
    if body < atr * 0.5:
        return None

    if candle.close > candle.open:
        return "BULLISH"
    elif candle.close < candle.open:
        return "BEARISH"
    return None


def is_liquidity_grab(candle: Candle, prev_candle: Candle) -> bool:
    if prev_candle is None:
        return False

    if candle.high > prev_candle.high and candle.low < prev_candle.low:
        return True

    if candle.high > prev_candle.high and candle.close < prev_candle.high:
        return True

    if candle.low < prev_candle.low and candle.close > prev_candle.low:
        return True

    return False


def detect_pullbacks(
    candles: list[Candle],
    atr: float,
) -> list[tuple[int, str]]:
    pullbacks: list[tuple[int, str]] = []

    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i - 1]

        if is_liquidity_grab(c, prev):
            if c.close > prev.close:
                pullbacks.append((i, "BULLISH_LIQUIDITY_GRAB"))
            else:
                pullbacks.append((i, "BEARISH_LIQUIDITY_GRAB"))

    return pullbacks


def find_extreme_candle(
    candles: list[Candle],
    start: int,
    end: int,
    direction: str,
) -> int:
    if start > end or start < 0 or end >= len(candles):
        return start

    if direction == "HIGHEST":
        return max(range(start, end + 1), key=lambda i: candles[i].high)
    else:
        return min(range(start, end + 1), key=lambda i: candles[i].low)
