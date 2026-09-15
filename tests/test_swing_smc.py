import pytest
from datetime import datetime, timedelta
from app.strategies.swing_smc.models import (
    Candle,
    SwingPoint,
    StructureEvent,
    LiquidityLevel,
    FairValueGap,
    OrderBlock,
    TradeSetup,
)
from app.strategies.swing_smc.config import SwingSMCConfig
from app.strategies.swing_smc.swings import detect_swings
from app.strategies.swing_smc.structure import determine_structure, _detect_trend
from app.strategies.swing_smc.liquidity import detect_liquidity, detect_sweeps
from app.strategies.swing_smc.fvg import detect_fvg, check_fvg_fill
from app.strategies.swing_smc.order_blocks import detect_order_blocks, check_ob_mitigation
from app.strategies.swing_smc.displacement import detect_displacement, is_displacement_candle
from app.strategies.swing_smc.premium_discount import calculate_premium_discount
from app.strategies.swing_smc.scoring import ScoringInput, ScoringWeights, calculate_score, confidence_label
from app.strategies.swing_smc.validation import validate_setup
from app.strategies.swing_smc.setup import build_long_setup, build_short_setup
from app.strategies.swing_smc.strategy import SwingSMCStrategy


def _ts(i: int) -> datetime:
    return datetime(2024, 1, 1) + timedelta(hours=i)


def _c(o, h, l, c, vol=1000, i=0) -> Candle:
    return Candle(timestamp=_ts(i), open=o, high=h, low=l, close=c, volume=vol)


def _make_uptrend(n=10, base=100, step=2):
    candles = []
    for i in range(n):
        o = base + i * step
        h = o + 3
        l = o - 1
        c = o + 2
        candles.append(_c(o, h, l, c, i=i))
    return candles


def _make_downtrend(n=10, base=120, step=2):
    candles = []
    for i in range(n):
        o = base - i * step
        h = o + 1
        l = o - 3
        c = o - 2
        candles.append(_c(o, h, l, c, i=i))
    return candles


class TestSwingDetection:
    def test_detects_swing_high(self):
        candles = [
            _c(10, 11, 9, 10, i=0),
            _c(10, 12, 9, 11, i=1),
            _c(11, 13, 10, 12, i=2),
            _c(12, 11, 9, 10, i=3),
            _c(10, 11, 9, 10, i=4),
        ]
        swings = detect_swings(candles, left=2, right=2)
        highs = [s for s in swings if s.type == "HIGH"]
        assert len(highs) == 1
        assert highs[0].price == 13

    def test_detects_swing_low(self):
        candles = [
            _c(20, 21, 19, 20, i=0),
            _c(20, 21, 19, 20, i=1),
            _c(20, 21, 17, 18, i=2),
            _c(18, 20, 17, 19, i=3),
            _c(19, 21, 18, 20, i=4),
        ]
        swings = detect_swings(candles, left=2, right=2)
        lows = [s for s in swings if s.type == "LOW"]
        assert len(lows) == 1
        assert lows[0].price == 17

    def test_no_swings_insufficient_data(self):
        candles = [_c(10, 12, 8, 10, i=i) for i in range(3)]
        swings = detect_swings(candles, left=2, right=2)
        assert len(swings) == 0

    def test_multiple_swings(self):
        candles = [
            _c(10, 12, 9, 10, i=0),
            _c(10, 14, 10, 13, i=1),
            _c(13, 15, 12, 14, i=2),
            _c(14, 13, 10, 11, i=3),
            _c(11, 12, 9, 10, i=4),
            _c(10, 13, 9, 12, i=5),
            _c(12, 16, 12, 15, i=6),
            _c(15, 14, 11, 12, i=7),
            _c(12, 13, 10, 11, i=8),
        ]
        swings = detect_swings(candles, left=2, right=2)
        assert len(swings) >= 2

    def test_strength_increases_with_bigger_swing(self):
        candles = [
            _c(10, 11, 9, 10, i=0),
            _c(10, 11, 9, 10, i=1),
            _c(10, 20, 9, 15, i=2),
            _c(15, 16, 14, 15, i=3),
            _c(15, 16, 14, 15, i=4),
            _c(15, 16, 14, 15, i=5),
            _c(15, 16, 14, 15, i=6),
        ]
        swings = detect_swings(candles, left=2, right=2)
        highs = [s for s in swings if s.type == "HIGH"]
        assert len(highs) == 1
        assert highs[0].strength >= 2


