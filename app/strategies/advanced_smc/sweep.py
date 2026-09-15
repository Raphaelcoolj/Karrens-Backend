from __future__ import annotations
from app.strategies.advanced_smc.models import (
    Candle, StructureEvent, StructureLabel, SwingPoint
)


def move_structural_reference_after_sweep(
    events: list[StructureEvent],
    candles: list[Candle],
    labels: list[StructureLabel],
) -> list[StructureEvent]:
    for event in events:
        if event.swept and event.sweep_index is not None:
            sweep_candle = candles[event.sweep_index]
            if event.direction == "BULLISH":
                event.price = max(event.price, sweep_candle.high)
            else:
                event.price = min(event.price, sweep_candle.low)
    return events


def check_bos_sweep(
    bos_events: list[StructureEvent],
    candles: list[Candle],
    atr: float,
) -> list[StructureEvent]:
    swept = []
    for bos in bos_events:
        if bos.swept:
            continue
        for i in range(bos.index + 1, len(candles)):
            c = candles[i]
            if bos.direction == "BULLISH":
                if c.high > bos.price and c.close <= bos.price:
                    bos.swept = True
                    bos.sweep_index = i
                    swept.append(bos)
                    break
            else:
                if c.low < bos.price and c.close >= bos.price:
                    bos.swept = True
                    bos.sweep_index = i
                    swept.append(bos)
                    break
    return swept


def check_choch_sweep(
    choch_events: list[StructureEvent],
    candles: list[Candle],
    atr: float,
) -> list[StructureEvent]:
    swept = []
    for choch in choch_events:
        if choch.swept:
            continue
        for i in range(choch.index + 1, len(candles)):
            c = candles[i]
            if choch.direction == "BULLISH":
                if c.high > choch.price and c.close <= choch.price:
                    choch.swept = True
                    choch.sweep_index = i
                    swept.append(choch)
                    break
            else:
                if c.low < choch.price and c.close >= choch.price:
                    choch.swept = True
                    choch.sweep_index = i
                    swept.append(choch)
                    break
    return swept


def is_wick_sweep(candle: Candle, level: float, direction: str) -> bool:
    if direction == "ABOVE":
        return candle.high > level and candle.close <= level
    else:
        return candle.low < level and candle.close >= level
