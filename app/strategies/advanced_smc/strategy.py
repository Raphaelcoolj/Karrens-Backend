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
from app.strategies.advanced_smc.scoring import ScoringInput, calculate_score, calculate_assessment_score
from app.strategies.swing_smc.swings import detect_swings

logger = logging.getLogger(__name__)


REJECTION_NO_DATA = "INSUFFICIENT_DATA"
REJECTION_NO_SWINGS = "NO_STRUCTURE"
REJECTION_NO_BOS = "NO_BOS"
REJECTION_NO_CHOCH = "NO_CHOCH"
REJECTION_NO_IDM = "NO_IDM"
REJECTION_IDM_NOT_SWEPT = "IDM_NOT_SWEPT"
REJECTION_NO_LIQUIDITY = "NO_LIQUIDITY"
REJECTION_NO_POI = "NO_POI"
REJECTION_POI_NOT_REACHED = "POI_NOT_REACHED"
REJECTION_NO_ENTRY = "NO_ENTRY_SCHEME"
REJECTION_INVALID_RR = "INVALID_RR"
REJECTION_LOW_CONFIDENCE = "LOW_CONFIDENCE"
REJECTION_ATR_ZERO = "ATR_ZERO"
REJECTION_INVALID_CONFIG = "TIMEFRAME_INVALID"


