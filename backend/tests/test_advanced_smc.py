import pytest
from datetime import datetime, timedelta
from app.strategies.advanced_smc.models import (
    Candle, SwingPoint, StructureLabel, StructureEvent, IDM,
    LiquidityLevel, FairValueGap, OrderBlock, OrderFlow, IFC, EntryZone,
)
from app.strategies.advanced_smc.config import AdvancedSMCConfig
from app.strategies.advanced_smc.structure import (
    label_swings, detect_bos, detect_choch, detect_idm, check_idm_sweep,
)
from app.strategies.advanced_smc.sweep import (
    check_bos_sweep, check_choch_sweep, is_wick_sweep,
)
from app.strategies.advanced_smc.impulse import (
    is_impulse, is_liquidity_grab, detect_pullbacks, find_extreme_candle,
)
from app.strategies.advanced_smc.fvg import detect_fvg, check_fvg_fill
from app.strategies.advanced_smc.order_blocks import detect_order_blocks, check_ob_mitigation
from app.strategies.advanced_smc.order_flow import detect_order_flow
from app.strategies.advanced_smc.ifc import detect_ifc
from app.strategies.advanced_smc.liquidity import (
    detect_liquidity, detect_sweeps, _get_session_high_low,
)
from app.strategies.advanced_smc.pullback import (
    detect_pullbacks_via_liquidity_grab, find_first_pullback_after_poi, find_idm_in_move,
)
from app.strategies.advanced_smc.entry_schemes import (
    try_scheme_1, try_scheme_2, try_scheme_3, try_scheme_4,
    try_scheme_5, try_scheme_6, try_scheme_7, try_scheme_8,
    evaluate_all_schemes,
)
from app.strategies.advanced_smc.scoring import ScoringInput, calculate_score, confidence_label
from app.strategies.advanced_smc.strategy import AdvancedSMCStrategy
from app.strategies.swing_smc.swings import detect_swings


def _ts(i: int) -> datetime:
    return datetime(2024, 1, 1) + timedelta(hours=i)


def _c(o, h, l, c, vol=1000, i=0) -> Candle:
    return Candle(timestamp=_ts(i), open=o, high=h, low=l, close=c, volume=vol)


class TestSwingDetection:
    def test_detects_swing_high(self):
        candles = [
            _c(10, 11, 9, 10, i=0),
            _c(10, 12, 9, 11, i=1),
            _c(11, 15, 10, 14, i=2),
            _c(14, 13, 9, 10, i=3),
            _c(10, 11, 9, 10, i=4),
        ]
        swings = detect_swings(candles, left=2, right=2)
        highs = [s for s in swings if s.type == "HIGH"]
        assert len(highs) == 1
        assert highs[0].price == 15

    def test_detects_swing_low(self):
        candles = [
            _c(20, 21, 19, 20, i=0),
            _c(20, 21, 19, 20, i=1),
            _c(20, 21, 15, 16, i=2),
            _c(16, 20, 15, 19, i=3),
            _c(19, 21, 18, 20, i=4),
        ]
        swings = detect_swings(candles, left=2, right=2)
        lows = [s for s in swings if s.type == "LOW"]
        assert len(lows) == 1
        assert lows[0].price == 15

    def test_no_swings_insufficient_data(self):
        candles = [_c(10, 12, 8, 10, i=i) for i in range(3)]
        swings = detect_swings(candles, left=2, right=2)
        assert len(swings) == 0


