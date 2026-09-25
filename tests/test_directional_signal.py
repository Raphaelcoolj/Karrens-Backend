"""Tests for the always-on directional signal engine (app/services/signal_engine.py).

The engine is the contract for Karren's new philosophy:
  DIRECTION -> CONFIDENCE -> SETUP STATUS -> RISK -> TRADE LEVELS
"""
import math
import pytest
from datetime import datetime, timedelta

from app.core.thresholds import SignalThresholds, get_thresholds
from app.models.signal import DirectionalSignal
from app.strategies.advanced_smc import AdvancedSMCStrategy, AdvancedSMCConfig, Candle
from app.services.signal_engine import (
    EvidenceWeights,
    EvidenceSummary,
    collect_evidence,
    choose_direction,
    compute_confidence,
    compute_risk_score,
    classify_risk,
    confidence_label,
    determine_setup_status,
    generate_directional_signal,
    build_reasons,
    STATUS_OK,
    STATUS_MARKET_DATA_UNAVAILABLE,
    STATUS_UPSTREAM_RATE_LIMITED,
    STATUS_INSUFFICIENT_DATA,
)


def _candles(count: int, base: float = 100.0, trend: float = 0.1, start: int = 0) -> list[Candle]:
    """Zigzag series with drift: yields real swing points for the detectors."""
    out, prev_close = [], base
    for i in range(start, start + count):
        center = base + trend * i
        wave = math.sin(i / 3.0) * 2.5
        o = prev_close
        c = center + wave
        out.append(
            Candle(
                timestamp=datetime(2026, 1, 1) + timedelta(hours=i),
                open=o, high=max(o, c) + 0.5, low=min(o, c) - 0.5,
                close=c, volume=1000 + i,
            )
        )
        prev_close = c
    return out


def _flat_candles(count: int = 40) -> list[Candle]:
    return [
        Candle(
            timestamp=datetime(2026, 1, 1) + timedelta(hours=i),
            open=100.0, high=101.0, low=99.0, close=100.0, volume=1000,
        )
        for i in range(count)
    ]


def _ta(structure: str = "bullish", ema: str = "bullish", change: float = 1.5) -> dict:
    return {
        "current_price": 100.0,
        "price_change_20": change,
        "market_structure": {"structure": structure, "trend": "uptrend", "details": ""},
        "momentum": {
            "rsi_zone": "neutral",
            "ema_alignment": ema,
            "macd_crossover": None,
        },
    }


# ──────────────────────────────────────────────
# Direction: always-on behaviour
# ──────────────────────────────────────────────
class TestAlwaysOnDirection:
    def test_sufficient_data_always_produces_direction(self):
        candles = _candles(120, trend=0.15)
        setup = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0)).analyze(candles=candles)
        signal = generate_directional_signal(setup=setup, technical_analysis=_ta())

        assert signal.status == STATUS_OK
        assert signal.direction in ("LONG", "SHORT")

    def test_flat_market_still_produces_direction(self):
        setup = AdvancedSMCStrategy(AdvancedSMCConfig()).analyze(candles=_flat_candles())
        signal = generate_directional_signal(setup=setup, technical_analysis=_ta(structure="undetermined", ema="neutral", change=0.0))

        assert signal.direction in ("LONG", "SHORT")
        assert signal.confidence <= 50

    def test_technical_analysis_only_still_produces_direction(self):
        signal = generate_directional_signal(setup=None, technical_analysis=_ta())

        assert signal.status == STATUS_OK
        assert signal.direction in ("LONG", "SHORT")
        assert signal.confidence > 0

    @pytest.mark.parametrize("status", [STATUS_MARKET_DATA_UNAVAILABLE, STATUS_UPSTREAM_RATE_LIMITED])
    def test_data_failure_never_manufactures_direction(self, status):
        signal = generate_directional_signal(status=status)

        assert signal.status == status
        assert signal.direction == "NEUTRAL"
        assert signal.confidence == 0
        assert signal.setup_status == "NONE"
        assert signal.risk == "UNKNOWN"
        assert signal.entry is None and signal.sl is None and signal.tp is None and signal.rr is None

    def test_insufficient_candles_reported_as_non_signal(self):
        setup = AdvancedSMCStrategy(AdvancedSMCConfig()).analyze(candles=_flat_candles(5))
        signal = generate_directional_signal(setup=setup, technical_analysis=_ta())

        assert signal.status == STATUS_INSUFFICIENT_DATA
        assert signal.direction == "NEUTRAL"
        assert signal.confidence == 0

    def test_missing_technical_analysis_without_setup_is_non_signal(self):
        signal = generate_directional_signal(setup=None, technical_analysis=None)

        assert signal.status == STATUS_INSUFFICIENT_DATA
        assert signal.direction == "NEUTRAL"

    def test_missing_ai_never_blocks_the_signal(self):
        # An engine result with no AI narrative must still carry a direction.
        signal = generate_directional_signal(setup=None, technical_analysis=_ta())
        assert signal.direction in ("LONG", "SHORT")
        assert signal.reasons


