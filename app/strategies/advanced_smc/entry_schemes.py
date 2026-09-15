from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from app.strategies.advanced_smc.models import (
    Candle, IDM, IFC, OrderBlock, FairValueGap, EntryZone, LiquidityLevel
)


EntryType = Literal["IDM_BASED", "IFC_BASED"]
EntryScheme = Literal[
    "SCHEME_1", "SCHEME_2", "SCHEME_3", "SCHEME_4",
    "SCHEME_5", "SCHEME_6", "SCHEME_7", "SCHEME_8",
]


@dataclass
class SchemeResult:
    found: bool
    entry_type: EntryType = ""
    entry_scheme: EntryScheme = ""
    entry_zone: EntryZone | None = None
    reason: str = ""


def try_scheme_1(
    candles: list[Candle],
    idms: list[IDM],
    ifcs: list[IFC],
    obs: list[OrderBlock],
    direction: str,
    atr: float,
) -> SchemeResult:
    for idm in idms:
        if not idm.swept or idm.direction != direction:
            continue
        if idm.sweep_index is None:
            continue

        for ob in obs:
            if ob.direction != direction:
                continue
            if ob.mitigated:
                continue
            if ob.source_candle_index > idm.sweep_index:
                continue

            zone = EntryZone(
                type=ob.ob_type if ob.ob_type in ("OB_IDM", "OB_EXT") else "OB_IDM",
                direction=direction,
                high=ob.high,
                low=ob.low,
                timestamp=ob.timestamp,
                index=ob.source_candle_index,
                reason=f"Block after IDM sweep at {idm.price:.2f}",
            )
            return SchemeResult(
                found=True,
                entry_type="IDM_BASED",
                entry_scheme="SCHEME_1",
                entry_zone=zone,
                reason=f"IDM swept → entry from block after IDM",
            )

    return SchemeResult(found=False)


def try_scheme_2(
    candles: list[Candle],
    idms: list[IDM],
    ifcs: list[IFC],
    direction: str,
    atr: float,
) -> SchemeResult:
    for idm in idms:
        if not idm.swept or idm.direction != direction:
            continue
        if idm.sweep_index is None:
            continue

        for ifc in ifcs:
            if ifc.direction != direction:
                continue
            if ifc.index == idm.sweep_index or abs(ifc.index - idm.sweep_index) <= 2:
                if ifc.swept_liquidity and ifc.closes_through:
                    zone = EntryZone(
                        type="IFC",
                        direction=direction,
                        high=ifc.high,
                        low=ifc.low,
                        timestamp=ifc.timestamp,
                        index=ifc.index,
                        reason=f"IFC grabbed IDM liquidity at {idm.price:.2f}",
                    )
                    return SchemeResult(
                        found=True,
                        entry_type="IFC_BASED",
                        entry_scheme="SCHEME_2",
                        entry_zone=zone,
                        reason=f"IDM swept by IFC → direct entry from IFC",
                    )

    return SchemeResult(found=False)


def try_scheme_3(
    candles: list[Candle],
    idms: list[IDM],
    ifcs: list[IFC],
    obs: list[OrderBlock],
    direction: str,
    atr: float,
) -> SchemeResult:
    new_idms = [idm for idm in idms if idm.direction == direction and idm.swept]
    if not new_idms:
        return SchemeResult(found=False)

    latest_idm = max(new_idms, key=lambda x: x.sweep_index or 0)
    result_1 = try_scheme_1(candles, [latest_idm], ifcs, obs, direction, atr)
    if result_1.found:
        result_1.entry_scheme = "SCHEME_3"
        result_1.reason = f"Missed move → new IDM → {result_1.reason}"
        return result_1

    result_2 = try_scheme_2(candles, [latest_idm], ifcs, direction, atr)
    if result_2.found:
        result_2.entry_scheme = "SCHEME_3"
        result_2.reason = f"Missed move → new IDM → {result_2.reason}"
        return result_2

    return SchemeResult(found=False)


def try_scheme_4(
    candles: list[Candle],
    ifcs: list[IFC],
    direction: str,
    atr: float,
) -> SchemeResult:
    for ifc in ifcs:
        if ifc.direction != direction:
            continue
        if not ifc.swept_liquidity:
            continue
        if not ifc.closes_through:
            continue

        zone = EntryZone(
            type="IFC",
            direction=direction,
            high=ifc.high,
            low=ifc.low,
            timestamp=ifc.timestamp,
            index=ifc.index,
            reason=f"Clean IFC sweep at POI",
        )
        return SchemeResult(
            found=True,
            entry_type="IFC_BASED",
            entry_scheme="SCHEME_4",
            entry_zone=zone,
            reason=f"Price overshot POI → IFC sweep → direct entry",
        )

    return SchemeResult(found=False)


