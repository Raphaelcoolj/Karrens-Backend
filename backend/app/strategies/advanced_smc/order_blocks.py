from __future__ import annotations
from app.strategies.advanced_smc.models import (
    Candle, StructureEvent, IDM, OrderBlock, FairValueGap, IFC
)


def detect_order_blocks(
    candles: list[Candle],
    bos_events: list[StructureEvent],
    idms: list[IDM],
    fvgs: list[FairValueGap],
    ifcs: list[IFC],
    atr: float,
    body_atr: float = 0.8,
    body_ratio: float = 0.5,
) -> list[OrderBlock]:
    obs: list[OrderBlock] = []

    for bos in bos_events:
        if bos.direction == "BULLISH":
            ob = _find_bullish_ob(candles, bos, fvgs, ifcs, atr, body_atr, body_ratio)
            if ob:
                obs.append(ob)
        else:
            ob = _find_bearish_ob(candles, bos, fvgs, ifcs, atr, body_atr, body_ratio)
            if ob:
                obs.append(ob)

    ob_idm = _classify_ob_idm(obs, idms, bos_events, candles)
    ob_ext = _classify_ob_ext(obs, idms, bos_events, candles)
    _mark_trap_blocks(obs, ob_idm, ob_ext)

    return obs


def _find_bullish_ob(
    candles: list[Candle],
    bos: StructureEvent,
    fvgs: list[FairValueGap],
    ifcs: list[IFC],
    atr: float,
    body_atr: float,
    body_ratio: float,
) -> OrderBlock | None:
    idx = bos.index
    if idx < 1 or idx >= len(candles):
        return None

    for i in range(idx - 1, max(idx - 8, -1), -1):
        c = candles[i]
        body = abs(c.close - c.open)
        rng = c.high - c.low
        if rng <= 0:
            continue

        is_bearish = c.close < c.open
        has_body = body >= atr * body_atr
        good_ratio = (body / rng) >= body_ratio

        if is_bearish and has_body and good_ratio:
            has_imbalance = _check_associated_imbalance(candles, i, fvgs, "BULLISH")
            has_ifc = _check_associated_ifc(ifcs, i, "BULLISH")

            return OrderBlock(
                direction="BULLISH",
                high=c.high,
                low=c.low,
                timestamp=c.timestamp,
                source_candle_index=i,
                strength=body / atr if atr > 0 else 0,
                has_imbalance=has_imbalance or has_ifc,
                is_ifc=has_ifc,
            )

    return None


def _find_bearish_ob(
    candles: list[Candle],
    bos: StructureEvent,
    fvgs: list[FairValueGap],
    ifcs: list[IFC],
    atr: float,
    body_atr: float,
    body_ratio: float,
) -> OrderBlock | None:
    idx = bos.index
    if idx < 1 or idx >= len(candles):
        return None

    for i in range(idx - 1, max(idx - 8, -1), -1):
        c = candles[i]
        body = abs(c.close - c.open)
        rng = c.high - c.low
        if rng <= 0:
            continue

        is_bullish = c.close > c.open
        has_body = body >= atr * body_atr
        good_ratio = (body / rng) >= body_ratio

        if is_bullish and has_body and good_ratio:
            has_imbalance = _check_associated_imbalance(candles, i, fvgs, "BEARISH")
            has_ifc = _check_associated_ifc(ifcs, i, "BEARISH")

            return OrderBlock(
                direction="BEARISH",
                high=c.high,
                low=c.low,
                timestamp=c.timestamp,
                source_candle_index=i,
                strength=body / atr if atr > 0 else 0,
                has_imbalance=has_imbalance or has_ifc,
                is_ifc=has_ifc,
            )

    return None


def _check_associated_imbalance(
    candles: list[Candle],
    ob_index: int,
    fvgs: list[FairValueGap],
    direction: str,
) -> bool:
    for fvg in fvgs:
        if fvg.direction != direction:
            continue
        if abs(fvg.source_index - ob_index) <= 3:
            return True
    return False


def _check_associated_ifc(
    ifcs: list[IFC],
    ob_index: int,
    direction: str,
) -> bool:
    for ifc in ifcs:
        if ifc.direction != direction:
            continue
        if abs(ifc.index - ob_index) <= 3:
            return True
    return False


def _classify_ob_idm(
    obs: list[OrderBlock],
    idms: list[IDM],
    bos_events: list[StructureEvent],
    candles: list[Candle],
) -> list[OrderBlock]:
    idm_prices = {idm.price for idm in idms}
    result = []
    for ob in obs:
        for idm in idms:
            if idm.direction == ob.direction:
                if ob.source_candle_index <= idm.index:
                    ob.ob_type = "OB_IDM"
                    result.append(ob)
                    break
    return result


def _classify_ob_ext(
    obs: list[OrderBlock],
    idms: list[IDM],
    bos_events: list[StructureEvent],
    candles: list[Candle],
) -> list[OrderBlock]:
    result = []
    for ob in obs:
        if ob.ob_type == "RAW":
            ob.ob_type = "OB_EXT"
            result.append(ob)
    return result


def _mark_trap_blocks(
    obs: list[OrderBlock],
    ob_idm: list[OrderBlock],
    ob_ext: list[OrderBlock],
):
    idm_indices = {o.source_candle_index for o in ob_idm}
    ext_indices = {o.source_candle_index for o in ob_ext}

    for ob in obs:
        if ob.source_candle_index not in idm_indices and ob.source_candle_index not in ext_indices:
            if ob.ob_type == "RAW":
                ob.ob_type = "TRAP"


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
