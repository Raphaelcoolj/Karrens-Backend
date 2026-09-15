from __future__ import annotations
from app.strategies.swing_smc.models import (
    Candle,
    SwingPoint,
    StructureEvent,
    LiquidityLevel,
    FairValueGap,
    OrderBlock,
    TradeSetup,
)
from app.strategies.swing_smc.config import SwingSMCConfig
from app.strategies.swing_smc.scoring import ScoringInput, ScoringWeights, calculate_score


def build_long_setup(
    candles: list[Candle],
    current_price: float,
    htf_bias: str,
    swings: list[SwingPoint],
    structure_events: list[StructureEvent],
    liquidity_levels: list[LiquidityLevel],
    swept_levels: list[LiquidityLevel],
    fvgs: list[FairValueGap],
    order_blocks: list[OrderBlock],
    has_displacement: bool,
    volume_confirms: bool,
    premium_discount: tuple[str, float, float],
    atr: float,
    config: SwingSMCConfig,
) -> TradeSetup:
    setup = TradeSetup(direction="NO_SIGNAL")

    if htf_bias not in ("BULLISH", "NEUTRAL"):
        setup.reasons.append(f"HTF bias is {htf_bias}, not bullish")
        return setup

    bullish_structure = any(
        e.direction == "BULLISH" and e.confirmed
        for e in structure_events
    )

    bullish_sweep = any(
        l.type in ("EQUAL_LOW", "PREVIOUS_LOW", "SWING_LOW") and l.swept
        for l in swept_levels
    )

    valid_fvg = _find_valid_fvg(fvgs, "BULLISH", current_price, atr)
    valid_ob = _find_valid_ob(order_blocks, "BULLISH", current_price)

    zone_name, _, _ = premium_discount
    in_discount = zone_name == "DISCOUNT"

    entry_low, entry_high = _build_entry_zone(valid_fvg, valid_ob, current_price)

    if entry_low is None or entry_high is None:
        setup.reasons.append("No valid entry zone found")
        return setup

    sl = _calc_stop_loss(entry_low, swept_levels, valid_ob, swings, atr, "LONG")
    risk = entry_low - sl

    tp1, tp2, tp3 = _calc_take_profits(entry_high, liquidity_levels, swings, "LONG", risk, config.minimum_rr)

    reasons = []
    if htf_bias == "BULLISH":
        reasons.append("Higher timeframe structure is bullish")
    if bullish_sweep:
        reasons.append("Sell-side liquidity was swept")
    if bullish_structure:
        reasons.append("Bullish structural break confirmed")
    if valid_fvg:
        reasons.append(f"Bullish FVG detected at {valid_fvg.low:.2f}-{valid_fvg.high:.2f}")
    if valid_ob:
        reasons.append(f"Bullish order block at {valid_ob.low:.2f}-{valid_ob.high:.2f}")
    if in_discount:
        reasons.append("Price is in discount zone")
    if has_displacement:
        reasons.append("Bullish displacement candle detected")
    if volume_confirms:
        reasons.append("Volume confirms bullish momentum")

    invalidation = []
    invalidation.append(f"Price closes below {sl:.2f} (stop loss)")
    if valid_ob:
        invalidation.append(f"Price closes below order block low {valid_ob.low:.2f}")
    if bullish_structure:
        invalidation.append("Bearish structural break invalidates setup")

    scoring = ScoringInput(
        htf_aligned=htf_bias == "BULLISH",
        structure_confirmed=bullish_structure,
        liquidity_swept=bullish_sweep,
        in_preferred_zone=in_discount,
        has_order_block=valid_ob is not None,
        has_fvg=valid_fvg is not None,
        has_displacement=has_displacement,
        volume_confirms=volume_confirms,
    )

    confidence = calculate_score(scoring)

    setup.direction = "LONG"
    setup.entry_low = entry_low
    setup.entry_high = entry_high
    setup.stop_loss = sl
    setup.take_profit_1 = tp1
    setup.take_profit_2 = tp2
    setup.take_profit_3 = tp3
    setup.confidence = confidence
    setup.market_bias = "BULLISH" if htf_bias == "BULLISH" else "NEUTRAL"
    setup.reasons = reasons
    setup.invalidation_conditions = invalidation
    setup.structure_events = structure_events
    setup.liquidity_levels = liquidity_levels
    setup.fvg = valid_fvg
    setup.order_block = valid_ob

    return setup