# ──────────────────────────────────────────────
# Confidence: bipolar, bounded, deterministic
# ──────────────────────────────────────────────
class TestConfidence:
    def test_one_sided_full_evidence_scores_100(self):
        assert compute_confidence(60, 0) == 100

    def test_zero_evidence_scores_zero(self):
        assert compute_confidence(0, 0) == 0

    def test_balanced_evidence_never_exceeds_50(self):
        assert compute_confidence(30, 30) == 50
        assert compute_confidence(3, 3) <= 50

    def test_more_evidence_scores_higher(self):
        assert compute_confidence(15, 0) < compute_confidence(30, 0) < compute_confidence(60, 0)

    def test_opposing_evidence_lowers_confidence(self):
        # Same total evidence, split across both sides -> weaker conviction.
        one_sided = compute_confidence(30, 0)
        contested = compute_confidence(20, 10)
        assert contested < one_sided

    def test_opposing_evidence_dominating_cuts_confidence_sharply(self):
        clean = compute_confidence(50, 0)
        majority_conflicted = compute_confidence(30, 20)
        assert majority_conflicted < clean

    def test_confidence_is_bounded_0_to_100(self):
        assert compute_confidence(10_000, 0) == 100
        assert compute_confidence(0, 10_000) == 100
        assert compute_confidence(-5, -5) == 0

    def test_confidence_is_deterministic(self):
        a = compute_confidence(43.5, 17.25)
        b = compute_confidence(43.5, 17.25)
        assert a == b

    def test_thinner_evidence_cannot_reach_top_tier(self):
        # Half the reference mass on one side only -> ~50, not ~100.
        assert compute_confidence(30, 0) < 60


# ──────────────────────────────────────────────
# Direction selection
# ──────────────────────────────────────────────
class TestDirectionSelection:
    def test_stronger_side_wins(self):
        assert choose_direction(EvidenceSummary(bullish=40, bearish=10)) == "LONG"
        assert choose_direction(EvidenceSummary(bullish=10, bearish=40)) == "SHORT"

    def test_tie_breaks_to_htf_bias(self):
        summary = EvidenceSummary(bullish=20, bearish=20)
        class Setup:
            htf_bias = "BEARISH"
            market_bias = "BULLISH"
            ltf_bias = "NEUTRAL"
        assert choose_direction(summary, Setup()) == "SHORT"

    def test_empty_evidence_still_returns_a_direction(self):
        assert choose_direction(EvidenceSummary()) in ("LONG", "SHORT")

    def test_direction_prefers_the_side_with_more_evidence_from_setup(self):
        setup_bull = type("S", (), {
            "htf_bias": "BULLISH", "market_bias": "BULLISH", "ltf_bias": "BULLISH",
        })()
        summary = collect_evidence(setup_bull, _ta())
        assert choose_direction(summary, setup_bull) == "LONG"

        setup_bear = type("S", (), {
            "htf_bias": "BEARISH", "market_bias": "BEARISH", "ltf_bias": "BEARISH",
        })()
        summary = collect_evidence(setup_bear, _ta(structure="bearish", ema="bearish", change=-2.0))
        assert choose_direction(summary, setup_bear) == "SHORT"