class TestMarketStructure:
    def test_bullish_bos(self):
        swings = [
            SwingPoint(0, _ts(0), 100, "HIGH", 3),
            SwingPoint(2, _ts(2), 90, "LOW", 3),
            SwingPoint(4, _ts(4), 105, "HIGH", 3),
            SwingPoint(6, _ts(6), 92, "LOW", 3),
        ]
        events = determine_structure(swings)
        bullish_bos = [e for e in events if e.type == "BOS" and e.direction == "BULLISH"]
        assert len(bullish_bos) >= 1

    def test_bearish_bos(self):
        swings = [
            SwingPoint(0, _ts(0), 90, "LOW", 3),
            SwingPoint(2, _ts(2), 100, "HIGH", 3),
            SwingPoint(4, _ts(4), 85, "LOW", 3),
            SwingPoint(6, _ts(6), 98, "HIGH", 3),
        ]
        events = determine_structure(swings)
        bearish_bos = [e for e in events if e.type == "BOS" and e.direction == "BEARISH"]
        assert len(bearish_bos) >= 1

    def test_no_structure_insufficient_swings(self):
        swings = [
            SwingPoint(0, _ts(0), 100, "HIGH", 3),
            SwingPoint(2, _ts(2), 90, "LOW", 3),
        ]
        events = determine_structure(swings)
        assert len(events) == 0

    def test_detect_trend_bullish(self):
        swings = [
            SwingPoint(0, _ts(0), 100, "HIGH", 3),
            SwingPoint(2, _ts(2), 90, "LOW", 3),
            SwingPoint(4, _ts(4), 110, "HIGH", 3),
            SwingPoint(6, _ts(6), 95, "LOW", 3),
        ]
        trend = _detect_trend(swings)
        assert trend == "BULLISH"

    def test_detect_trend_bearish(self):
        swings = [
            SwingPoint(0, _ts(0), 110, "HIGH", 3),
            SwingPoint(2, _ts(2), 100, "LOW", 3),
            SwingPoint(4, _ts(4), 105, "HIGH", 3),
            SwingPoint(6, _ts(6), 90, "LOW", 3),
        ]
        trend = _detect_trend(swings)
        assert trend == "BEARISH"


class TestLiquidity:
    def test_equal_highs(self):
        swings = [
            SwingPoint(0, _ts(0), 105.20, "HIGH", 2),
            SwingPoint(5, _ts(5), 105.30, "HIGH", 2),
        ]
        levels = detect_liquidity([], swings, atr=1.0, tolerance_atr=0.5)
        eq_highs = [l for l in levels if l.type == "EQUAL_HIGH"]
        assert len(eq_highs) == 1
        assert abs(eq_highs[0].price - 105.25) < 0.1

    def test_equal_lows(self):
        swings = [
            SwingPoint(0, _ts(0), 99.80, "LOW", 2),
            SwingPoint(5, _ts(5), 99.70, "LOW", 2),
        ]
        levels = detect_liquidity([], swings, atr=1.0, tolerance_atr=0.5)
        eq_lows = [l for l in levels if l.type == "EQUAL_LOW"]
        assert len(eq_lows) == 1

    def test_previous_day_levels(self):
        candles = [
            _c(100, 105, 98, 102, i=0),
            _c(102, 108, 100, 106, i=1),
        ]
        levels = detect_liquidity(candles, [], atr=1.0)
        prev_high = [l for l in levels if l.type == "PREVIOUS_HIGH"]
        prev_low = [l for l in levels if l.type == "PREVIOUS_LOW"]
        assert len(prev_high) == 1
        assert len(prev_low) == 1
        assert prev_high[0].price == 105.0
        assert prev_low[0].price == 98.0

    def test_major_swing_levels(self):
        swings = [
            SwingPoint(0, _ts(0), 100, "HIGH", 5),
            SwingPoint(5, _ts(5), 90, "LOW", 5),
        ]
        levels = detect_liquidity([], swings, atr=1.0)
        major = [l for l in levels if l.type in ("SWING_HIGH", "SWING_LOW")]
        assert len(major) == 2

    def test_sweep_detection(self):
        candles = [_c(100, 106, 99, 102, i=i) for i in range(10)]
        levels = [
            LiquidityLevel(type="EQUAL_HIGH", price=105.0, strength=2),
        ]
        swept = detect_sweeps(candles, levels, lookback=10)
        assert len(swept) == 1
        assert swept[0].swept is True