def build_short_setup(
    candles: list[Candle],
    current_price: float,
    htf_bias: str,
    swings: list[SwingPoint],
    structure_events: list[StructureEvent],
    liquidity_levels: list[LiquidityLevel],
    swept_levels: list[LiquidityLevel],
    fvgs: list[FairValueGap],
    order_blocks: list[OrderBlock],
    has_displacement: bool,
    volume_confirms: bool,
    premium_discount: tuple[str, float, float],
    atr: float,
    config: SwingSMCConfig,
) -> TradeSetup:
    setup = TradeSetup(direction="NO_SIGNAL")

    if htf_bias not in ("BEARISH", "NEUTRAL"):
        setup.reasons.append(f"HTF bias is {htf_bias}, not bearish")
        return setup

    bearish_structure = any(
        e.direction == "BEARISH" and e.confirmed
        for e in structure_events
    )

    bearish_sweep = any(
        l.type in ("EQUAL_HIGH", "PREVIOUS_HIGH", "SWING_HIGH") and l.swept
        for l in swept_levels
    )

    valid_fvg = _find_valid_fvg(fvgs, "BEARISH", current_price, atr)
    valid_ob = _find_valid_ob(order_blocks, "BEARISH", current_price)

    zone_name, _, _ = premium_discount
    in_premium = zone_name == "PREMIUM"

    entry_low, entry_high = _build_entry_zone_short(valid_fvg, valid_ob, current_price)

    if entry_low is None or entry_high is None:
        setup.reasons.append("No valid entry zone found")
        return setup

    sl = _calc_stop_loss_short(entry_high, swept_levels, valid_ob, swings, atr)
    risk = sl - entry_high

    tp1, tp2, tp3 = _calc_take_profits_short(entry_low, liquidity_levels, swings, risk, config.minimum_rr)

    reasons = []
    if htf_bias == "BEARISH":
        reasons.append("Higher timeframe structure is bearish")
    if bearish_sweep:
        reasons.append("Buy-side liquidity was swept")
    if bearish_structure:
        reasons.append("Bearish structural break confirmed")
    if valid_fvg:
        reasons.append(f"Bearish FVG detected at {valid_fvg.low:.2f}-{valid_fvg.high:.2f}")
    if valid_ob:
        reasons.append(f"Bearish order block at {valid_ob.low:.2f}-{valid_ob.high:.2f}")
    if in_premium:
        reasons.append("Price is in premium zone")
    if has_displacement:
        reasons.append("Bearish displacement candle detected")
    if volume_confirms:
        reasons.append("Volume confirms bearish momentum")

    invalidation = []
    invalidation.append(f"Price closes above {sl:.2f} (stop loss)")
    if valid_ob:
        invalidation.append(f"Price closes above order block high {valid_ob.high:.2f}")
    if bearish_structure:
        invalidation.append("Bullish structural break invalidates setup")

    scoring = ScoringInput(
        htf_aligned=htf_bias == "BEARISH",
        structure_confirmed=bearish_structure,
        liquidity_swept=bearish_sweep,
        in_preferred_zone=in_premium,
        has_order_block=valid_ob is not None,
        has_fvg=valid_fvg is not None,
        has_displacement=has_displacement,
        volume_confirms=volume_confirms,
    )

    confidence = calculate_score(scoring)

    setup.direction = "SHORT"
    setup.entry_low = entry_low
    setup.entry_high = entry_high
    setup.stop_loss = sl
    setup.take_profit_1 = tp1
    setup.take_profit_2 = tp2
    setup.take_profit_3 = tp3
    setup.confidence = confidence
    setup.market_bias = "BEARISH" if htf_bias == "BEARISH" else "NEUTRAL"
    setup.reasons = reasons
    setup.invalidation_conditions = invalidation
    setup.structure_events = structure_events
    setup.liquidity_levels = liquidity_levels
    setup.fvg = valid_fvg
    setup.order_block = valid_ob

    return setup


def _find_valid_fvg(
    fvgs: list[FairValueGap],
    direction: str,
    current_price: float,
    atr: float,
) -> FairValueGap | None:
    valid = [
        f for f in fvgs
        if f.direction == direction and not f.filled
    ]
    if not valid:
        return None

    for f in valid:
        if direction == "BULLISH":
            if f.low <= current_price <= f.high + atr * 0.5:
                return f
        else:
            if f.low - atr * 0.5 <= current_price <= f.high:
                return f

    return valid[0] if valid else None