# ──────────────────────────────────────────────
# Evidence collection: advanced SMC detections are evidence, not gates
# ──────────────────────────────────────────────
class TestEvidenceCollection:
    def test_timeframe_biases_contribute(self):
        setup = type("S", (), {
            "htf_bias": "BULLISH", "htf_timeframe": "1D",
            "market_bias": "BULLISH", "ltf_bias": "NEUTRAL",
            "bos_events": [], "choch_events": [], "idm_events": [],
            "liquidity_sweeps": [], "ifcs": [], "order_blocks": [],
            "fvgs": [], "entry_scheme": "", "poi_zone": None,
        })()
        summary = collect_evidence(setup, None)
        assert summary.bullish > 0
        assert summary.bearish == 0

    def test_conflicting_bias_adds_to_both_sides(self):
        bull = type("S", (), {
            "htf_bias": "BULLISH", "htf_timeframe": "1D", "market_bias": "BEARISH",
            "ltf_bias": "NEUTRAL", "bos_events": [], "choch_events": [], "idm_events": [],
            "liquidity_sweeps": [], "ifcs": [], "order_blocks": [], "fvgs": [],
            "entry_scheme": "", "poi_zone": None,
        })()
        summary = collect_evidence(bull, None)
        assert summary.bullish > 0 and summary.bearish > 0

    def test_unswept_idm_is_not_scored(self):
        idm = type("I", (), {"direction": "BULLISH", "swept": False})()
        setup = type("S", (), {
            "htf_bias": "NEUTRAL", "htf_timeframe": "", "market_bias": "NEUTRAL",
            "ltf_bias": "NEUTRAL", "bos_events": [], "choch_events": [], "idm_events": [idm],
            "liquidity_sweeps": [], "ifcs": [], "order_blocks": [], "fvgs": [],
            "entry_scheme": "", "poi_zone": None,
        })()
        summary = collect_evidence(setup, None)
        assert summary.bullish == 0
        assert summary.bearish == 0

    def test_swept_idm_is_scored(self):
        idm = type("I", (), {"direction": "BULLISH", "swept": True})()
        setup = type("S", (), {
            "htf_bias": "NEUTRAL", "htf_timeframe": "", "market_bias": "NEUTRAL",
            "ltf_bias": "NEUTRAL", "bos_events": [], "choch_events": [], "idm_events": [idm],
            "liquidity_sweeps": [], "ifcs": [], "order_blocks": [], "fvgs": [],
            "entry_scheme": "", "poi_zone": None,
        })()
        summary = collect_evidence(setup, None)
        assert summary.bullish > 0

    def test_ta_evidence_is_bipolar(self):
        summary = collect_evidence(None, _ta(structure="bearish", ema="bearish", change=-3.0))
        assert summary.bearish > 0
        assert summary.bullish == 0

    def test_event_counts_are_capped(self):
        weights = EvidenceWeights()
        events = [type("E", (), {"direction": "BULLISH"})() for _ in range(10)]
        setup = type("S", (), {
            "htf_bias": "NEUTRAL", "htf_timeframe": "", "market_bias": "NEUTRAL",
            "ltf_bias": "NEUTRAL", "bos_events": events, "choch_events": [],
            "idm_events": [], "liquidity_sweeps": [], "ifcs": [], "order_blocks": [],
            "fvgs": [], "entry_scheme": "", "poi_zone": None,
        })()
        summary = collect_evidence(setup, None, weights)
        assert summary.bullish == pytest.approx(weights.bos_event * weights.bos_max_events)

    def test_engine_is_deterministic(self):
        candles = _candles(100, trend=0.12)
        setup = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0)).analyze(candles=candles)
        first = generate_directional_signal(setup=setup, technical_analysis=_ta())
        second = generate_directional_signal(setup=setup, technical_analysis=_ta())
        assert first.model_dump() == second.model_dump()


