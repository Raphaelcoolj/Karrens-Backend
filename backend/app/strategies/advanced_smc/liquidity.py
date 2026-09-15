from __future__ import annotations
from datetime import datetime, time
from app.strategies.advanced_smc.models import Candle, LiquidityLevel, SwingPoint
from app.strategies.advanced_smc.config import AdvancedSMCConfig, SessionConfig


def detect_liquidity(
    candles: list[Candle],
    swings: list[SwingPoint],
    atr: float,
    config: AdvancedSMCConfig | None = None,
) -> list[LiquidityLevel]:
    levels: list[LiquidityLevel] = []
    tolerance = atr * 0.10

    levels.extend(_detect_equal_highs(swings, tolerance))
    levels.extend(_detect_equal_lows(swings, tolerance))

    if candles:
        levels.extend(_detect_pdh_pdl(candles))

    if config and config.session_liquidity_enabled:
        levels.extend(_detect_session_levels(candles, config))

    levels.extend(_detect_major_swing_levels(swings))

    return levels


def _detect_equal_highs(swings: list[SwingPoint], tolerance: float) -> list[LiquidityLevel]:
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
                type="EQUAL_HIGH", price=avg_price, strength=float(len(cluster)),
            ))
            used.add(i)

    return levels


def _detect_equal_lows(swings: list[SwingPoint], tolerance: float) -> list[LiquidityLevel]:
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
                type="EQUAL_LOW", price=avg_price, strength=float(len(cluster)),
            ))
            used.add(i)

    return levels


def _detect_pdh_pdl(candles: list[Candle]) -> list[LiquidityLevel]:
    levels: list[LiquidityLevel] = []
    if len(candles) < 2:
        return levels

    prev = candles[-2]
    levels.append(LiquidityLevel(type="PDH", price=prev.high, strength=1.0))
    levels.append(LiquidityLevel(type="PDL", price=prev.low, strength=1.0))

    return levels


def _detect_session_levels(
    candles: list[Candle],
    config: AdvancedSMCConfig,
) -> list[LiquidityLevel]:
    levels: list[LiquidityLevel] = []
    if not candles:
        return levels

    asian = _get_session_high_low(candles, config.asian_session)
    if asian:
        levels.append(LiquidityLevel(type="ASIAN_HIGH", price=asian[0], strength=1.0, session="asian"))
        levels.append(LiquidityLevel(type="ASIAN_LOW", price=asian[1], strength=1.0, session="asian"))

    london = _get_session_high_low(candles, config.london_session)
    if london:
        levels.append(LiquidityLevel(type="LONDON_HIGH", price=london[0], strength=1.0, session="london"))
        levels.append(LiquidityLevel(type="LONDON_LOW", price=london[1], strength=1.0, session="london"))

    ny = _get_session_high_low(candles, config.new_york_session)
    if ny:
        levels.append(LiquidityLevel(type="NY_HIGH", price=ny[0], strength=1.0, session="ny"))
        levels.append(LiquidityLevel(type="NY_LOW", price=ny[1], strength=1.0, session="ny"))

    return levels


def _get_session_high_low(
    candles: list[Candle],
    session: SessionConfig,
) -> tuple[float, float] | None:
    session_candles = []
    for c in candles:
        t = c.timestamp.time()
        if session.start <= session.end:
            if session.start <= t <= session.end:
                session_candles.append(c)
        else:
            if t >= session.start or t <= session.end:
                session_candles.append(c)

    if not session_candles:
        return None

    high = max(c.high for c in session_candles)
    low = min(c.low for c in session_candles)
    return (high, low)


def _detect_major_swing_levels(swings: list[SwingPoint]) -> list[LiquidityLevel]:
    levels: list[LiquidityLevel] = []
    for s in swings:
        if s.strength >= 4:
            lt = "SWING_HIGH" if s.type == "HIGH" else "SWING_LOW"
            levels.append(LiquidityLevel(type=lt, price=s.price, strength=float(s.strength)))
    return levels


def detect_sweeps(
    candles: list[Candle],
    liquidity_levels: list[LiquidityLevel],
    lookback: int = 20,
) -> list[LiquidityLevel]:
    if not candles or not liquidity_levels:
        return []

    recent = candles[-lookback:] if len(candles) >= lookback else candles
    swept: list[LiquidityLevel] = []

    for level in liquidity_levels:
        if level.swept:
            continue

        if level.type in ("EQUAL_HIGH", "PDH", "ASIAN_HIGH", "LONDON_HIGH", "NY_HIGH", "SESSION_HIGH", "SWING_HIGH"):
            for c in reversed(recent):
                if c.high > level.price:
                    level.swept = True
                    level.sweep_timestamp = c.timestamp
                    swept.append(level)
                    break

        elif level.type in ("EQUAL_LOW", "PDL", "ASIAN_LOW", "LONDON_LOW", "NY_LOW", "SESSION_LOW", "SWING_LOW"):
            for c in reversed(recent):
                if c.low < level.price:
                    level.swept = True
                    level.sweep_timestamp = c.timestamp
                    swept.append(level)
                    break

    return swept
