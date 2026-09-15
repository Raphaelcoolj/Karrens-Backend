from __future__ import annotations
import logging
from app.strategies.advanced_smc.models import (
    Candle, AdvancedSMCSetup, StructureLabel, StructureEvent, IDM,
    LiquidityLevel, FairValueGap, OrderBlock, OrderFlow, IFC, EntryZone,
)
from app.strategies.advanced_smc.config import AdvancedSMCConfig
from app.strategies.advanced_smc.structure import (
    label_swings, detect_bos, detect_choch, detect_idm, check_idm_sweep,
)
from app.strategies.advanced_smc.sweep import (
    check_bos_sweep, check_choch_sweep, move_structural_reference_after_sweep,
)
from app.strategies.advanced_smc.fvg import detect_fvg, check_fvg_fill
from app.strategies.advanced_smc.order_blocks import detect_order_blocks, check_ob_mitigation
from app.strategies.advanced_smc.order_flow import detect_order_flow
from app.strategies.advanced_smc.ifc import detect_ifc
from app.strategies.advanced_smc.liquidity import detect_liquidity, detect_sweeps
from app.strategies.advanced_smc.pullback import detect_pullbacks_via_liquidity_grab
from app.strategies.advanced_smc.entry_schemes import evaluate_all_schemes
from app.strategies.advanced_smc.scoring import ScoringInput, calculate_score
from app.strategies.swing_smc.swings import detect_swings

logger = logging.getLogger(__name__)