class TestFVG:
    def test_bullish_fvg(self):
        candles = [
            _c(100, 102, 99, 101, i=0),
            _c(101, 105, 100, 104, i=1),
            _c(104, 110, 103, 108, i=2),
        ]
        fvgs = detect_fvg(candles, atr=2.0, min_size_atr=0.1)
        bullish = [f for f in fvgs if f.direction == "BULLISH"]
        assert len(bullish) == 1
        assert bullish[0].low == 102.0
        assert bullish[0].high == 103.0

    def test_bearish_fvg(self):
        candles = [
            _c(110, 112, 109, 111, i=0),
            _c(111, 112, 105, 106, i=1),
            _c(106, 108, 100, 102, i=2),
        ]
        fvgs = detect_fvg(candles, atr=2.0, min_size_atr=0.1)
        bearish = [f for f in fvgs if f.direction == "BEARISH"]
        assert len(bearish) == 1
        assert bearish[0].low == 108.0
        assert bearish[0].high == 109.0

    def test_no_fvg_when_overlapping(self):
        candles = [
            _c(100, 105, 99, 103, i=0),
            _c(103, 106, 102, 105, i=1),
            _c(105, 108, 104, 107, i=2),
        ]
        fvgs = detect_fvg(candles, atr=2.0, min_size_atr=0.1)
        assert len(fvgs) == 0

    def test_fvg_size_filter(self):
        candles = [
            _c(100, 102, 99, 101, i=0),
            _c(101, 105, 100, 104, i=1),
            _c(104, 105.1, 103.5, 104.5, i=2),
        ]
        fvgs = detect_fvg(candles, atr=5.0, min_size_atr=0.5)
        assert len(fvgs) == 0

    def test_fvg_fill_check(self):
        fvg = FairValueGap(
            direction="BULLISH",
            low=102.0,
            high=103.0,
            midpoint=102.5,
            created_at=_ts(2),
            timeframe="4H",
        )
        candles = [
            _c(104, 105, 101, 102, i=3),
        ]
        result = check_fvg_fill(fvg, candles, 0)
        assert result.filled is True

    def test_fvg_no_fill(self):
        fvg = FairValueGap(
            direction="BULLISH",
            low=102.0,
            high=103.0,
            midpoint=102.5,
            created_at=_ts(2),
            timeframe="4H",
        )
        candles = [
            _c(104, 106, 103.5, 105, i=3),
        ]
        result = check_fvg_fill(fvg, candles, 0)
        assert result.filled is False