class AdvancedSMCStrategy:

    def __init__(self, config: AdvancedSMCConfig | None = None):
        self.config = config or AdvancedSMCConfig()

    def analyze(
        self,
        htf_candles: list[Candle] | None = None,
        middle_candles: list[Candle] | None = None,
        ltf_candles: list[Candle] | None = None,
        candles: list[Candle] | None = None,
    ) -> AdvancedSMCSetup:
        if candles is not None and htf_candles is None:
            htf_candles = candles
            middle_candles = candles
            ltf_candles = candles

        if middle_candles is None:
            middle_candles = []
        if htf_candles is None:
            htf_candles = []
        if ltf_candles is None:
            ltf_candles = []

        setup = AdvancedSMCSetup(
            symbol="",
            htf_timeframe=self.config.htf,
            middle_timeframe=self.config.middle_tf,
            ltf_timeframe=self.config.ltf,
        )

        if not self.config.is_valid_combo():
            setup.reasons.append("Invalid timeframe combination")
            setup.direction = "NO_SIGNAL"
            return setup

        min_candles = self.config.swing_left + self.config.swing_right + 10
        if len(middle_candles) < min_candles:
            setup.reasons.append(
                f"Insufficient middle-TF data: {len(middle_candles)} candles, need {min_candles}"
            )
            setup.direction = "NO_SIGNAL"
            return setup

        if len(htf_candles) < 10:
            setup.reasons.append(
                f"Insufficient HTF data: {len(htf_candles)} candles, need at least 10"
            )
            setup.direction = "NO_SIGNAL"
            return setup

        middle_candles = sorted(middle_candles, key=lambda c: c.timestamp)
        htf_candles = sorted(htf_candles, key=lambda c: c.timestamp)
        ltf_candles = sorted(ltf_candles, key=lambda c: c.timestamp) if ltf_candles else middle_candles

        atr = self._compute_atr(middle_candles)
        if atr <= 0:
            setup.reasons.append("ATR is zero")
            setup.direction = "NO_SIGNAL"
            return setup

        current_price = middle_candles[-1].close

        htf_labels = label_swings(
            detect_swings(htf_candles, self.config.swing_left, self.config.swing_right)
        )
        htf_bias = self._determine_bias(htf_labels)

        setup.htf_labels = htf_labels
        setup.htf_bias = htf_bias

        swings = detect_swings(middle_candles, self.config.swing_left, self.config.swing_right)
        if len(swings) < 2:
            setup.reasons.append(f"Insufficient swings for structure analysis: {len(swings)}")
            setup.direction = "NO_SIGNAL"
            return setup

        labels = label_swings(swings)
        setup.middle_labels = labels

        bos_events = detect_bos(labels, middle_candles)
        choch_events = detect_choch(labels, middle_candles)
        idms = detect_idm(labels, swings, middle_candles)

        bos_swept = check_bos_sweep(bos_events, middle_candles, atr)
        choch_swept = check_choch_sweep(choch_events, middle_candles, atr)
        idm_swept = check_idm_sweep(idms, middle_candles, atr, self.config.liquidity_tolerance_atr)

        move_structural_reference_after_sweep(bos_events, middle_candles, labels)
        move_structural_reference_after_sweep(choch_events, middle_candles, labels)

        fvgs = detect_fvg(middle_candles, atr, self.config.fvg_min_atr, self.config.middle_tf) if self.config.fvg_enabled else []
        ifcs = detect_ifc(middle_candles, atr, self.config.ifc_wick_ratio, self.config.ifc_sweep_atr)

        obs = detect_order_blocks(
            middle_candles, bos_events, idms, fvgs, ifcs, atr,
            self.config.ob_body_atr, self.config.ob_body_ratio,
        )

        pullbacks = detect_pullbacks_via_liquidity_grab(middle_candles, 0, len(middle_candles) - 1)
        bias = htf_bias if htf_bias != "NEUTRAL" else self._determine_bias(labels)
        order_flow = detect_order_flow(middle_candles, pullbacks, bias)

        liquidity_levels = detect_liquidity(middle_candles, swings, atr, self.config)
        swept_liquidity = detect_sweeps(middle_candles, liquidity_levels, lookback=20)

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

        direction = self._determine_direction(bias, bos_events, choch_events, idms, idm_swept)

        if direction == "NO_SIGNAL":
            setup.direction = "NO_SIGNAL"
            setup.reasons.append("No clear directional bias from market structure")
            self._log_result(setup)
            return setup

        setup.direction = direction

        scheme_result = evaluate_all_schemes(middle_candles, idms, ifcs, obs, direction, atr)

        if not scheme_result.found:
            setup.reasons.append("Directional bias detected but no validated entry setup")
            setup.reasons.append(f"Waiting for: {scheme_result.reason}")
            setup.reasons.append(self._describe_wait_reason(direction, idms, idm_swept, ifcs, obs))
            self._log_result(setup)
            return setup

        zone = scheme_result.entry_zone
        if zone is None:
            setup.reasons.append("Entry zone calculation returned None")
            self._log_result(setup)
            return setup

        setup.poi_type = zone.type
        setup.poi_zone = zone
        setup.entry_type = scheme_result.entry_type
        setup.entry_scheme = scheme_result.entry_scheme

        setup.entry_low = zone.low
        setup.entry_high = zone.high

        sl = self._calc_stop_loss(zone, direction, middle_candles, atr)
        setup.stop_loss = sl

        risk = self._calc_risk(zone, sl, direction)
        tps = self._calc_take_profits(zone, direction, risk, liquidity_levels, middle_candles)
        setup.take_profit_1 = tps[0]
        setup.take_profit_2 = tps[1]
        setup.take_profit_3 = tps[2]

        rr = self._calc_rr(zone, sl, tps[0], direction)
        setup.risk_reward = rr

        if rr is not None and rr < self.config.minimum_rr:
            setup.direction = "NO_SIGNAL"
            setup.reasons.append(f"R:R {rr:.2f} below minimum {self.config.minimum_rr}")
            self._log_result(setup)
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
            rr_strong=rr is not None and rr >= 3.0,
        )

        confidence = calculate_score(scoring)
        setup.confidence = confidence

        if confidence < self.config.minimum_confidence:
            setup.direction = "NO_SIGNAL"
            setup.reasons.append(f"Confidence {confidence:.0f} below minimum {self.config.minimum_confidence}")
            self._log_result(setup)
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

        recent = labels[-8:] if len(labels) >= 8 else labels
        hh_count = sum(1 for l in recent if l.type == "HH")
        hl_count = sum(1 for l in recent if l.type == "HL")
        ll_count = sum(1 for l in recent if l.type == "LL")
        lh_count = sum(1 for l in recent if l.type == "LH")

        bullish = hh_count + hl_count
        bearish = ll_count + lh_count

        total = bullish + bearish
        if total == 0:
            return "NEUTRAL"

        bullish_ratio = bullish / total
        bearish_ratio = bearish / total

        if bullish_ratio >= 0.6:
            return "BULLISH"
        elif bearish_ratio >= 0.6:
            return "BEARISH"

        if bullish > bearish and bullish >= 1:
            return "BULLISH"
        elif bearish > bullish and bearish >= 1:
            return "BEARISH"

        return "NEUTRAL"

    def _determine_direction(
        self,
        bias: str,
        bos_events: list[StructureEvent],
        choch_events: list[StructureEvent],
        idms: list[IDM],
        idm_swept: list[IDM],
    ) -> str:
        if bias == "BULLISH":
            bullish_bos = any(e.direction == "BULLISH" and e.confirmed for e in bos_events)
            bullish_choch = any(e.direction == "BULLISH" and e.confirmed for e in choch_events)
            bullish_idm_swept = any(i.direction == "BULLISH" and i.swept for i in idms)
            if bullish_bos or bullish_choch:
                return "LONG"
            if bullish_idm_swept and len(idms) > 0:
                return "LONG"
            if bias == "BULLISH" and len(bos_events) == 0 and len(choch_events) == 0:
                if len(idms) > 0:
                    return "LONG"

        elif bias == "BEARISH":
            bearish_bos = any(e.direction == "BEARISH" and e.confirmed for e in bos_events)
            bearish_choch = any(e.direction == "BEARISH" and e.confirmed for e in choch_events)
            bearish_idm_swept = any(i.direction == "BEARISH" and i.swept for i in idms)
            if bearish_bos or bearish_choch:
                return "SHORT"
            if bearish_idm_swept and len(idms) > 0:
                return "SHORT"
            if bias == "BEARISH" and len(bos_events) == 0 and len(choch_events) == 0:
                if len(idms) > 0:
                    return "SHORT"

        return "NO_SIGNAL"

    def _describe_wait_reason(
        self,
        direction: str,
        idms: list[IDM],
        idm_swept: list[IDM],
        ifcs: list[IFC],
        obs: list[OrderBlock],
    ) -> str:
        unswept = [i for i in idms if not i.swept and i.direction == ("BULLISH" if direction == "LONG" else "BEARISH")]
        if unswept:
            return f"IDM at {unswept[0].price:.2f} has not been swept yet"
        if not ifcs:
            return "No IFC confirmation detected"
        if not obs:
            return "No order blocks detected at POI"
        return "Entry conditions not yet fully aligned"

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
        idm_swept_count = sum(1 for i in idms if i.swept)
        return (
            f"Structure: {' → '.join(recent_labels)} | "
            f"BOS: {bos_count} | CHoCH: {choch_count} | "
            f"IDM: {idm_count} (swept: {idm_swept_count})"
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

        if setup.htf_labels:
            htf_bias = self._determine_bias(setup.htf_labels)
            if htf_bias != "NEUTRAL":
                reasons.append(f"HTF ({self.config.htf}) bias is {htf_bias.lower()}")
            else:
                reasons.append(f"HTF ({self.config.htf}) bias is neutral")

        if setup.market_bias == "BULLISH":
            reasons.append("Middle-TF bias is bullish")
        elif setup.market_bias == "BEARISH":
            reasons.append("Middle-TF bias is bearish")

        if setup.bos_events:
            reasons.append(
                "Bullish BOS confirmed" if setup.bos_events[0].direction == "BULLISH"
                else "Bearish BOS confirmed"
            )

        if setup.choch_events:
            reasons.append(
                "Bullish CHoCH confirmed" if setup.choch_events[0].direction == "BULLISH"
                else "Bearish CHoCH confirmed"
            )

        if idm_swept:
            reasons.append(f"IDM liquidity swept at {idm_swept[0].price:.2f}")

        if swept_liquidity:
            reasons.append("Liquidity sweep detected")

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
            entry_str = f"{setup.entry_low:.2f}-{setup.entry_high:.2f}" if setup.entry_low and setup.entry_high else "PENDING"
            sl_str = f"{setup.stop_loss:.2f}" if setup.stop_loss else "PENDING"
            logger.info(
                f"ADVANCED_SMC: {setup.direction} | bias={setup.market_bias} | "
                f"entry={entry_str} | sl={sl_str} | tp1={setup.take_profit_1} | "
                f"rr={setup.risk_reward} | scheme={setup.entry_scheme} | "
                f"conf={setup.confidence:.0f}"
            )
