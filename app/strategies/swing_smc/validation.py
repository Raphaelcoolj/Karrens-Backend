from __future__ import annotations
from app.strategies.swing_smc.models import TradeSetup


def validate_setup(setup: TradeSetup, current_price: float) -> TradeSetup:
    if setup.direction == "NO_SIGNAL":
        return setup

    if setup.entry_low is None or setup.entry_high is None:
        setup.direction = "NO_SIGNAL"
        setup.reasons.append("Missing entry zone")
        return setup

    if setup.stop_loss is None:
        setup.direction = "NO_SIGNAL"
        setup.reasons.append("Missing stop loss")
        return setup

    if setup.take_profit_1 is None:
        setup.direction = "NO_SIGNAL"
        setup.reasons.append("Missing take profit")
        return setup

    if setup.direction == "LONG":
        if setup.stop_loss >= setup.entry_low:
            setup.direction = "NO_SIGNAL"
            setup.reasons.append("Stop loss above entry zone for LONG")
            return setup
        if setup.take_profit_1 <= setup.entry_high:
            setup.direction = "NO_SIGNAL"
            setup.reasons.append("Take profit below entry zone for LONG")
            return setup

        risk = setup.entry_low - setup.stop_loss
        reward = setup.take_profit_1 - setup.entry_high
    else:
        if setup.stop_loss <= setup.entry_high:
            setup.direction = "NO_SIGNAL"
            setup.reasons.append("Stop loss below entry zone for SHORT")
            return setup
        if setup.take_profit_1 >= setup.entry_low:
            setup.direction = "NO_SIGNAL"
            setup.reasons.append("Take profit above entry zone for SHORT")
            return setup

        risk = setup.stop_loss - setup.entry_high
        reward = setup.entry_low - setup.take_profit_1

    if risk <= 0:
        setup.direction = "NO_SIGNAL"
        setup.reasons.append("Invalid risk calculation")
        return setup

    rr = round(reward / risk, 2)
    setup.risk_reward = rr

    if rr < 2.0:
        setup.direction = "NO_SIGNAL"
        setup.reasons.append(f"R:R {rr} below minimum 2.0")
        return setup

    entry_mid = (setup.entry_low + setup.entry_high) / 2
    if abs(entry_mid - current_price) / current_price > 0.05:
        setup.invalidation_conditions.append("Entry zone too far from current price")

    return setup