class TestOrderBlocks:
    def test_bullish_ob_detection(self):
        candles = [
            _c(100, 101, 99, 100, i=0),
            _c(100, 101, 99, 100, i=1),
            _c(102, 103, 98, 99, i=2),
            _c(99, 100, 98, 99, i=3),
            _c(99, 108, 98.5, 107, i=4),
        ]
        events = [
            StructureEvent(
                type="BOS",
                direction="BULLISH",
                price=101,
                timestamp=_ts(4),
                broken_swing_index=3,
                confirmed=True,
            )
        ]
        obs = detect_order_blocks(candles, events, atr=2.0, body_atr_mult=1.0, body_ratio_min=0.5)
        bullish_obs = [o for o in obs if o.direction == "BULLISH"]
        assert len(bullish_obs) >= 1

    def test_no_ob_without_displacement(self):
        candles = [
            _c(100, 101, 99, 100, i=0),
            _c(100, 101, 99, 100, i=1),
            _c(100, 101, 99, 100, i=2),
            _c(100, 101, 99, 100, i=3),
        ]
        events = [
            StructureEvent(
                type="BOS",
                direction="BULLISH",
                price=101,
                timestamp=_ts(3),
                broken_swing_index=0,
                confirmed=True,
            )
        ]
        obs = detect_order_blocks(candles, events, atr=5.0, body_atr_mult=2.0, body_ratio_min=0.8)
        assert len(obs) == 0

    def test_ob_mitigation(self):
        ob = OrderBlock(
            direction="BULLISH",
            low=98.0,
            high=100.0,
            timestamp=_ts(0),
            source_candle_index=0,
            strength=1.5,
        )
        candles = [_c(97, 98, 96, 96.5, i=1)]
        result = check_ob_mitigation(ob, candles, 0)
        assert result.mitigated is True

    def test_ob_not_mitigated(self):
        ob = OrderBlock(
            direction="BULLISH",
            low=98.0,
            high=100.0,
            timestamp=_ts(0),
            source_candle_index=0,
            strength=1.5,
        )
        candles = [_c(99, 102, 98.5, 101, i=1)]
        result = check_ob_mitigation(ob, candles, 0)
        assert result.mitigated is False


class TestDisplacement:
    def test_bullish_displacement(self):
        candles = [
            _c(100, 101, 99, 100, i=0),
            _c(100, 108, 99.5, 107, i=1),
        ]
        results = detect_displacement(candles, atr=2.0, body_atr_mult=1.0, body_ratio_min=0.5)
        assert len(results) == 1
        assert results[0] == (1, "BULLISH")

    def test_bearish_displacement(self):
        candles = [
            _c(100, 101, 99, 100, i=0),
            _c(100, 100.5, 92, 93, i=1),
        ]
        results = detect_displacement(candles, atr=2.0, body_atr_mult=1.0, body_ratio_min=0.5)
        assert len(results) == 1
        assert results[0] == (1, "BEARISH")

    def test_no_displacement_small_body(self):
        candles = [
            _c(100, 101, 99, 100, i=0),
            _c(100, 101, 99, 100.5, i=1),
        ]
        results = detect_displacement(candles, atr=5.0, body_atr_mult=2.0, body_ratio_min=0.5)
        assert len(results) == 0

    def test_is_displacement_candle(self):
        c = _c(100, 108, 99.5, 107)
        result = is_displacement_candle(c, atr=2.0, body_atr_mult=1.0, body_ratio_min=0.5)
        assert result == "BULLISH"


class TestPremiumDiscount:
    def test_discount(self):
        swings = [
            SwingPoint(0, _ts(0), 120, "HIGH", 3),
            SwingPoint(2, _ts(2), 100, "LOW", 3),
        ]
        zone, high, low = calculate_premium_discount(105, swings)
        assert zone == "DISCOUNT"

    def test_premium(self):
        swings = [
            SwingPoint(0, _ts(0), 120, "HIGH", 3),
            SwingPoint(2, _ts(2), 100, "LOW", 3),
        ]
        zone, high, low = calculate_premium_discount(115, swings)
        assert zone == "PREMIUM"

    def test_equilibrium(self):
        swings = [
            SwingPoint(0, _ts(0), 120, "HIGH", 3),
            SwingPoint(2, _ts(2), 100, "LOW", 3),
        ]
        zone, high, low = calculate_premium_discount(110, swings)
        assert zone == "EQUILIBRIUM"

    def test_no_swings(self):
        zone, high, low = calculate_premium_discount(100, [])
        assert zone == "NEUTRAL"


