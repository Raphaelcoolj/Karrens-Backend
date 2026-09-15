from __future__ import annotations
from app.strategies.swing_smc.models import Candle, FairValueGap


def detect_fvg(
    candles: list[Candle],
    atr: float,
    min_size_atr: float = 0.10,
    timeframe: str = "4H",
) -> list[FairValueGap]:
    if len(candles) < 3:
        return []

    fvgs: list[FairValueGap] = []
    min_size = atr * min_size_atr

    for i in range(2, len(candles)):
        c1 = candles[i - 2]
        c3 = candles[i]

        if c3.low > c1.high:
            size = c3.low - c1.high
            if size >= min_size:
                fvgs.append(FairValueGap(
                    direction="BULLISH",
                    high=c3.low,
                    low=c1.high,
                    midpoint=(c3.low + c1.high) / 2,
                    created_at=c3.timestamp,
                    timeframe=timeframe,
                ))

        elif c3.high < c1.low:
            size = c1.low - c3.high
            if size >= min_size:
                fvgs.append(FairValueGap(
                    direction="BEARISH",
                    high=c1.low,
                    low=c3.high,
                    midpoint=(c1.low + c3.high) / 2,
                    created_at=c3.timestamp,
                    timeframe=timeframe,
                ))

    return fvgs


def check_fvg_fill(
    fvg: FairValueGap,
    candles: list[Candle],
    start_index: int,
) -> FairValueGap:
    if start_index >= len(candles):
        return fvg

    gap_size = fvg.high - fvg.low
    if gap_size <= 0:
        fvg.filled = True
        fvg.fill_percentage = 1.0
        return fvg

    max_fill = 0.0

    for i in range(start_index, len(candles)):
        c = candles[i]
        if fvg.direction == "BULLISH":
            if c.low < fvg.high:
                fill_depth = min(fvg.high - c.low, gap_size)
                max_fill = max(max_fill, fill_depth)
        else:
            if c.high > fvg.low:
                fill_depth = min(c.high - fvg.low, gap_size)
                max_fill = max(max_fill, fill_depth)

    fvg.fill_percentage = min(max_fill / gap_size, 1.0)
    fvg.filled = fvg.fill_percentage >= 0.99

    return fvg
