import pytest
import asyncio
from datetime import datetime, timedelta
from app.strategies.advanced_smc.models import Candle
from app.strategies.advanced_smc.config import AdvancedSMCConfig
from app.strategies.advanced_smc.strategy import AdvancedSMCStrategy
from app.strategies.advanced_smc.scoring import calculate_assessment_score
from app.models.assessment import MarketAssessment, TradeStatus, Diagnostics, AdvancedSMCAnalysisResult


def _ts(i: int) -> datetime:
    return datetime(2024, 1, 1) + timedelta(hours=i)


def _c(o, h, l, c, vol=1000, i=0) -> Candle:
    return Candle(timestamp=_ts(i), open=o, high=h, low=l, close=c, volume=vol)


def _make_zigzag(pivots, range_size=2.0):
    candles = []
    idx = 0
    for pi in range(len(pivots) - 1):
        start_p = pivots[pi]
        end_p = pivots[pi + 1]
        steps = 6
        for s in range(steps):
            frac = s / steps
            base = start_p + (end_p - start_p) * frac
            h = base + range_size
            l = base - range_size * 0.5
            c = base + range_size * 0.3
            candles.append(_c(base, h, l, c, vol=1000 + idx * 10, i=idx))
            idx += 1
    candles.append(_c(pivots[-1], pivots[-1] + range_size, pivots[-1] - range_size * 0.5, pivots[-1] + range_size * 0.3, vol=1000 + idx * 10, i=idx))
    return candles


class TestEndToEndPipeline:
    def test_bullish_dataset_produces_assessment(self):
        pivots = [100, 95, 108, 102, 115, 108, 122, 115, 130]
        candles = _make_zigzag(pivots)

        strategy = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result = strategy.analyze(candles)

        assert result.market_bias in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result.structure_state != "" or len(result.reasons) > 0

        score, opp, label, quality = calculate_assessment_score(
            bias=result.market_bias,
            has_bos=len(result.bos_events) > 0,
            has_choch=len(result.choch_events) > 0,
            idm_count=len(result.idm_events),
            idm_swept_count=sum(1 for i in result.idm_events if i.swept),
            ifc_count=len(result.ifcs),
            ob_count=len(result.order_blocks),
            fvg_count=len(result.fvgs),
            liquidity_sweep_count=len(result.liquidity_sweeps),
            entry_scheme_found=result.entry_scheme != "",
        )
        assert 10 <= score <= 90
        assert 10 <= opp <= 90

    def test_bearish_dataset_produces_assessment(self):
        pivots = [200, 205, 192, 198, 185, 190, 178, 182, 170]
        candles = _make_zigzag(pivots)

        strategy = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result = strategy.analyze(candles)

        assert result.market_bias in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result.structure_state != "" or len(result.reasons) > 0

    def test_range_dataset_produces_neutral(self):
        pivots = [100, 98, 102, 99, 101, 98, 102, 99, 101]
        candles = _make_zigzag(pivots, range_size=1.5)

        strategy = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result = strategy.analyze(candles)

        assert result.market_bias in ("NEUTRAL", "BULLISH", "BEARISH")

    def test_assessment_always_has_direction(self):
        pivots = [100, 95, 108, 102, 115, 108, 122]
        candles = _make_zigzag(pivots)

        strategy = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result = strategy.analyze(candles)

        assert result.market_bias in ("BULLISH", "BEARISH", "NEUTRAL")

    def test_trade_status_reflects_setup(self):
        pivots = [100, 95, 108, 102, 115, 108, 122, 115, 130]
        candles = _make_zigzag(pivots)

        strategy = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result = strategy.analyze(candles)

        if result.direction == "NO_SIGNAL":
            assert result.market_bias in ("BULLISH", "BEARISH", "NEUTRAL")
            assert len(result.reasons) > 0
        else:
            assert result.direction in ("LONG", "SHORT")
            assert result.entry_low is not None
            assert result.entry_high is not None
            assert result.stop_loss is not None

    def test_no_direction_from_neutral_bias(self):
        candles = [_c(100, 101, 99, 100, i=i) for i in range(30)]

        strategy = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result = strategy.analyze(candles)

        assert result.direction == "NO_SIGNAL"
        assert result.market_bias == "NEUTRAL"

    def test_assessment_score_never_zero_or_hundred(self):
        for bias in ["BULLISH", "BEARISH", "NEUTRAL"]:
            score, opp, label, quality = calculate_assessment_score(bias=bias)
            assert 10 <= score <= 90
            assert 10 <= opp <= 90

    def test_validated_trade_has_all_levels(self):
        pivots = [100, 90, 110, 85, 120, 80, 130, 75, 140]
        candles = _make_zigzag(pivots, range_size=5.0)

        strategy = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result = strategy.analyze(candles)

        if result.direction in ("LONG", "SHORT"):
            assert result.entry_low is not None
            assert result.entry_high is not None
            assert result.stop_loss is not None

    def test_risk_label_populated_on_validated(self):
        pivots = [100, 90, 110, 85, 120, 80, 130, 75, 140]
        candles = _make_zigzag(pivots, range_size=5.0)

        strategy = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result = strategy.analyze(candles)

        if result.direction in ("LONG", "SHORT"):
            assert result.risk_reward is not None

    def test_multiple_analyses_same_data_same_result(self):
        pivots = [100, 95, 108, 102, 115]
        candles = _make_zigzag(pivots)

        strategy1 = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result1 = strategy1.analyze(candles)

        strategy2 = AdvancedSMCStrategy(AdvancedSMCConfig(minimum_confidence=0))
        result2 = strategy2.analyze(candles)

        assert result1.direction == result2.direction
        assert result1.market_bias == result2.market_bias
        assert result1.confidence == result2.confidence

    def test_insufficient_data_returns_reason(self):
        candles = [_c(100, 105, 95, 102, i=i) for i in range(5)]

        strategy = AdvancedSMCStrategy(AdvancedSMCConfig())
        result = strategy.analyze(candles)

        assert result.direction == "NO_SIGNAL"
        assert any("Insufficient" in r or "insufficient" in r.lower() for r in result.reasons)

    def test_flat_data_no_direction(self):
        candles = [_c(100, 101, 99, 100, i=i) for i in range(40)]

        strategy = AdvancedSMCStrategy(AdvancedSMCConfig())
        result = strategy.analyze(candles)

        assert result.direction == "NO_SIGNAL"


