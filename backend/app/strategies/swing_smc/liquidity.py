from __future__ import annotations
from app.strategies.swing_smc.models import Candle, SwingPoint, LiquidityLevel
from app.strategies.swing_smc.swings import detect_swings


def detect_liquidity(
    candles: list[Candle],
    swings: list[SwingPoint],
    atr: float,
    tolerance_atr: float = 0.10,
) -> list[LiquidityLevel]:
    levels: list[LiquidityLevel] = []
    tolerance = atr * tolerance_atr

    levels.extend(_detect_equal_highs(swings, tolerance))
    levels.extend(_detect_equal_lows(swings, tolerance))
    levels.extend(_detect_previous_day_levels(candles))
    levels.extend(_detect_major_swing_levels(swings))

    return levels


def _detect_equal_highs(
    swings: list[SwingPoint],
    tolerance: float,
) -> list[LiquidityLevel]:
    highs = [s for s in swings if s.type == "HIGH"]
    levels: list[LiquidityLevel] = []
    used = set()

    for i in range(len(highs)):
        if i in used:
            continue
        cluster = [highs[i]]
        for j in range(i + 1, len(highs)):
            if j in used:
                continue
            if abs(highs[i].price - highs[j].price) <= tolerance:
                cluster.append(highs[j])
                used.add(j)
        if len(cluster) >= 2:
            avg_price = sum(h.price for h in cluster) / len(cluster)
            levels.append(LiquidityLevel(
                type="EQUAL_HIGH",
                price=avg_price,
                strength=len(cluster),
            ))
            used.add(i)

    return levels


def _detect_equal_lows(
    swings: list[SwingPoint],
    tolerance: float,
) -> list[LiquidityLevel]:
    lows = [s for s in swings if s.type == "LOW"]
    levels: list[LiquidityLevel] = []
    used = set()

    for i in range(len(lows)):
        if i in used:
            continue
        cluster = [lows[i]]
        for j in range(i + 1, len(lows)):
            if j in used:
                continue
            if abs(lows[i].price - lows[j].price) <= tolerance:
                cluster.append(lows[j])
                used.add(j)
        if len(cluster) >= 2:
            avg_price = sum(l.price for l in cluster) / len(cluster)
            levels.append(LiquidityLevel(
                type="EQUAL_LOW",
                price=avg_price,
                strength=len(cluster),
            ))
            used.add(i)

    return levels


def _detect_previous_day_levels(candles: list[Candle]) -> list[LiquidityLevel]:
    levels: list[LiquidityLevel] = []
    if len(candles) < 2:
        return levels

    prev = candles[-2]
    levels.append(LiquidityLevel(
        type="PREVIOUS_HIGH",
        price=prev.high,
        strength=1.0,
    ))
    levels.append(LiquidityLevel(
        type="PREVIOUS_LOW",
        price=prev.low,
        strength=1.0,
    ))

    return levels


def _detect_major_swing_levels(swings: list[SwingPoint]) -> list[LiquidityLevel]:
    levels: list[LiquidityLevel] = []
    for s in swings:
        if s.strength >= 4:
            lt = "SWING_HIGH" if s.type == "HIGH" else "SWING_LOW"
            levels.append(LiquidityLevel(
                type=lt,
                price=s.price,
                strength=s.strength,
            ))
    return levels


def detect_sweeps(
    candles: list[Candle],
    liquidity_levels: list[LiquidityLevel],
    lookback: int = 10,
) -> list[LiquidityLevel]:
    if not candles or not liquidity_levels:
        return []

    recent = candles[-lookback:] if len(candles) >= lookback else candles
    swept: list[LiquidityLevel] = []

    for level in liquidity_levels:
        if level.swept:
            continue

        if level.type in ("EQUAL_HIGH", "PREVIOUS_HIGH", "SWING_HIGH"):
            for c in reversed(recent):
                if c.high > level.price:
                    level.swept = True
                    level.sweep_timestamp = c.timestamp
                    swept.append(level)
                    break

        elif level.type in ("EQUAL_LOW", "PREVIOUS_LOW", "SWING_LOW"):
            for c in reversed(recent):
                if c.low < level.price:
                    level.swept = True
                    level.sweep_timestamp = c.timestamp
                    swept.append(level)
                    break

    return swept
