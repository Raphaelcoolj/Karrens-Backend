from __future__ import annotations
from app.strategies.swing_smc.models import Candle


def detect_displacement(
    candles: list[Candle],
    atr: float,
    body_atr_mult: float = 1.2,
    body_ratio_min: float = 0.65,
) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []

    for i, c in enumerate(candles):
        body = abs(c.close - c.open)
        rng = c.high - c.low

        if rng <= 0:
            continue

        if body < atr * body_atr_mult:
            continue
        if (body / rng) < body_ratio_min:
            continue

        direction = "BULLISH" if c.close > c.open else "BEARISH"
        results.append((i, direction))

    return results


def is_displacement_candle(
    candle: Candle,
    atr: float,
    body_atr_mult: float = 1.2,
    body_ratio_min: float = 0.65,
) -> str | None:
    body = abs(candle.close - candle.open)
    rng = candle.high - candle.low

    if rng <= 0:
        return None

    if body < atr * body_atr_mult:
        return None
    if (body / rng) < body_ratio_min:
        return None

    return "BULLISH" if candle.close > candle.open else "BEARISH"
