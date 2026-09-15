from __future__ import annotations
from app.strategies.swing_smc.models import Candle, SwingPoint, StructureEvent


def determine_structure(
    swings: list[SwingPoint],
) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    if len(swings) < 3:
        return events

    highs = [s for s in swings if s.type == "HIGH"]
    lows = [s for s in swings if s.type == "LOW"]

    trend = _detect_trend(swings)

    if trend == "BULLISH":
        events.extend(_detect_bullish_bos(highs, lows, swings))
        events.extend(_detect_choch_bearish_to_bullish(swings))
    elif trend == "BEARISH":
        events.extend(_detect_bearish_bos(highs, lows, swings))
        events.extend(_detect_choch_bullish_to_bearish(swings))
    else:
        events.extend(_detect_bullish_bos(highs, lows, swings))
        events.extend(_detect_bearish_bos(highs, lows, swings))
        events.extend(_detect_choch_bearish_to_bullish(swings))
        events.extend(_detect_choch_bullish_to_bearish(swings))

    return events


def _detect_trend(swings: list[SwingPoint]) -> str:
    highs = [s for s in swings if s.type == "HIGH"]
    lows = [s for s in swings if s.type == "LOW"]

    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1].price > highs[-2].price
        hl = lows[-1].price > lows[-2].price
        ll = lows[-1].price < lows[-2].price
        lh = highs[-1].price < highs[-2].price

        if hh and hl:
            return "BULLISH"
        if ll and lh:
            return "BEARISH"

    return "NEUTRAL"


def _detect_bullish_bos(
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    all_swings: list[SwingPoint],
) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    if len(highs) < 2:
        return events

    for i in range(1, len(highs)):
        prev = highs[i - 1]
        curr = highs[i]
        if curr.price > prev.price:
            events.append(StructureEvent(
                type="BOS",
                direction="BULLISH",
                price=prev.price,
                timestamp=curr.timestamp,
                broken_swing_index=prev.index,
                confirmed=True,
            ))

    return events


def _detect_bearish_bos(
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    all_swings: list[SwingPoint],
) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    if len(lows) < 2:
        return events

    for i in range(1, len(lows)):
        prev = lows[i - 1]
        curr = lows[i]
        if curr.price < prev.price:
            events.append(StructureEvent(
                type="BOS",
                direction="BEARISH",
                price=prev.price,
                timestamp=curr.timestamp,
                broken_swing_index=prev.index,
                confirmed=True,
            ))

    return events


def _detect_choch_bearish_to_bullish(
    swings: list[SwingPoint],
) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    highs = [s for s in swings if s.type == "HIGH"]
    lows = [s for s in swings if s.type == "LOW"]

    if len(highs) < 2 or len(lows) < 2:
        return events

    bearish_lh = None
    for i in range(len(highs) - 1, -1, -1):
        if i > 0 and highs[i].price < highs[i - 1].price:
            bearish_lh = highs[i]
            break

    if bearish_lh is None:
        return events

    recent_bullish = [h for h in highs if h.timestamp > bearish_lh.timestamp]
    for h in recent_bullish:
        if h.price > bearish_lh.price:
            events.append(StructureEvent(
                type="CHOCH",
                direction="BULLISH",
                price=bearish_lh.price,
                timestamp=h.timestamp,
                broken_swing_index=bearish_lh.index,
                confirmed=True,
            ))
            break

    return events


def _detect_choch_bullish_to_bearish(
    swings: list[SwingPoint],
) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    highs = [s for s in swings if s.type == "HIGH"]
    lows = [s for s in swings if s.type == "LOW"]

    if len(highs) < 2 or len(lows) < 2:
        return events

    bullish_hl = None
    for i in range(len(lows) - 1, -1, -1):
        if i > 0 and lows[i].price > lows[i - 1].price:
            bullish_hl = lows[i]
            break

    if bullish_hl is None:
        return events

    recent_bearish = [l for l in lows if l.timestamp > bullish_hl.timestamp]
    for l in recent_bearish:
        if l.price < bullish_hl.price:
            events.append(StructureEvent(
                type="CHOCH",
                direction="BEARISH",
                price=bullish_hl.price,
                timestamp=l.timestamp,
                broken_swing_index=bullish_hl.index,
                confirmed=True,
            ))
            break

    return events
