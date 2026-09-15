from __future__ import annotations
from app.strategies.advanced_smc.models import Candle, IFC


def detect_ifc(
    candles: list[Candle],
    atr: float,
    wick_ratio: float = 0.6,
    sweep_atr: float = 0.3,
) -> list[IFC]:
    if len(candles) < 2:
        return []

    ifcs: list[IFC] = []
    min_wick = atr * sweep_atr

    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i - 1]

        body = abs(c.close - c.open)
        rng = c.high - c.low
        if rng <= 0:
            continue

        upper_wick = c.high - max(c.open, c.close)
        lower_wick = min(c.open, c.close) - c.low

        is_pin = False
        direction = None

        if lower_wick > body and lower_wick / rng >= wick_ratio and lower_wick >= min_wick:
            is_pin = True
            direction = "BULLISH"
        elif upper_wick > body and upper_wick / rng >= wick_ratio and upper_wick >= min_wick:
            is_pin = True
            direction = "BEARISH"

        if not is_pin:
            continue

        swept = False
        if direction == "BULLISH":
            if c.low < prev.low:
                swept = True
            if c.close > prev.low:
                ifcs.append(IFC(
                    direction=direction,
                    high=c.high,
                    low=c.low,
                    wick_high=max(c.open, c.close),
                    wick_low=c.low,
                    timestamp=c.timestamp,
                    index=i,
                    swept_liquidity=swept,
                    closes_through=True,
                ))
        elif direction == "BEARISH":
            if c.high > prev.high:
                swept = True
            if c.close < prev.high:
                ifcs.append(IFC(
                    direction=direction,
                    high=c.high,
                    low=c.low,
                    wick_high=c.high,
                    wick_low=min(c.open, c.close),
                    timestamp=c.timestamp,
                    index=i,
                    swept_liquidity=swept,
                    closes_through=True,
                ))

    return ifcs