class TestScoring:
    def test_max_score(self):
        inp = ScoringInput(
            htf_aligned=True,
            structure_confirmed=True,
            liquidity_swept=True,
            in_preferred_zone=True,
            has_order_block=True,
            has_fvg=True,
            has_displacement=True,
            volume_confirms=True,
            rr_strong=True,
        )
        score = calculate_score(inp)
        assert score == 100.0

    def test_zero_score(self):
        inp = ScoringInput()
        score = calculate_score(inp)
        assert score == 0.0

    def test_partial_score(self):
        inp = ScoringInput(
            htf_aligned=True,
            structure_confirmed=True,
            liquidity_swept=False,
            in_preferred_zone=False,
            has_order_block=False,
            has_fvg=False,
            has_displacement=False,
            volume_confirms=False,
            rr_strong=False,
        )
        score = calculate_score(inp)
        assert score == 35.0

    def test_confidence_labels(self):
        assert confidence_label(90) == "VERY_STRONG"
        assert confidence_label(80) == "STRONG"
        assert confidence_label(70) == "MODERATE"
        assert confidence_label(55) == "WEAK"
        assert confidence_label(30) == "NO_SIGNAL"


class TestValidation:
    def test_valid_long(self):
        setup = TradeSetup(
            direction="LONG",
            entry_low=100,
            entry_high=102,
            stop_loss=96,
            take_profit_1=110,
            confidence=80,
        )
        result = validate_setup(setup, 101)
        assert result.direction == "LONG"
        assert result.risk_reward is not None
        assert result.risk_reward > 0

    def test_valid_short(self):
        setup = TradeSetup(
            direction="SHORT",
            entry_low=100,
            entry_high=102,
            stop_loss=106,
            take_profit_1=92,
            confidence=80,
        )
        result = validate_setup(setup, 101)
        assert result.direction == "SHORT"
        assert result.risk_reward is not None

    def test_no_signal_rejected(self):
        setup = TradeSetup(direction="NO_SIGNAL")
        result = validate_setup(setup, 100)
        assert result.direction == "NO_SIGNAL"

    def test_missing_entry(self):
        setup = TradeSetup(direction="LONG", stop_loss=96, take_profit_1=110)
        result = validate_setup(setup, 100)
        assert result.direction == "NO_SIGNAL"
        assert any("Missing entry" in r for r in result.reasons)

    def test_missing_stop_loss(self):
        setup = TradeSetup(direction="LONG", entry_low=100, entry_high=102, take_profit_1=110)
        result = validate_setup(setup, 101)
        assert result.direction == "NO_SIGNAL"

    def test_invalid_rr(self):
        setup = TradeSetup(
            direction="LONG",
            entry_low=100,
            entry_high=102,
            stop_loss=99,
            take_profit_1=102.5,
            confidence=80,
        )
        result = validate_setup(setup, 101)
        assert result.direction == "NO_SIGNAL"
        assert result.risk_reward is not None
        assert result.risk_reward < 2.0

    def test_long_sl_above_entry(self):
        setup = TradeSetup(
            direction="LONG",
            entry_low=100,
            entry_high=102,
            stop_loss=103,
            take_profit_1=110,
            confidence=80,
        )
        result = validate_setup(setup, 101)
        assert result.direction == "NO_SIGNAL"

    def test_short_sl_below_entry(self):
        setup = TradeSetup(
            direction="SHORT",
            entry_low=100,
            entry_high=102,
            stop_loss=99,
            take_profit_1=92,
            confidence=80,
        )
        result = validate_setup(setup, 101)
        assert result.direction == "NO_SIGNAL"