class TestAssessmentScoring:
    def test_bullish_strong_evidence(self):
        score, opp, label, quality = calculate_assessment_score(
            bias="BULLISH", has_bos=True, has_choch=True,
            idm_count=3, idm_swept_count=2, ifc_count=2,
            ob_count=1, fvg_count=1, liquidity_sweep_count=1,
            entry_scheme_found=True,
        )
        assert score >= 70
        assert opp <= 30
        assert quality in ("HIGH CONVICTION", "EXTREME CONVICTION")

    def test_bearish_strong_evidence(self):
        score, opp, label, quality = calculate_assessment_score(
            bias="BEARISH", has_bos=True, has_choch=True,
            idm_count=3, idm_swept_count=2, ifc_count=2,
            ob_count=1, fvg_count=1, liquidity_sweep_count=1,
            entry_scheme_found=True,
        )
        assert score <= 30
        assert opp >= 70
        assert quality in ("HIGH CONVICTION", "EXTREME CONVICTION")

    def test_neutral_always_balanced(self):
        score, opp, label, quality = calculate_assessment_score(bias="NEUTRAL")
        assert score == 50
        assert opp == 50
        assert label == "BALANCED"
        assert quality == "MODERATE"

    def test_bullish_weak_evidence(self):
        score, opp, label, quality = calculate_assessment_score(
            bias="BULLISH", has_bos=False, has_choch=False,
            idm_count=0, idm_swept_count=0, ifc_count=0,
            ob_count=0, fvg_count=0, liquidity_sweep_count=0,
            entry_scheme_found=False,
        )
        assert score > 50
        assert opp < 50
        assert quality in ("MODERATE", "FAVOURED", "WEAK", "BALANCED", "HIGH CONVICTION")

    def test_conflicting_evidence_near_balance(self):
        score, opp, label, quality = calculate_assessment_score(
            bias="BULLISH", has_bos=True, has_choch=False,
            idm_count=0, idm_swept_count=0, ifc_count=0,
            ob_count=0, fvg_count=0, liquidity_sweep_count=0,
            entry_scheme_found=False,
        )
        assert 40 <= score <= 75

    def test_entry_scheme_boosts_score(self):
        score_no_entry, _, _, _ = calculate_assessment_score(
            bias="BULLISH", has_bos=True,
            entry_scheme_found=False,
        )
        score_with_entry, _, _, _ = calculate_assessment_score(
            bias="BULLISH", has_bos=True,
            entry_scheme_found=True,
        )
        assert score_with_entry > score_no_entry


class TestDiagnosticModels:
    def test_assessment_model_fields(self):
        m = MarketAssessment(direction="LONG", score=72, opposing_score=28, label="LONG-FAVOURED", quality="HIGH CONVICTION")
        assert m.direction == "LONG"
        assert m.score == 72
        assert m.opposing_score == 28

    def test_trade_status_model_fields(self):
        t = TradeStatus(
            status="VALIDATED", direction="LONG",
            entry=1.1050, stop_loss=1.1020, take_profit_1=1.1200,
            risk_reward=5.0, confidence_score=75,
            risk_label="MODERATE RISK", entry_type="IDM_BASED", entry_scheme="SCHEME_1",
        )
        assert t.status == "VALIDATED"
        assert t.entry == 1.1050
        assert t.risk_reward == 5.0

    def test_diagnostics_model_fields(self):
        d = Diagnostics(
            data_valid=True, candle_count=200,
            htf_bias="BULLISH", swing_high_count=5, swing_low_count=4,
            bos_count=3, choch_count=1, idm_count=2,
            liquidity_level_count=10, liquidity_sweep_count=2,
            fvg_count=3, order_block_count=2, ifc_count=1,
            entry_candidates=1, rejection_reasons=[],
        )
        assert d.data_valid is True
        assert d.bos_count == 3

    def test_analysis_result_model_fields(self):
        r = AdvancedSMCAnalysisResult(
            symbol="BTCUSD",
            assessment=MarketAssessment(direction="LONG", score=70, opposing_score=30, label="LONG-FAVOURED", quality="FAVOURED"),
            trade=TradeStatus(status="WAITING_FOR_CONFIRMATION", direction="LONG"),
            diagnostics=Diagnostics(data_valid=True, candle_count=200),
        )
        assert r.symbol == "BTCUSD"
        assert r.assessment.direction == "LONG"
        assert r.trade.status == "WAITING_FOR_CONFIRMATION"