class TestStructureLabels:
    def test_hh_label(self):
        swings = [
            SwingPoint(0, _ts(0), 100, "HIGH", 3),
            SwingPoint(2, _ts(2), 90, "LOW", 3),
            SwingPoint(4, _ts(4), 110, "HIGH", 3),
        ]
        labels = label_swings(swings)
        assert labels[0].type == "HH"
        assert labels[2].type == "HH"

    def test_lh_label(self):
        swings = [
            SwingPoint(0, _ts(0), 110, "HIGH", 3),
            SwingPoint(2, _ts(2), 100, "LOW", 3),
            SwingPoint(4, _ts(4), 105, "HIGH", 3),
        ]
        labels = label_swings(swings)
        assert labels[2].type == "LH"

    def test_hl_label(self):
        swings = [
            SwingPoint(0, _ts(0), 100, "LOW", 3),
            SwingPoint(2, _ts(2), 110, "HIGH", 3),
            SwingPoint(4, _ts(4), 105, "LOW", 3),
        ]
        labels = label_swings(swings)
        assert labels[2].type == "HL"

    def test_ll_label(self):
        swings = [
            SwingPoint(0, _ts(0), 100, "LOW", 3),
            SwingPoint(2, _ts(2), 110, "HIGH", 3),
            SwingPoint(4, _ts(4), 90, "LOW", 3),
        ]
        labels = label_swings(swings)
        assert labels[2].type == "LL"

    def test_empty_swings(self):
        labels = label_swings([])
        assert len(labels) == 0


class TestBOS:
    def test_bullish_bos(self):
        labels = [
            StructureLabel("HH", 0, _ts(0), 100),
            StructureLabel("HH", 2, _ts(2), 110),
        ]
        candles = [_c(100, 115, 99, 112, i=i) for i in range(5)]
        events = detect_bos(labels, candles)
        assert len(events) == 1
        assert events[0].direction == "BULLISH"
        assert events[0].price == 100

    def test_bearish_bos(self):
        labels = [
            StructureLabel("LL", 0, _ts(0), 100),
            StructureLabel("LL", 2, _ts(2), 90),
        ]
        candles = [_c(100, 101, 85, 88, i=i) for i in range(5)]
        events = detect_bos(labels, candles)
        assert len(events) == 1
        assert events[0].direction == "BEARISH"

    def test_no_bos_without_continuation(self):
        labels = [
            StructureLabel("HH", 0, _ts(0), 100),
            StructureLabel("LH", 2, _ts(2), 95),
        ]
        candles = [_c(100, 105, 90, 102, i=i) for i in range(5)]
        events = detect_bos(labels, candles)
        assert len(events) == 0


class TestCHOCH:
    def test_bullish_choch(self):
        labels = [
            StructureLabel("LH", 0, _ts(0), 105),
            StructureLabel("LL", 2, _ts(2), 90),
            StructureLabel("HL", 4, _ts(4), 106),
        ]
        candles = [_c(100, 110, 85, 108, i=i) for i in range(7)]
        events = detect_choch(labels, candles)
        assert len(events) == 1
        assert events[0].direction == "BULLISH"
        assert events[0].price == 105

    def test_bearish_choch(self):
        labels = [
            StructureLabel("HL", 0, _ts(0), 95),
            StructureLabel("HH", 2, _ts(2), 110),
            StructureLabel("LH", 4, _ts(4), 94),
        ]
        candles = [_c(100, 115, 80, 82, i=i) for i in range(7)]
        events = detect_choch(labels, candles)
        assert len(events) == 1
        assert events[0].direction == "BEARISH"
        assert events[0].price == 95

    def test_no_choch_without_trend(self):
        labels = [
            StructureLabel("HH", 0, _ts(0), 100),
            StructureLabel("LL", 2, _ts(2), 90),
            StructureLabel("HH", 4, _ts(4), 110),
        ]
        candles = [_c(100, 115, 85, 112, i=i) for i in range(7)]
        events = detect_choch(labels, candles)
        assert len(events) == 0