class TestSwingSMCStrategy:
    def test_insufficient_data(self):
        strategy = SwingSMCStrategy(SwingSMCConfig())
        candles = [_c(100, 105, 95, 102, i=i) for i in range(3)]
        result = strategy.analyze(candles)
        assert result.direction == "NO_SIGNAL"
        assert any("Insufficient" in r for r in result.reasons)

    def test_no_signal_on_flat_data(self):
        strategy = SwingSMCStrategy(SwingSMCConfig())
        candles = [_c(100, 101, 99, 100, i=i) for i in range(30)]
        result = strategy.analyze(candles)
        assert result.direction == "NO_SIGNAL"

    def test_uptrend_may_produce_long(self):
        strategy = SwingSMCStrategy(SwingSMCConfig(minimum_confidence=0))
        candles = []
        for i in range(40):
            base = 100 + i * 1.5
            h = base + 3 + (i % 3)
            l = base - 1
            c = base + 2
            candles.append(_c(base, h, l, c, vol=1000 + i * 50, i=i))
        result = strategy.analyze(candles)
        assert result.direction in ("LONG", "NO_SIGNAL")

    def test_downtrend_may_produce_short(self):
        strategy = SwingSMCStrategy(SwingSMCConfig(minimum_confidence=0))
        candles = []
        for i in range(40):
            base = 200 - i * 1.5
            h = base + 1
            l = base - 3 - (i % 3)
            c = base - 2
            candles.append(_c(base, h, l, c, vol=1000 + i * 50, i=i))
        result = strategy.analyze(candles)
        assert result.direction in ("SHORT", "NO_SIGNAL")

    def test_invalid_config(self):
        config = SwingSMCConfig(htf="2H", structure_tf="30m", entry_tf="5m")
        assert config.is_valid_combo() is False

    def test_valid_config(self):
        config = SwingSMCConfig(htf="1D", structure_tf="4H", entry_tf="1H")
        assert config.is_valid_combo() is True

    def test_atr_computation(self):
        strategy = SwingSMCStrategy()
        candles = [
            _c(100, 105, 95, 102, i=0),
            _c(102, 108, 100, 106, i=1),
            _c(106, 110, 104, 108, i=2),
        ]
        atr = strategy._compute_atr(candles)
        assert atr > 0


class TestSetupBuilding:
    def test_long_setup_needs_bullish_bias(self):
        candles = [_c(100, 105, 95, 102, i=i) for i in range(40)]
        config = SwingSMCConfig(minimum_confidence=0)
        strategy = SwingSMCStrategy(config)
        atr = 3.0
        swings = detect_swings(candles, 2, 2)
        result = build_long_setup(
            candles=candles,
            current_price=102,
            htf_bias="BEARISH",
            swings=swings,
            structure_events=[],
            liquidity_levels=[],
            swept_levels=[],
            fvgs=[],
            order_blocks=[],
            has_displacement=False,
            volume_confirms=False,
            premium_discount=("NEUTRAL", 105, 95),
            atr=atr,
            config=config,
        )
        assert result.direction == "NO_SIGNAL"
        assert any("not bullish" in r for r in result.reasons)

    def test_short_setup_needs_bearish_bias(self):
        candles = [_c(100, 105, 95, 102, i=i) for i in range(40)]
        config = SwingSMCConfig(minimum_confidence=0)
        strategy = SwingSMCStrategy(config)
        atr = 3.0
        swings = detect_swings(candles, 2, 2)
        result = build_short_setup(
            candles=candles,
            current_price=102,
            htf_bias="BULLISH",
            swings=swings,
            structure_events=[],
            liquidity_levels=[],
            swept_levels=[],
            fvgs=[],
            order_blocks=[],
            has_displacement=False,
            volume_confirms=False,
            premium_discount=("NEUTRAL", 105, 95),
            atr=atr,
            config=config,
        )
        assert result.direction == "NO_SIGNAL"
        assert any("not bearish" in r for r in result.reasons)
