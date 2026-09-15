from __future__ import annotations
from app.strategies.advanced_smc.models import Candle, OrderFlow


def detect_order_flow(
    candles: list[Candle],
    pullback_indices: list[int],
    direction: str,
) -> OrderFlow | None:
    if not pullback_indices or len(candles) < 2:
        return None

    valid_pbs = [i for i in pullback_indices if 0 <= i < len(candles)]
    if not valid_pbs:
        return None

    last_pb_idx = max(valid_pbs)

    for i in range(last_pb_idx, -1, -1):
        c = candles[i]
        is_liquidity_grab = False

        if i > 0:
            prev = candles[i - 1]
            if c.high > prev.high and c.low < prev.low:
                is_liquidity_grab = True
            elif c.high > prev.high and c.close < prev.high:
                is_liquidity_grab = True
            elif c.low < prev.low and c.close > prev.low:
                is_liquidity_grab = True

        if is_liquidity_grab:
            return OrderFlow(
                direction=direction,
                high=c.high,
                low=c.low,
                timestamp=c.timestamp,
                source_index=i,
                strength=1.0,
            )

    last_c = candles[last_pb_idx]
    return OrderFlow(
        direction=direction,
        high=last_c.high,
        low=last_c.low,
        timestamp=last_c.timestamp,
        source_index=last_pb_idx,
    )