class TestIDM:
    def test_idm_detection_bullish(self):
        labels = [
            StructureLabel("HH", 0, _ts(0), 100),
            StructureLabel("HH", 4, _ts(4), 110),
        ]
        swings = [
            SwingPoint(0, _ts(0), 100, "HIGH", 3),
            SwingPoint(2, _ts(2), 95, "LOW", 3),
            SwingPoint(4, _ts(4), 110, "HIGH", 3),
        ]
        candles = [_c(95, 115, 90, 112, i=i) for i in range(7)]
        idms = detect_idm(labels, swings, candles)
        assert len(idms) == 1
        assert idms[0].direction == "BULLISH"
        assert idms[0].price == 95

    def test_idm_detection_bearish(self):
        labels = [
            StructureLabel("LL", 0, _ts(0), 100),
            StructureLabel("LL", 4, _ts(4), 90),
        ]
        swings = [
            SwingPoint(0, _ts(0), 100, "LOW", 3),
            SwingPoint(2, _ts(2), 105, "HIGH", 3),
            SwingPoint(4, _ts(4), 90, "LOW", 3),
        ]
        candles = [_c(105, 110, 85, 88, i=i) for i in range(7)]
        idms = detect_idm(labels, swings, candles)
        assert len(idms) == 1
        assert idms[0].direction == "BEARISH"
        assert idms[0].price == 105

    def test_idm_sweep(self):
        idms = [IDM(2, _ts(2), 95, "BULLISH")]
        candles = [
            _c(95, 100, 94, 98, i=0),
            _c(98, 101, 93, 99, i=1),
            _c(99, 102, 94, 100, i=2),
            _c(100, 105, 94.5, 103, i=3),
            _c(103, 110, 93, 108, i=4),
        ]
        swept = check_idm_sweep(idms, candles, atr=2.0)
        assert len(swept) == 1
        assert swept[0].swept is True

    def test_no_idm_without_labels(self):
        idms = detect_idm([], [], [])
        assert len(idms) == 0


class TestSweep:
    def test_bos_sweep(self):
        bos = [StructureEvent("BOS", "BULLISH", 100, _ts(2), 2)]
        candles = [
            _c(100, 105, 99, 102, i=0),
            _c(102, 106, 98, 103, i=1),
            _c(103, 107, 99, 104, i=2),
            _c(104, 106, 98, 99, i=3),
            _c(99, 101, 97, 98, i=4),
        ]
        swept = check_bos_sweep(bos, candles, atr=2.0)
        assert len(swept) == 1
        assert swept[0].swept is True

    def test_choch_sweep(self):
        choch = [StructureEvent("CHOCH", "BULLISH", 105, _ts(2), 2)]
        candles = [
            _c(105, 110, 104, 108, i=0),
            _c(108, 111, 103, 109, i=1),
            _c(109, 112, 104, 110, i=2),
            _c(110, 106, 102, 103, i=3),
            _c(103, 105, 101, 102, i=4),
        ]
        swept = check_choch_sweep(choch, candles, atr=2.0)
        assert len(swept) == 1
        assert swept[0].swept is True

    def test_wick_sweep_detection(self):
        c = _c(100, 106, 99, 100)
        assert is_wick_sweep(c, 105, "ABOVE") is True
        assert is_wick_sweep(c, 98, "BELOW") is False

    def test_no_sweep_without_wick(self):
        bos = [StructureEvent("BOS", "BULLISH", 100, _ts(2), 2)]
        candles = [_c(100, 110, 99, 108, i=3)]
        swept = check_bos_sweep(bos, candles, atr=2.0)
        assert len(swept) == 0


class TestImpulse:
    def test_bullish_impulse(self):
        prev = _c(100, 101, 99, 100)
        c = _c(100, 108, 99.5, 107)
        assert is_impulse(c, prev, 2.0) == "BULLISH"

    def test_bearish_impulse(self):
        prev = _c(100, 101, 99, 100)
        c = _c(100, 100.5, 92, 93)
        assert is_impulse(c, prev, 2.0) == "BEARISH"

    def test_no_impulse_small_body(self):
        prev = _c(100, 101, 99, 100)
        c = _c(100, 101, 99, 100.2)
        assert is_impulse(c, prev, 5.0) is None

    def test_liquidity_grab(self):
        prev = _c(100, 105, 98, 102)
        c = _c(102, 106, 97, 99)
        assert is_liquidity_grab(c, prev) is True

    def test_no_liquidity_grab(self):
        prev = _c(100, 105, 98, 102)
        c = _c(102, 104, 99, 103)
        assert is_liquidity_grab(c, prev) is False