# ──────────────────────────────────────────────
# Setup status: separate axis from direction
# ──────────────────────────────────────────────
class TestSetupStatus:
    def _setup(self, **kwargs):
        base = dict(
            direction="NO_SIGNAL", rejection_reason="", market_bias="NEUTRAL",
            htf_bias="NEUTRAL", ltf_bias="NEUTRAL", bos_events=[], choch_events=[],
            idm_events=[], ifcs=[], entry_scheme="", liquidity_sweeps=[],
            order_blocks=[], fvgs=[], poi_zone=None, entry_low=None, entry_high=None,
            stop_loss=None, take_profit_1=None, take_profit_2=None, take_profit_3=None,
            risk_reward=None, confidence=0.0, reasons=[], invalidation_conditions=[],
            structure_state="", symbol="", htf_labels=[], middle_labels=[],
        )
        base.update(kwargs)
        return type("Setup", (), base)()

    def test_validated_requires_complete_levels(self):
        setup = self._setup(
            direction="LONG", entry_low=100.0, entry_high=101.0, stop_loss=99.0,
            take_profit_1=104.0, risk_reward=3.0,
        )
        assert determine_setup_status(setup) == "VALIDATED"

    def test_direction_without_levels_is_not_validated(self):
        setup = self._setup(direction="LONG")
        status = determine_setup_status(setup)
        assert status != "VALIDATED"

    def test_rejected_candidate_is_invalidated(self):
        setup = self._setup(rejection_reason="INVALID_RR")
        assert determine_setup_status(setup) == "INVALIDATED"

    def test_low_confidence_candidate_is_invalidated(self):
        setup = self._setup(rejection_reason="LOW_CONFIDENCE")
        assert determine_setup_status(setup) == "INVALIDATED"

    def test_single_confirmation_is_waiting(self):
        setup = self._setup(bos_events=[object()])
        assert determine_setup_status(setup) == "WAITING_FOR_CONFIRMATION"

    def test_two_confirmations_are_partially_confirmed(self):
        setup = self._setup(bos_events=[object()], ifcs=[object()])
        assert determine_setup_status(setup) == "PARTIALLY_CONFIRMED"

    def test_no_confirmations_is_developing(self):
        assert determine_setup_status(self._setup()) == "DEVELOPING"

    def test_unswept_idm_is_waiting(self):
        idm = type("I", (), {"swept": False, "direction": "BULLISH"})()
        setup = self._setup(idm_events=[idm])
        assert determine_setup_status(setup) == "WAITING_FOR_CONFIRMATION"

    def test_no_setup_object_is_developing(self):
        assert determine_setup_status(None) == "DEVELOPING"