def try_scheme_5(
    candles: list[Candle],
    obs: list[OrderBlock],
    idms: list[IDM],
    direction: str,
    atr: float,
) -> SchemeResult:
    trap_blocks = [ob for ob in obs if ob.ob_type == "TRAP" and ob.direction == direction]
    if not trap_blocks:
        return SchemeResult(found=False)

    return SchemeResult(
        found=False,
        reason="SMT/trap block detected but requires IFC confirmation nearby",
    )


def try_scheme_6(
    candles: list[Candle],
    obs: list[OrderBlock],
    ifcs: list[IFC],
    direction: str,
    atr: float,
) -> SchemeResult:
    trap_blocks = [ob for ob in obs if ob.ob_type == "TRAP" and ob.direction == direction]
    for trap in trap_blocks:
        for ifc in ifcs:
            if ifc.direction != direction:
                continue
            if not ifc.swept_liquidity:
                continue
            if abs(ifc.index - trap.source_candle_index) <= 5:
                zone = EntryZone(
                    type="SMT",
                    direction=direction,
                    high=ifc.high,
                    low=ifc.low,
                    timestamp=ifc.timestamp,
                    index=ifc.index,
                    reason=f"IFC swept SMT block at {trap.low:.2f}-{trap.high:.2f}",
                )
                return SchemeResult(
                    found=True,
                    entry_type="IFC_BASED",
                    entry_scheme="SCHEME_6",
                    entry_zone=zone,
                    reason=f"SMT block swept via IFC → entry from IFC",
                )

    return SchemeResult(found=False)


def try_scheme_7(
    candles: list[Candle],
    obs: list[OrderBlock],
    idms: list[IDM],
    direction: str,
    atr: float,
) -> SchemeResult:
    idm_blocks = [ob for ob in obs if ob.ob_type == "OB_IDM" and ob.direction == direction]
    if not idm_blocks:
        return SchemeResult(
            found=False,
            reason="No IDM blocks to transform into SMT pattern",
        )
    return SchemeResult(
        found=False,
        reason="Old IDM block detected but SMT transformation requires new IDM formation",
    )


def try_scheme_8(
    candles: list[Candle],
    obs: list[OrderBlock],
    ifcs: list[IFC],
    idms: list[IDM],
    direction: str,
    atr: float,
) -> SchemeResult:
    for ifc in ifcs:
        if ifc.direction != direction:
            continue
        if ifc.swept_liquidity and ifc.closes_through:
            trap_blocks = [ob for ob in obs if ob.ob_type == "TRAP" and ob.direction == direction]
            for trap in trap_blocks:
                if abs(ifc.index - trap.source_candle_index) <= 5:
                    zone = EntryZone(
                        type="SMT",
                        direction=direction,
                        high=trap.high,
                        low=trap.low,
                        timestamp=trap.timestamp,
                        index=trap.source_candle_index,
                        reason=f"IFC already grabbed liquidity at POI → SMT validated",
                    )
                    return SchemeResult(
                        found=True,
                        entry_type="IFC_BASED",
                        entry_scheme="SCHEME_8",
                        entry_zone=zone,
                        reason=f"Liquidity grabbed at POI before CHoCH → SMT valid immediately",
                    )

    return SchemeResult(found=False)


def evaluate_all_schemes(
    candles: list[Candle],
    idms: list[IDM],
    ifcs: list[IFC],
    obs: list[OrderBlock],
    direction: str,
    atr: float,
) -> SchemeResult:
    for try_fn in [
        lambda: try_scheme_1(candles, idms, ifcs, obs, direction, atr),
        lambda: try_scheme_2(candles, idms, ifcs, direction, atr),
        lambda: try_scheme_3(candles, idms, ifcs, obs, direction, atr),
        lambda: try_scheme_4(candles, ifcs, direction, atr),
        lambda: try_scheme_5(candles, obs, idms, direction, atr),
        lambda: try_scheme_6(candles, obs, ifcs, direction, atr),
        lambda: try_scheme_7(candles, obs, idms, direction, atr),
        lambda: try_scheme_8(candles, obs, ifcs, idms, direction, atr),
    ]:
        result = try_fn()
        if result.found:
            return result

    return SchemeResult(found=False, reason="No valid entry scheme found")