class TestFVG:
    def test_bullish_fvg(self):
        candles = [
            _c(100, 102, 99, 101, i=0),
            _c(101, 105, 100, 104, i=1),
            _c(104, 110, 103, 108, i=2),
        ]
        fvgs = detect_fvg(candles, atr=2.0, min_size_atr=0.05)
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
        fvgs = detect_fvg(candles, atr=2.0, min_size_atr=0.05)
        bearish = [f for f in fvgs if f.direction == "BEARISH"]
        assert len(bearish) == 1

    def test_no_fvg_overlapping_wicks(self):
        candles = [
            _c(100, 105, 99, 103, i=0),
            _c(103, 106, 102, 105, i=1),
            _c(105, 108, 104, 107, i=2),
        ]
        fvgs = detect_fvg(candles, atr=2.0, min_size_atr=0.05)
        assert len(fvgs) == 0

    def test_fvg_fill(self):
        fvg = FairValueGap("BULLISH", 103.0, 102.0, 102.5, _ts(2), "4H")
        candles = [_c(104, 105, 101, 102, i=3)]
        result = check_fvg_fill(fvg, candles, 0)
        assert result.filled is True


class TestOrderBlocks:
    def test_bullish_ob_detection(self):
        candles = [
            _c(100, 101, 99, 100, i=0),
            _c(100, 101, 99, 100, i=1),
            _c(102, 103, 98, 99, i=2),
            _c(99, 100, 98, 99, i=3),
            _c(99, 108, 98.5, 107, i=4),
        ]
        bos = [StructureEvent("BOS", "BULLISH", 101, _ts(4), 4)]
        obs = detect_order_blocks(candles, bos, [], [], [], atr=2.0, body_atr=1.0, body_ratio=0.5)
        bullish = [o for o in obs if o.direction == "BULLISH"]
        assert len(bullish) >= 1

    def test_ob_mitigation(self):
        ob = OrderBlock("BULLISH", 100.0, 98.0, _ts(0), 0, 1.5)
        candles = [_c(97, 98, 96, 96.5, i=1)]
        result = check_ob_mitigation(ob, candles, 0)
        assert result.mitigated is True

    def test_ob_not_mitigated(self):
        ob = OrderBlock("BULLISH", 100.0, 98.0, _ts(0), 0, 1.5)
        candles = [_c(99, 102, 98.5, 101, i=1)]
        result = check_ob_mitigation(ob, candles, 0)
        assert result.mitigated is False


class TestIFC:
    def test_bullish_ifc(self):
        candles = [
            _c(100, 101, 99, 100, i=0),
            _c(100, 101, 95, 100.5, i=1),
        ]
        ifcs = detect_ifc(candles, atr=2.0, wick_ratio=0.5, sweep_atr=0.3)
        bullish = [f for f in ifcs if f.direction == "BULLISH"]
        assert len(bullish) >= 1

    def test_bearish_ifc(self):
        candles = [
            _c(100, 101, 99, 100, i=0),
            _c(100, 105, 99.5, 99.8, i=1),
        ]
        ifcs = detect_ifc(candles, atr=2.0, wick_ratio=0.5, sweep_atr=0.3)
        bearish = [f for f in ifcs if f.direction == "BEARISH"]
        assert len(bearish) >= 1

    def test_no_ifc_no_wick(self):
        candles = [
            _c(100, 101, 99, 100, i=0),
            _c(100, 105, 99, 104, i=1),
        ]
        ifcs = detect_ifc(candles, atr=2.0, wick_ratio=0.6, sweep_atr=0.5)
        assert len(ifcs) == 0


