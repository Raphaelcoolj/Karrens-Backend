from __future__ import annotations
from app.strategies.advanced_smc.models import (
    Candle, SwingPoint, StructureLabel, StructureEvent, IDM
)


def label_swings(swings: list[SwingPoint]) -> list[StructureLabel]:
    if len(swings) < 2:
        return []

    labels: list[StructureLabel] = []
    for i, s in enumerate(swings):
        if i == 0:
            lbl_type = "HH" if s.type == "HIGH" else "LL"
            labels.append(StructureLabel(
                type=lbl_type, index=s.index, timestamp=s.timestamp,
                price=s.price, confirmed=True,
            ))
            continue

        if s.type == "HIGH":
            prev_high = None
            for j in range(i - 1, -1, -1):
                if swings[j].type == "HIGH":
                    prev_high = swings[j]
                    break
            if prev_high:
                lbl_type = "HH" if s.price > prev_high.price else "LH"
            else:
                lbl_type = "HH"
        else:
            prev_low = None
            for j in range(i - 1, -1, -1):
                if swings[j].type == "LOW":
                    prev_low = swings[j]
                    break
            if prev_low:
                lbl_type = "LL" if s.price < prev_low.price else "HL"
            else:
                lbl_type = "LL"

        labels.append(StructureLabel(
            type=lbl_type, index=s.index, timestamp=s.timestamp,
            price=s.price, confirmed=True,
        ))

    return labels


def detect_bos(
    labels: list[StructureLabel],
    candles: list[Candle],
) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    if len(labels) < 2:
        return events

    for i in range(1, len(labels)):
        curr = labels[i]
        prev = labels[i - 1]

        if curr.type == "HH" and prev.type == "HH":
            if curr.price > prev.price:
                events.append(StructureEvent(
                    type="BOS", direction="BULLISH",
                    price=prev.price, timestamp=curr.timestamp,
                    index=curr.index, confirmed=True,
                ))
        elif curr.type == "LL" and prev.type == "LL":
            if curr.price < prev.price:
                events.append(StructureEvent(
                    type="BOS", direction="BEARISH",
                    price=prev.price, timestamp=curr.timestamp,
                    index=curr.index, confirmed=True,
                ))

    return events


def detect_choch(
    labels: list[StructureLabel],
    candles: list[Candle],
) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    if len(labels) < 3:
        return events

    for i in range(2, len(labels)):
        curr = labels[i]

        if curr.type == "HL":
            prev_lh = None
            for j in range(i - 1, -1, -1):
                if labels[j].type == "LH":
                    prev_lh = labels[j]
                    break
            if prev_lh and curr.price > prev_lh.price:
                events.append(StructureEvent(
                    type="CHOCH", direction="BULLISH",
                    price=prev_lh.price, timestamp=curr.timestamp,
                    index=curr.index, confirmed=True,
                ))

        elif curr.type == "LH":
            prev_hl = None
            for j in range(i - 1, -1, -1):
                if labels[j].type == "HL":
                    prev_hl = labels[j]
                    break
            if prev_hl and curr.price < prev_hl.price:
                events.append(StructureEvent(
                    type="CHOCH", direction="BEARISH",
                    price=prev_hl.price, timestamp=curr.timestamp,
                    index=curr.index, confirmed=True,
                ))

    return events


def detect_idm(
    labels: list[StructureLabel],
    swings: list[SwingPoint],
    candles: list[Candle],
) -> list[IDM]:
    idms: list[IDM] = []
    if len(labels) < 2:
        return idms

    bos_events = detect_bos(labels, candles)

    for bos in bos_events:
        if bos.direction == "BULLISH":
            pullbacks = [
                s for s in swings
                if s.type == "LOW" and s.index < bos.index
            ]
            if pullbacks:
                last_pb = max(pullbacks, key=lambda s: s.index)
                idms.append(IDM(
                    index=last_pb.index,
                    timestamp=last_pb.timestamp,
                    price=last_pb.price,
                    direction="BULLISH",
                ))
        else:
            pullbacks = [
                s for s in swings
                if s.type == "HIGH" and s.index < bos.index
            ]
            if pullbacks:
                last_pb = max(pullbacks, key=lambda s: s.index)
                idms.append(IDM(
                    index=last_pb.index,
                    timestamp=last_pb.timestamp,
                    price=last_pb.price,
                    direction="BEARISH",
                ))

    return idms


def check_idm_sweep(
    idms: list[IDM],
    candles: list[Candle],
    atr: float,
    tolerance_atr: float = 0.1,
) -> list[IDM]:
    tolerance = atr * tolerance_atr
    swept = []
    for idm in idms:
        if idm.swept:
            continue
        for i in range(idm.index + 1, len(candles)):
            c = candles[i]
            if idm.direction == "BULLISH":
                if c.low <= idm.price + tolerance:
                    idm.swept = True
                    idm.sweep_index = i
                    idm.sweep_timestamp = c.timestamp
                    swept.append(idm)
                    break
            else:
                if c.high >= idm.price - tolerance:
                    idm.swept = True
                    idm.sweep_index = i
                    idm.sweep_timestamp = c.timestamp
                    swept.append(idm)
                    break
    return swept
