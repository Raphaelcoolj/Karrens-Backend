from __future__ import annotations
from app.strategies.swing_smc.models import SwingPoint


def calculate_premium_discount(
    current_price: float,
    swings: list[SwingPoint],
) -> tuple[str, float, float]:
    highs = [s for s in swings if s.type == "HIGH"]
    lows = [s for s in swings if s.type == "LOW"]

    if not highs or not lows:
        return ("NEUTRAL", current_price, current_price)

    range_high = max(h.price for h in highs)
    range_low = min(l.price for l in lows)

    if range_high <= range_low:
        return ("NEUTRAL", range_high, range_low)

    equilibrium = (range_high + range_low) / 2

    if current_price < equilibrium:
        return ("DISCOUNT", equilibrium, range_low)
    elif current_price > equilibrium:
        return ("PREMIUM", range_high, equilibrium)
    else:
        return ("EQUILIBRIUM", range_high, range_low)
