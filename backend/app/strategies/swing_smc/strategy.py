from __future__ import annotations
import logging
from typing import Literal
from app.strategies.swing_smc.models import (
    Candle,
    SwingPoint,
    TradeSetup,
)
from app.strategies.swing_smc.config import SwingSMCConfig
from app.strategies.swing_smc.swings import detect_swings
from app.strategies.swing_smc.structure import determine_structure
from app.strategies.swing_smc.liquidity import detect_liquidity, detect_sweeps
from app.strategies.swing_smc.fvg import detect_fvg, check_fvg_fill
from app.strategies.swing_smc.order_blocks import detect_order_blocks, check_ob_mitigation
from app.strategies.swing_smc.displacement import detect_displacement
from app.strategies.swing_smc.premium_discount import calculate_premium_discount
from app.strategies.swing_smc.setup import build_long_setup, build_short_setup
from app.strategies.swing_smc.validation import validate_setup

logger = logging.getLogger(__name__)


class SwingSMCStrategy:

    def __init__(self, config: SwingSMCConfig | None = None):
        self.config = config or SwingSMCConfig()

    def analyze(self, candles: list[Candle]) -> TradeSetup:
        if not self.config.is_valid_combo():
            logger.warning(
                f"Invalid timeframe combo: {self.config.htf}/{self.config.structure_tf}/{self.config.entry_tf}"
            )
            return TradeSetup(direction="NO_SIGNAL", reasons=["Invalid timeframe combination"])

        if len(candles) < self.config.swing_left + self.config.swing_right + 2:
            return TradeSetup(
                direction="NO_SIGNAL",
                reasons=[f"Insufficient data: {len(candles)} candles, need at least {self.config.swing_left + self.config.swing_right + 2}"],
            )

        candles = sorted(candles, key=lambda c: c.timestamp)

        atr = self._compute_atr(candles)
        if atr <= 0:
            return TradeSetup(direction="NO_SIGNAL", reasons=["ATR is zero or negative"])

        current_price = candles[-1].close

        swings = detect_swings(candles, self.config.swing_left, self.config.swing_right)
        if len(swings) < 3:
            return TradeSetup(
                direction="NO_SIGNAL",
                reasons=[f"Insufficient swing points: {len(swings)}, need at least 3"],
            )

        structure_events = determine_structure(swings)
        liquidity_levels = detect_liquidity(
            candles, swings, atr, self.config.liquidity_tolerance_atr
        )
        swept_levels = detect_sweeps(candles, liquidity_levels, lookback=20)
        fvgs = detect_fvg(
            candles, atr, self.config.fvg_min_atr, self.config.entry_tf
        )
        order_blocks = detect_order_blocks(
            candles, structure_events, atr,
            self.config.displacement_body_atr,
            self.config.displacement_body_ratio,
        )
        displacements = detect_displacement(
            candles, atr,
            self.config.displacement_body_atr,
            self.config.displacement_body_ratio,
        )
        has_displacement = len(displacements) > 0

        volume_confirms = self._check_volume(candles)

        pd = calculate_premium_discount(current_price, swings)

        htf_bias = self._determine_htf_bias(swings, structure_events)

        long_setup = build_long_setup(
            candles=candles,
            current_price=current_price,
            htf_bias=htf_bias,
            swings=swings,
            structure_events=structure_events,
            liquidity_levels=liquidity_levels,
            swept_levels=swept_levels,
            fvgs=fvgs,
            order_blocks=order_blocks,
            has_displacement=has_displacement,
            volume_confirms=volume_confirms,
            premium_discount=pd,
            atr=atr,
            config=self.config,
        )

        short_setup = build_short_setup(
            candles=candles,
            current_price=current_price,
            htf_bias=htf_bias,
            swings=swings,
            structure_events=structure_events,
            liquidity_levels=liquidity_levels,
            swept_levels=swept_levels,
            fvgs=fvgs,
            order_blocks=order_blocks,
            has_displacement=has_displacement,
            volume_confirms=volume_confirms,
            premium_discount=pd,
            atr=atr,
            config=self.config,
        )

        best = self._pick_best(long_setup, short_setup)
        best = validate_setup(best, current_price)

        if best.confidence < self.config.minimum_confidence and best.direction != "NO_SIGNAL":
            best.direction = "NO_SIGNAL"
            best.reasons.append(f"Confidence {best.confidence:.0f} below minimum {self.config.minimum_confidence}")

        self._log_result(best)

        return best

    def _compute_atr(self, candles: list[Candle]) -> float:
        period = self.config.atr_period
        if len(candles) < period + 1:
            period = max(1, len(candles) - 1)

        trs = []
        for i in range(1, len(candles)):
            c = candles[i]
            prev = candles[i - 1]
            tr = max(
                c.high - c.low,
                abs(c.high - prev.close),
                abs(c.low - prev.close),
            )
            trs.append(tr)

        if not trs:
            return 0.0

        window = trs[-period:]
        return sum(window) / len(window)

    def _determine_htf_bias(
        self,
        swings: list[SwingPoint],
        structure_events: list,
    ) -> str:
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

        bullish_choch = any(
            e.type == "CHOCH" and e.direction == "BULLISH" and e.confirmed
            for e in structure_events
        )
        bearish_choch = any(
            e.type == "CHOCH" and e.direction == "BEARISH" and e.confirmed
            for e in structure_events
        )

        if bullish_choch:
            return "BULLISH"
        if bearish_choch:
            return "BEARISH"

        return "NEUTRAL"

    def _check_volume(self, candles: list[Candle]) -> bool:
        if len(candles) < 20:
            return False

        volumes = [c.volume for c in candles[-20:]]
        avg_vol = sum(volumes) / len(volumes)

        if avg_vol <= 0:
            return False

        return candles[-1].volume > avg_vol * 1.2

    def _pick_best(self, long: TradeSetup, short: TradeSetup) -> TradeSetup:
        if long.direction == "NO_SIGNAL" and short.direction == "NO_SIGNAL":
            return long

        if long.direction != "NO_SIGNAL" and short.direction != "NO_SIGNAL":
            if long.confidence >= short.confidence:
                return long
            return short

        if long.direction != "NO_SIGNAL":
            return long
        return short

    def _log_result(self, setup: TradeSetup):
        if setup.direction == "NO_SIGNAL":
            logger.info(
                f"SWING_SMC: NO_SIGNAL | confidence={setup.confidence:.0f} | "
                f"reasons={setup.reasons}"
            )
        else:
            logger.info(
                f"SWING_SMC: {setup.direction} | bias={setup.market_bias} | "
                f"entry={setup.entry_low:.2f}-{setup.entry_high:.2f} | "
                f"sl={setup.stop_loss:.2f} | tp1={setup.take_profit_1:.2f} | "
                f"rr={setup.risk_reward:.2f} | confidence={setup.confidence:.0f}"
            )
