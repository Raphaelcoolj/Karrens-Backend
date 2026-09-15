from __future__ import annotations
from app.strategies.advanced_smc.models import Candle, IDM


def detect_pullbacks_via_liquidity_grab(
    candles: list[Candle],
    start: int,
    end: int,
) -> list[int]:
    pullbacks: list[int] = []

    for i in range(max(start, 1), min(end + 1, len(candles))):
        c = candles[i]
        prev = candles[i - 1]

        if c.high > prev.high and c.low < prev.low:
            pullbacks.append(i)
        elif c.high > prev.high and c.close < prev.high:
            pullbacks.append(i)
        elif c.low < prev.low and c.close > prev.low:
            pullbacks.append(i)

    return pullbacks


def find_first_pullback_after_poi(
    candles: list[Candle],
    poi_index: int,
) -> int | None:
    for i in range(poi_index + 1, len(candles)):
        if i == 0:
            continue
        c = candles[i]
        prev = candles[i - 1]

        if c.high > prev.high and c.low < prev.low:
            return i
        elif c.high > prev.high and c.close < prev.high:
            return i
        elif c.low < prev.low and c.close > prev.low:
            return i

    return None


def find_idm_in_move(
    candles: list[Candle],
    move_start: int,
    move_end: int,
    direction: str,
) -> IDM | None:
    if move_start >= move_end or move_end >= len(candles):
        return None

    extreme_idx = move_start
    if direction == "BULLISH":
        for i in range(move_start, move_end + 1):
            if candles[i].low < candles[extreme_idx].low:
                extreme_idx = i
    else:
        for i in range(move_start, move_end + 1):
            if candles[i].high > candles[extreme_idx].high:
                extreme_idx = i

    for i in range(extreme_idx, move_start - 1, -1):
        c = candles[i]
        prev = candles[i - 1] if i > 0 else None

        if prev is None:
            continue

        is_grab = False
        if direction == "BULLISH":
            if c.low < prev.low:
                is_grab = True
        else:
            if c.high > prev.high:
                is_grab = True

        if is_grab:
            return IDM(
                index=i,
                timestamp=c.timestamp,
                price=c.low if direction == "BULLISH" else c.high,
                direction=direction,
            )

    return None