# ──────────────────────────────────────────────
# Levels: never fabricated
# ──────────────────────────────────────────────
class TestNoFabricatedLevels:
    def test_levels_exposed_only_for_validated_setup(self):
        setup = type("Setup", (), dict(
            direction="LONG", rejection_reason="", market_bias="BULLISH",
            htf_bias="BULLISH", ltf_bias="BULLISH",
            bos_events=[object()], choch_events=[], idm_events=[], ifcs=[object()],
            entry_scheme="SCHEME_1", liquidity_sweeps=[], order_blocks=[], fvgs=[],
            poi_zone=type("Z", (), {"direction": "BULLISH", "type": "OB_IDM"})(),
            entry_low=100.0, entry_high=101.0, stop_loss=99.0,
            take_profit_1=105.0, take_profit_2=108.0, take_profit_3=110.0,
            risk_reward=4.0, confidence=70.0, reasons=[], invalidation_conditions=[],
            structure_state="", symbol="", htf_labels=[], middle_labels=[],
        ))()
        signal = generate_directional_signal(setup=setup, technical_analysis=_ta())

        assert signal.setup_status == "VALIDATED"
        assert signal.entry == 100.0
        assert signal.sl == 99.0
        assert signal.tp == 105.0
        assert signal.rr == 4.0

    def test_levels_withheld_when_setup_incomplete(self):
        candles = _candles(100, trend=0.1)
        setup = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0)).analyze(candles=candles)
        signal = generate_directional_signal(setup=setup, technical_analysis=_ta())

        if signal.setup_status != "VALIDATED":
            assert signal.entry is None and signal.sl is None and signal.tp is None and signal.rr is None

    def test_levels_never_appear_on_data_failure(self):
        signal = generate_directional_signal(status=STATUS_MARKET_DATA_UNAVAILABLE)
        assert (signal.entry, signal.sl, signal.tp, signal.rr) == (None, None, None, None)


# ──────────────────────────────────────────────
# Risk: an independent axis
# ──────────────────────────────────────────────
class TestRisk:
    def test_validated_setup_scores_low_risk(self):
        score = compute_risk_score(
            setup_status="VALIDATED", direction="LONG",
            htf_bias="BULLISH", middle_bias="BULLISH", ltf_bias="BULLISH",
            bullish=50, bearish=5, rr=3.0,
        )
        assert classify_risk(score) == "LOW"

    def test_developing_setup_scores_higher_risk_than_validated(self):
        validated = compute_risk_score("VALIDATED", "LONG", bullish=50, bearish=5, rr=3.0)
        developing = compute_risk_score("DEVELOPING", "LONG", bullish=50, bearish=5, rr=None)
        assert developing > validated

    def test_timeframe_conflict_increases_risk(self):
        aligned = compute_risk_score("VALIDATED", "LONG", htf_bias="BULLISH", bullish=50, bearish=5, rr=3.0)
        conflicting = compute_risk_score("VALIDATED", "LONG", htf_bias="BEARISH", bullish=50, bearish=5, rr=3.0)
        assert conflicting > aligned

    def test_large_opposing_evidence_increases_risk(self):
        balanced = compute_risk_score("DEVELOPING", "LONG", bullish=30, bearish=30, rr=None)
        one_sided = compute_risk_score("DEVELOPING", "LONG", bullish=55, bearish=5, rr=3.0)
        assert balanced > one_sided

    def test_bad_data_quality_increases_risk(self):
        good = compute_risk_score("VALIDATED", "LONG", bullish=50, bearish=5, rr=3.0, data_quality_ok=True)
        bad = compute_risk_score("VALIDATED", "LONG", bullish=50, bearish=5, rr=3.0, data_quality_ok=False)
        assert bad > good

    def test_risk_tier_labels(self):
        assert classify_risk(1) == "LOW"
        assert classify_risk(3) == "MODERATE"
        assert classify_risk(5) == "HIGH"
        assert classify_risk(7) == "VERY HIGH"

    def test_risk_is_not_confidence(self):
        # A high-conviction but unconfirmed view is still risky...
        high_conviction_developing = compute_risk_score("DEVELOPING", "LONG", bullish=60, bearish=0, rr=None)
        assert high_conviction_developing >= 4

        # ...while a validated structure with modest evidence is not.
        validated = compute_risk_score("VALIDATED", "LONG", htf_bias="BULLISH", middle_bias="BULLISH",
                                       ltf_bias="BULLISH", bullish=30, bearish=5, rr=3.0)
        assert classify_risk(validated) == "LOW"