def _find_valid_ob(
    obs: list[OrderBlock],
    direction: str,
    current_price: float,
) -> OrderBlock | None:
    valid = [
        o for o in obs
        if o.direction == direction and not o.mitigated
    ]
    if not valid:
        return None

    for o in valid:
        if direction == "BULLISH":
            if o.low <= current_price <= o.high * 1.02:
                return o
        else:
            if o.low * 0.98 <= current_price <= o.high:
                return o

    return valid[0] if valid else None


def _build_entry_zone(
    fvg: FairValueGap | None,
    ob: OrderBlock | None,
    current_price: float,
) -> tuple[float | None, float | None]:
    if fvg and ob:
        low = max(fvg.low, ob.low)
        high = min(fvg.high, ob.high)
        if low < high:
            return (low, high)

    if fvg:
        return (fvg.low, fvg.high)

    if ob:
        return (ob.low, ob.high)

    return (None, None)


def _build_entry_zone_short(
    fvg: FairValueGap | None,
    ob: OrderBlock | None,
    current_price: float,
) -> tuple[float | None, float | None]:
    return _build_entry_zone(fvg, ob, current_price)


def _calc_stop_loss(
    entry_low: float,
    swept_levels: list[LiquidityLevel],
    ob: OrderBlock | None,
    swings: list[SwingPoint],
    atr: float,
    direction: str,
) -> float:
    buffer = atr * 0.1

    sweep_lows = [
        l.price for l in swept_levels
        if l.type in ("EQUAL_LOW", "PREVIOUS_LOW", "SWING_LOW")
    ]
    if sweep_lows:
        return min(sweep_lows) - buffer

    if ob:
        return ob.low - buffer

    lows = [s.price for s in swings if s.type == "LOW" and s.price < entry_low]
    if lows:
        return max(lows) - buffer

    return entry_low - atr * 2


def _calc_stop_loss_short(
    entry_high: float,
    swept_levels: list[LiquidityLevel],
    ob: OrderBlock | None,
    swings: list[SwingPoint],
    atr: float,
) -> float:
    buffer = atr * 0.1

    sweep_highs = [
        l.price for l in swept_levels
        if l.type in ("EQUAL_HIGH", "PREVIOUS_HIGH", "SWING_HIGH")
    ]
    if sweep_highs:
        return max(sweep_highs) + buffer

    if ob:
        return ob.high + buffer

    highs = [s.price for s in swings if s.type == "HIGH" and s.price > entry_high]
    if highs:
        return min(highs) + buffer

    return entry_high + atr * 2


def _calc_take_profits(
    entry_high: float,
    liquidity_levels: list[LiquidityLevel],
    swings: list[SwingPoint],
    direction: str,
    risk: float = 0,
    min_rr: float = 2.0,
) -> tuple[float | None, float | None, float | None]:
    targets: list[float] = []

    buy_side = [
        l.price for l in liquidity_levels
        if l.type in ("EQUAL_HIGH", "PREVIOUS_HIGH", "SWING_HIGH")
        and l.price > entry_high
    ]
    targets.extend(sorted(buy_side))

    swing_highs = sorted(
        [s.price for s in swings if s.type == "HIGH" and s.price > entry_high],
    )
    targets.extend(swing_highs)

    targets = sorted(set(targets))

    if risk > 0 and targets:
        adequate = [t for t in targets if (t - entry_high) >= risk * min_rr]
        if adequate:
            targets = adequate

    tp1 = targets[0] if len(targets) > 0 else None
    tp2 = targets[1] if len(targets) > 1 else None
    tp3 = targets[2] if len(targets) > 2 else None

    return (tp1, tp2, tp3)


def _calc_take_profits_short(
    entry_low: float,
    liquidity_levels: list[LiquidityLevel],
    swings: list[SwingPoint],
    risk: float = 0,
    min_rr: float = 2.0,
) -> tuple[float | None, float | None, float | None]:
    targets: list[float] = []

    sell_side = [
        l.price for l in liquidity_levels
        if l.type in ("EQUAL_LOW", "PREVIOUS_LOW", "SWING_LOW")
        and l.price < entry_low
    ]
    targets.extend(sorted(sell_side, reverse=True))

    swing_lows = sorted(
        [s.price for s in swings if s.type == "LOW" and s.price < entry_low],
        reverse=True,
    )
    targets.extend(swing_lows)

    targets = sorted(set(targets), reverse=True)

    if risk > 0 and targets:
        adequate = [t for t in targets if (entry_low - t) >= risk * min_rr]
        if adequate:
            targets = adequate

    tp1 = targets[0] if len(targets) > 0 else None
    tp2 = targets[1] if len(targets) > 1 else None
    tp3 = targets[2] if len(targets) > 2 else None

    return (tp1, tp2, tp3)