class AdvancedSMCStrategy:

    def __init__(self, config: AdvancedSMCConfig | None = None):
        self.config = config or AdvancedSMCConfig()

    def analyze(self, candles: list[Candle]) -> AdvancedSMCSetup:
        setup = AdvancedSMCSetup(
            symbol="",
            htf_timeframe=self.config.htf,
            middle_timeframe=self.config.middle_tf,
            ltf_timeframe=self.config.ltf,
        )

        if not self.config.is_valid_combo():
            setup.reasons.append("Invalid timeframe combination")
            return setup

        min_candles = self.config.swing_left + self.config.swing_right + 10
        if len(candles) < min_candles:
            setup.reasons.append(f"Insufficient data: {len(candles)} candles, need {min_candles}")
            return setup

        candles = sorted(candles, key=lambda c: c.timestamp)
        atr = self._compute_atr(candles)
        if atr <= 0:
            setup.reasons.append("ATR is zero")
            return setup

        current_price = candles[-1].close

        swings = detect_swings(candles, self.config.swing_left, self.config.swing_right)
        if len(swings) < 3:
            setup.reasons.append(f"Insufficient swings: {len(swings)}")
            return setup

        labels = label_swings(swings)
        setup.middle_labels = labels

        bos_events = detect_bos(labels, candles)
        choch_events = detect_choch(labels, candles)
        idms = detect_idm(labels, swings, candles)

        bos_swept = check_bos_sweep(bos_events, candles, atr)
        choch_swept = check_choch_sweep(choch_events, candles, atr)
        idm_swept = check_idm_sweep(idms, candles, atr, self.config.liquidity_tolerance_atr)

        move_structural_reference_after_sweep(bos_events, candles, labels)
        move_structural_reference_after_sweep(choch_events, candles, labels)

        fvgs = detect_fvg(candles, atr, self.config.fvg_min_atr, self.config.middle_tf) if self.config.fvg_enabled else []
        ifcs = detect_ifc(candles, atr, self.config.ifc_wick_ratio, self.config.ifc_sweep_atr)

        obs = detect_order_blocks(
            candles, bos_events, idms, fvgs, ifcs, atr,
            self.config.ob_body_atr, self.config.ob_body_ratio,
        )

        pullbacks = detect_pullbacks_via_liquidity_grab(candles, 0, len(candles) - 1)
        order_flow = detect_order_flow(candles, pullbacks, self._determine_bias(labels))

        liquidity_levels = detect_liquidity(candles, swings, atr, self.config)
        swept_liquidity = detect_sweeps(candles, liquidity_levels, lookback=20)

        bias = self._determine_bias(labels)
        setup.market_bias = bias
        setup.structure_state = self._describe_structure(labels, bos_events, choch_events, idms)
        setup.bos_events = bos_events
        setup.choch_events = choch_events
        setup.idm_events = idms
        setup.liquidity_levels = liquidity_levels
        setup.liquidity_sweeps = swept_liquidity
        setup.fvgs = fvgs
        setup.order_blocks = obs
        setup.order_flow = [order_flow] if order_flow else []
        setup.ifcs = ifcs

        direction = self._determine_direction(bias, bos_events, choch_events)
        if direction == "NO_SIGNAL":
            setup.direction = "NO_SIGNAL"
            setup.reasons.append("No clear directional bias from structure")
            return setup

        scheme_result = evaluate_all_schemes(candles, idms, ifcs, obs, direction, atr)

        if not scheme_result.found:
            setup.direction = "NO_SIGNAL"
            setup.reasons.append("No valid entry scheme found")
            setup.reasons.append(scheme_result.reason)
            return setup

        zone = scheme_result.entry_zone
        if zone is None:
            setup.direction = "NO_SIGNAL"
            setup.reasons.append("Entry zone is None")
            return setup

        setup.poi_type = zone.type
        setup.poi_zone = zone
        setup.entry_type = scheme_result.entry_type
        setup.entry_scheme = scheme_result.entry_scheme

        setup.entry_low = zone.low
        setup.entry_high = zone.high

        sl = self._calc_stop_loss(zone, direction, candles, atr)
        setup.stop_loss = sl

        risk = self._calc_risk(zone, sl, direction)
        tps = self._calc_take_profits(zone, direction, risk, liquidity_levels, candles)
        setup.take_profit_1 = tps[0]
        setup.take_profit_2 = tps[1]
        setup.take_profit_3 = tps[2]

        rr = self._calc_rr(zone, sl, tps[0], direction)
        setup.risk_reward = rr

        if rr is not None and rr < self.config.minimum_rr:
            setup.direction = "NO_SIGNAL"
            setup.reasons.append(f"R:R {rr:.2f} below minimum {self.config.minimum_rr}")
            return setup

        scoring = ScoringInput(
            htf_aligned=bias != "NEUTRAL",
            has_bos=len(bos_events) > 0,
            has_choch=len(choch_events) > 0,
            idm_swept=len(idm_swept) > 0,
            ifc_confirms=len(ifcs) > 0,
            has_order_block=any(o.has_imbalance for o in obs if o.direction == ("BULLISH" if direction == "LONG" else "BEARISH")),
            has_fvg=len(fvgs) > 0,
            liquidity_event=len(swept_liquidity) > 0,
            entry_scheme_valid=True,
            rr_strong=rr is not None and rr >= 5.0,
        )

        confidence = calculate_score(scoring)
        setup.confidence = confidence
        setup.direction = direction

        if confidence < self.config.minimum_confidence:
            setup.direction = "NO_SIGNAL"
            setup.reasons.append(f"Confidence {confidence:.0f} below minimum {self.config.minimum_confidence}")
            return setup

        setup.reasons = self._build_reasons(setup, scheme_result, idm_swept, swept_liquidity)
        setup.invalidation_conditions = self._build_invalidation(zone, direction, obs)

        self._log_result(setup)
        return setup

    def _compute_atr(self, candles: list[Candle]) -> float:
        period = self.config.atr_period
        if len(candles) < period + 1:
            period = max(1, len(candles) - 1)

        trs = []
        for i in range(1, len(candles)):
            c = candles[i]
            prev = candles[i - 1]
            tr = max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
            trs.append(tr)

        if not trs:
            return 0.0

        window = trs[-period:]
        return sum(window) / len(window)

    def _determine_bias(self, labels: list[StructureLabel]) -> str:
        if not labels:
            return "NEUTRAL"

        recent = labels[-5:]
        hh_count = sum(1 for l in recent if l.type == "HH")
        hl_count = sum(1 for l in recent if l.type == "HL")
        ll_count = sum(1 for l in recent if l.type == "LL")
        lh_count = sum(1 for l in recent if l.type == "LH")

        bullish = hh_count + hl_count
        bearish = ll_count + lh_count

        if bullish > bearish and bullish >= 2:
            return "BULLISH"
        elif bearish > bullish and bearish >= 2:
            return "BEARISH"
        return "NEUTRAL"

    def _determine_direction(
        self,
        bias: str,
        bos_events: list[StructureEvent],
        choch_events: list[StructureEvent],
    ) -> str:
        if bias == "BULLISH":
            bullish_structure = any(e.direction == "BULLISH" and e.confirmed for e in bos_events)
            bullish_choch = any(e.direction == "BULLISH" and e.confirmed for e in choch_events)
            if bullish_structure or bullish_choch:
                return "LONG"
        elif bias == "BEARISH":
            bearish_structure = any(e.direction == "BEARISH" and e.confirmed for e in bos_events)
            bearish_choch = any(e.direction == "BEARISH" and e.confirmed for e in choch_events)
            if bearish_structure or bearish_choch:
                return "SHORT"
        return "NO_SIGNAL"

    def _describe_structure(
        self,
        labels: list[StructureLabel],
        bos_events: list[StructureEvent],
        choch_events: list[StructureEvent],
        idms: list[IDM],
    ) -> str:
        recent_labels = [l.type for l in labels[-5:]]
        bos_count = len(bos_events)
        choch_count = len(choch_events)
        idm_count = len(idms)
        idm_swept = sum(1 for i in idms if i.swept)
        return (
            f"Structure: {' → '.join(recent_labels)} | "
            f"BOS: {bos_count} | CHoCH: {choch_count} | "
            f"IDM: {idm_count} (swept: {idm_swept})"
        )

    def _calc_stop_loss(
        self,
        zone: EntryZone,
        direction: str,
        candles: list[Candle],
        atr: float,
    ) -> float:
        buffer = atr * 0.1

        if direction == "LONG":
            return zone.low - buffer
        else:
            return zone.high + buffer

    def _calc_risk(self, zone: EntryZone, sl: float, direction: str) -> float:
        entry_mid = (zone.high + zone.low) / 2
        if direction == "LONG":
            return entry_mid - sl
        else:
            return sl - entry_mid

    def _calc_take_profits(
        self,
        zone: EntryZone,
        direction: str,
        risk: float,
        liquidity_levels: list[LiquidityLevel],
        candles: list[Candle],
    ) -> tuple[float | None, float | None, float | None]:
        entry_mid = (zone.high + zone.low) / 2
        min_rr = self.config.minimum_rr if self.config.exit_mode == "CONSERVATIVE" else 2.0

        targets: list[float] = []

        if direction == "LONG":
            for l in liquidity_levels:
                if l.type in ("EQUAL_HIGH", "PDH", "ASIAN_HIGH", "LONDON_HIGH", "NY_HIGH", "SWING_HIGH"):
                    if l.price > entry_mid:
                        targets.append(l.price)

            for c in candles[-50:]:
                if c.high > entry_mid:
                    targets.append(c.high)

            targets = sorted(set(targets))
            if risk > 0:
                adequate = [t for t in targets if (t - entry_mid) >= risk * min_rr]
                if adequate:
                    targets = adequate
        else:
            for l in liquidity_levels:
                if l.type in ("EQUAL_LOW", "PDL", "ASIAN_LOW", "LONDON_LOW", "NY_LOW", "SWING_LOW"):
                    if l.price < entry_mid:
                        targets.append(l.price)

            for c in candles[-50:]:
                if c.low < entry_mid:
                    targets.append(c.low)

            targets = sorted(set(targets), reverse=True)
            if risk > 0:
                adequate = [t for t in targets if (entry_mid - t) >= risk * min_rr]
                if adequate:
                    targets = adequate

        tp1 = targets[0] if len(targets) > 0 else None
        tp2 = targets[1] if len(targets) > 1 else None
        tp3 = targets[2] if len(targets) > 2 else None

        return (tp1, tp2, tp3)

    def _calc_rr(
        self,
        zone: EntryZone,
        sl: float,
        tp: float | None,
        direction: str,
    ) -> float | None:
        if tp is None:
            return None

        entry_mid = (zone.high + zone.low) / 2

        if direction == "LONG":
            risk = entry_mid - sl
            reward = tp - entry_mid
        else:
            risk = sl - entry_mid
            reward = entry_mid - tp

        if risk <= 0:
            return None

        return round(reward / risk, 2)

    def _build_reasons(
        self,
        setup: AdvancedSMCSetup,
        scheme_result,
        idm_swept: list[IDM],
        swept_liquidity: list[LiquidityLevel],
    ) -> list[str]:
        reasons = []

        if setup.market_bias == "BULLISH":
            reasons.append("HTF bias is bullish")
        elif setup.market_bias == "BEARISH":
            reasons.append("HTF bias is bearish")

        if setup.bos_events:
            reasons.append(f"Bullish BOS confirmed" if setup.bos_events[0].direction == "BULLISH" else "Bearish BOS confirmed")

        if setup.choch_events:
            reasons.append(f"Bullish CHoCH confirmed" if setup.choch_events[0].direction == "BULLISH" else "Bearish CHoCH confirmed")

        if idm_swept:
            reasons.append(f"IDM liquidity swept at {idm_swept[0].price:.2f}")

        if swept_liquidity:
            reasons.append(f"Liquidity sweep detected")

        if setup.poi_type:
            reasons.append(f"POI type: {setup.poi_type}")

        if setup.entry_scheme:
            reasons.append(f"Entry scheme: {setup.entry_scheme}")

        reasons.append(scheme_result.reason)

        return reasons

    def _build_invalidation(
        self,
        zone: EntryZone,
        direction: str,
        obs: list[OrderBlock],
    ) -> list[str]:
        invalidation = []

        if direction == "LONG":
            invalidation.append(f"Price closes below entry zone low {zone.low:.2f}")
        else:
            invalidation.append(f"Price closes above entry zone high {zone.high:.2f}")

        for ob in obs:
            if ob.direction == ("BULLISH" if direction == "LONG" else "BEARISH"):
                if ob.ob_type in ("OB_IDM", "OB_EXT"):
                    if direction == "LONG":
                        invalidation.append(f"Price closes below OB low {ob.low:.2f}")
                    else:
                        invalidation.append(f"Price closes above OB high {ob.high:.2f}")

        return invalidation

    def _log_result(self, setup: AdvancedSMCSetup):
        if setup.direction == "NO_SIGNAL":
            logger.info(
                f"ADVANCED_SMC: NO_SIGNAL | bias={setup.market_bias} | "
                f"conf={setup.confidence:.0f} | reasons={setup.reasons[:3]}"
            )
        else:
            logger.info(
                f"ADVANCED_SMC: {setup.direction} | bias={setup.market_bias} | "
                f"entry={setup.entry_low:.2f}-{setup.entry_high:.2f} | "
                f"sl={setup.stop_loss:.2f} | tp1={setup.take_profit_1} | "
                f"rr={setup.risk_reward} | scheme={setup.entry_scheme} | "
                f"conf={setup.confidence:.0f}"
            )