# ──────────────────────────────────────────────
# Labels + reasons
# ──────────────────────────────────────────────
class TestLabelsAndReasons:
    @pytest.mark.parametrize("score,expected", [
        (84, "VERY HIGH"), (74, "HIGH"), (64, "MODERATE"), (54, "LOW"), (49, "VERY LOW"), (0, "VERY LOW"),
    ])
    def test_confidence_tier_labels(self, score, expected):
        assert confidence_label(score) == expected

    def test_signal_carries_label_matching_confidence(self):
        signal = generate_directional_signal(setup=None, technical_analysis=_ta())
        th = get_thresholds()
        assert signal.confidence_label == th.confidence_label(signal.confidence)

    def test_reasons_reference_detected_evidence_only(self):
        setup = type("S", (), {
            "htf_bias": "BULLISH", "htf_timeframe": "1D", "market_bias": "BULLISH",
            "ltf_bias": "BEARISH", "bos_events": [], "choch_events": [], "idm_events": [],
            "liquidity_sweeps": [], "ifcs": [], "order_blocks": [], "fvgs": [],
            "entry_scheme": "", "poi_zone": None,
            "direction": "NO_SIGNAL", "rejection_reason": "NO_DIRECTION",
        })()
        signal = generate_directional_signal(setup=setup, technical_analysis=None)

        joined = " | ".join(signal.reasons)
        assert "HTF (1D) bullish structure" in joined
        assert "LTF confirmation pending" in joined
        # nothing invented about BOS/entry that does not exist
        assert "BOS confirmed" not in joined

    def test_reasons_include_pending_markers(self):
        setup = type("S", (), {
            "htf_bias": "NEUTRAL", "htf_timeframe": "", "market_bias": "BULLISH",
            "ltf_bias": "NEUTRAL", "bos_events": [], "choch_events": [], "idm_events": [],
            "liquidity_sweeps": [], "ifcs": [], "order_blocks": [], "fvgs": [],
            "entry_scheme": "", "poi_zone": None,
            "direction": "NO_SIGNAL", "rejection_reason": "NO_DIRECTION",
            "reasons": [],
        })()
        reasons = build_reasons(collect_evidence(setup, None), "LONG", "DEVELOPING", setup)
        assert "No confirmed BOS/CHoCH" in reasons
        assert "Awaiting entry confirmation" in reasons

    def test_risk_and_setup_survive_serialisation(self):
        signal = generate_directional_signal(setup=None, technical_analysis=_ta())
        dumped = signal.model_dump()
        assert dumped["direction"] in ("LONG", "SHORT")
        assert isinstance(dumped["confidence"], int)
        assert 0 <= dumped["confidence"] <= 100
        assert dumped["setup_status"] in (
            "DEVELOPING", "WAITING_FOR_CONFIRMATION", "PARTIALLY_CONFIRMED",
            "VALIDATED", "INVALIDATED", "NONE",
        )
        assert dumped["risk"] in ("LOW", "MODERATE", "HIGH", "VERY HIGH", "UNKNOWN")


# ──────────────────────────────────────────────
# Threshold configuration
# ──────────────────────────────────────────────
class TestThresholdConfiguration:
    def test_tiers_are_ordered_high_to_low(self):
        th = SignalThresholds()
        bounds = [b for b, _ in th.confidence_tiers]
        assert bounds == sorted(bounds, reverse=True)

    def test_risk_tiers_are_ordered_low_to_high(self):
        th = SignalThresholds()
        bounds = [b for b, _ in th.risk_tiers]
        assert bounds == sorted(bounds)

    def test_label_falls_back_to_last_tier(self):
        th = SignalThresholds(confidence_tiers=((90, "VERY HIGH"), (0, "LOW")))
        assert th.confidence_label(10) == "LOW"
        assert th.confidence_label(95) == "VERY HIGH"

    def test_defaults_expose_notification_policy(self):
        th = get_thresholds()
        assert th.notify_min_confidence == 70
        assert th.notify_min_confidence_delta == 10
        assert th.notify_on_direction_change is True