class TestLiquidity:
    def test_equal_highs(self):
        swings = [
            SwingPoint(0, _ts(0), 105.20, "HIGH", 2),
            SwingPoint(5, _ts(5), 105.30, "HIGH", 2),
        ]
        levels = detect_liquidity([], swings, atr=1.0)
        eq = [l for l in levels if l.type == "EQUAL_HIGH"]
        assert len(eq) == 1

    def test_pdh_pdl(self):
        candles = [_c(100, 105, 98, 102, i=0), _c(102, 108, 100, 106, i=1)]
        levels = detect_liquidity(candles, [], atr=1.0)
        pdh = [l for l in levels if l.type == "PDH"]
        pdl = [l for l in levels if l.type == "PDL"]
        assert len(pdh) == 1
        assert len(pdl) == 1
        assert pdh[0].price == 105.0
        assert pdl[0].price == 98.0

    def test_sweep_detection(self):
        candles = [_c(100, 106, 99, 102, i=i) for i in range(10)]
        levels = [LiquidityLevel("EQUAL_HIGH", 105.0, 2)]
        swept = detect_sweeps(candles, levels, lookback=10)
        assert len(swept) == 1

    def test_session_levels(self):
        from app.strategies.advanced_smc.config import SessionConfig
        from datetime import time
        config = AdvancedSMCConfig()
        config.session_liquidity_enabled = True
        candles = [
            Candle(datetime(2024, 1, 1, 2, 0), 100, 105, 98, 102, 1000),
            Candle(datetime(2024, 1, 1, 5, 0), 102, 108, 100, 106, 1000),
        ]
        levels = detect_liquidity(candles, [], atr=1.0, config=config)
        asian = [l for l in levels if l.session == "asian"]
        assert len(asian) == 2


class TestOrderFlow:
    def test_order_flow_detection(self):
        candles = [
            _c(100, 105, 98, 102, i=0),
            _c(102, 106, 101, 104, i=1),
            _c(104, 108, 103, 106, i=2),
        ]
        of = detect_order_flow(candles, [1], "BULLISH")
        assert of is not None
        assert of.direction == "BULLISH"


class TestPullback:
    def test_pullback_via_liquidity_grab(self):
        candles = [
            _c(100, 105, 98, 102, i=0),
            _c(102, 106, 97, 99, i=1),
        ]
        pbs = detect_pullbacks_via_liquidity_grab(candles, 0, 1)
        assert len(pbs) == 1

    def test_first_pullback_after_poi(self):
        candles = [
            _c(100, 105, 98, 102, i=0),
            _c(102, 106, 97, 99, i=1),
            _c(99, 104, 98, 103, i=2),
        ]
        idx = find_first_pullback_after_poi(candles, 0)
        assert idx == 1


class TestScoring:
    def test_max_score(self):
        inp = ScoringInput(
            htf_aligned=True, has_bos=True, has_choch=True,
            idm_swept=True, ifc_confirms=True, has_order_block=True,
            has_fvg=True, liquidity_event=True, entry_scheme_valid=True,
            rr_strong=True,
        )
        score = calculate_score(inp)
        assert score == 100.0

    def test_zero_score(self):
        score = calculate_score(ScoringInput())
        assert score == 0.0

    def test_confidence_labels(self):
        assert confidence_label(85) == "VERY_STRONG"
        assert confidence_label(70) == "STRONG"
        assert confidence_label(55) == "MODERATE"
        assert confidence_label(40) == "WEAK"
        assert confidence_label(20) == "NO_SIGNAL"


