from __future__ import annotations
from app.strategies.swing_smc.models import Candle, SwingPoint


def detect_swings(
    candles: list[Candle],
    left: int = 2,
    right: int = 2,
) -> list[SwingPoint]:
    if len(candles) < left + right + 1:
        return []

    swings: list[SwingPoint] = []

    for i in range(left, len(candles) - right):
        is_high = True
        for j in range(1, left + 1):
            if candles[i].high < candles[i - j].high:
                is_high = False
                break
        if is_high:
            for j in range(1, right + 1):
                if candles[i].high < candles[i + j].high:
                    is_high = False
                    break

        is_low = True
        for j in range(1, left + 1):
            if candles[i].low > candles[i - j].low:
                is_low = False
                break
        if is_low:
            for j in range(1, right + 1):
                if candles[i].low > candles[i + j].low:
                    is_low = False
                    break

        if is_high:
            strength = _calc_strength(candles, i, "HIGH", left, right)
            swings.append(SwingPoint(
                index=i,
                timestamp=candles[i].timestamp,
                price=candles[i].high,
                type="HIGH",
                strength=strength,
            ))

        if is_low:
            strength = _calc_strength(candles, i, "LOW", left, right)
            swings.append(SwingPoint(
                index=i,
                timestamp=candles[i].timestamp,
                price=candles[i].low,
                type="LOW",
                strength=strength,
            ))

    return swings


def _calc_strength(
    candles: list[Candle],
    index: int,
    swing_type: str,
    left: int,
    right: int,
) -> int:
    strength = 0
    if swing_type == "HIGH":
        price = candles[index].high
        for j in range(1, max(left, right) + 3):
            if index - j >= 0 and candles[index - j].high < price:
                strength += 1
            if index + j < len(candles) and candles[index + j].high < price:
                strength += 1
    else:
        price = candles[index].low
        for j in range(1, max(left, right) + 3):
            if index - j >= 0 and candles[index - j].low > price:
                strength += 1
            if index + j < len(candles) and candles[index + j].low > price:
                strength += 1
    return strength