class TestAdvancedSMCStrategy:
    def test_insufficient_data(self):
        strategy = AdvancedSMCStrategy(AdvancedSMCConfig())
        candles = [_c(100, 105, 95, 102, i=i) for i in range(5)]
        result = strategy.analyze(candles)
        assert result.direction == "NO_SIGNAL"
        assert any("Insufficient" in r for r in result.reasons)

    def test_no_signal_on_flat_data(self):
        strategy = AdvancedSMCStrategy(AdvancedSMCConfig())
        candles = [_c(100, 101, 99, 100, i=i) for i in range(30)]
        result = strategy.analyze(candles)
        assert result.direction == "NO_SIGNAL"

    def test_uptrend_may_produce_long(self):
        strategy = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        candles = []
        for i in range(40):
            base = 100 + i * 1.5
            h = base + 3 + (i % 3)
            l = base - 1
            c = base + 2
            candles.append(_c(base, h, l, c, vol=1000 + i * 50, i=i))
        result = strategy.analyze(candles)
        assert result.direction in ("LONG", "NO_SIGNAL")

    def test_invalid_config(self):
        config = AdvancedSMCConfig(htf="2H", middle_tf="30m", ltf="5m")
        assert config.is_valid_combo() is False

    def test_valid_config(self):
        config = AdvancedSMCConfig(htf="1D", middle_tf="15m", ltf="1m")
        assert config.is_valid_combo() is True

    def test_atr_computation(self):
        strategy = AdvancedSMCStrategy()
        candles = [
            _c(100, 105, 95, 102, i=0),
            _c(102, 108, 100, 106, i=1),
            _c(106, 110, 104, 108, i=2),
        ]
        atr = strategy._compute_atr(candles)
        assert atr > 0


class TestEntrySchemes:
    def test_scheme_1_idm_based(self):
        candles = [
            _c(100, 105, 98, 102, i=0),
            _c(102, 106, 97, 99, i=1),
            _c(99, 110, 98, 108, i=2),
        ]
        idms = [IDM(1, _ts(1), 97, "BULLISH", swept=True, sweep_index=2, sweep_timestamp=_ts(2))]
        obs = [OrderBlock("BULLISH", 100.0, 98.0, _ts(0), 0, has_imbalance=True)]
        result = try_scheme_1(candles, idms, [], obs, "BULLISH", 2.0)
        assert result.found is True
        assert result.entry_type == "IDM_BASED"
        assert result.entry_scheme == "SCHEME_1"

    def test_scheme_2_ifc_based(self):
        candles = [
            _c(100, 105, 98, 102, i=0),
            _c(102, 106, 97, 99, i=1),
        ]
        idms = [IDM(1, _ts(1), 97, "BULLISH", swept=True, sweep_index=1, sweep_timestamp=_ts(1))]
        ifcs = [IFC("BULLISH", 100, 97, 100, 97, _ts(1), 1, swept_liquidity=True, closes_through=True)]
        result = try_scheme_2(candles, idms, ifcs, "BULLISH", 2.0)
        assert result.found is True
        assert result.entry_scheme == "SCHEME_2"

    def test_scheme_4_direct_ifc(self):
        candles = [
            _c(100, 105, 98, 102, i=0),
            _c(102, 106, 95, 100, i=1),
        ]
        ifcs = [IFC("BULLISH", 106, 95, 102, 95, _ts(1), 1, swept_liquidity=True, closes_through=True)]
        result = try_scheme_4(candles, ifcs, "BULLISH", 2.0)
        assert result.found is True
        assert result.entry_scheme == "SCHEME_4"

    def test_evaluate_all_schemes_nothing(self):
        result = evaluate_all_schemes([], [], [], [], "BULLISH", 2.0)
        assert result.found is False


class TestBacktestRequirements:
    def test_lookahead_prevention(self):
        candles = [
            _c(100, 105, 98, 102, i=0),
            _c(102, 106, 97, 99, i=1),
            _c(99, 110, 98, 108, i=2),
            _c(108, 112, 107, 110, i=3),
            _c(110, 115, 109, 113, i=4),
        ]
        swings = detect_swings(candles, left=2, right=2)
        for s in swings:
            assert s.index < len(candles)

    def test_sequential_processing(self):
        candles = [
            _c(100, 105, 98, 102, i=0),
            _c(102, 106, 97, 99, i=1),
            _c(99, 110, 98, 108, i=2),
        ]
        strategy = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result = strategy.analyze(candles)
        assert result is not None
        assert isinstance(result.direction, str)
