"""Recommendation scoring now consumes the directional signal
(confidence / setup status / risk) without changing legacy behaviour when
those inputs are absent."""
from datetime import datetime

import pytest

from app.services.recommendation_engine import (
    RISK_SCORE_ADJUST,
    SETUP_STATUS_SCORE_ADJUST,
    compute_recommendation_score,
    classify_quality,
)


def _kwargs(**overrides) -> dict:
    base = dict(
        trade_status="WAITING_FOR_CONFIRMATION",
        direction="LONG",
        assessment_score=60,
        htf_bias="BULLISH",
        middle_bias="BULLISH",
        ltf_confirmation="LONG",
        has_bos=True,
        has_choch=True,
        idm_count=2,
        idm_swept=True,
        ifc_count=1,
        fvg_count=1,
        ob_count=1,
        liquidity_sweeps=1,
        entry_scheme_found=True,
        rr=3.0,
        last_analysis=datetime.utcnow(),
        timeframe="15m",
        has_entry=True,
    )
    base.update(overrides)
    return base


class TestLegacyBehaviourUnchanged:
    def test_explicit_none_inputs_equal_omitted_inputs(self):
        explicit = compute_recommendation_score(
            **_kwargs(confidence=None, setup_status=None, risk=None)
        )
        omitted = compute_recommendation_score(**{
            k: v for k, v in _kwargs().items()
            if k not in ("confidence", "setup_status", "risk")
        })
        assert explicit == omitted

    def test_neutral_insufficient_data_still_scores_zero(self):
        score = compute_recommendation_score(**_kwargs(
            direction="NEUTRAL",
            trade_status="INSUFFICIENT_DATA",
            confidence=95,
            setup_status="DEVELOPING",
        ))
        assert score == 0

    @pytest.mark.parametrize("setup,expected", [
        ("VALIDATED", 65),
        ("WATCH_LIKE", 30),
    ])
    def test_quality_bands_survive(self, setup, expected):
        # Validated setups with strong structure must stay in the HIGH band.
        if setup == "VALIDATED":
            score = compute_recommendation_score(**_kwargs(
                trade_status="VALIDATED",
                confidence=85,
                setup_status="VALIDATED",
                risk="LOW",
            ))
            assert score >= 65
        else:
            score = compute_recommendation_score(**_kwargs(
                trade_status="WAITING_FOR_CONFIRMATION",
                confidence=30,
                setup_status="DEVELOPING",
                risk="VERY HIGH",
                ltf_confirmation="NONE",
            ))
            assert 15 <= score <= 50


class TestConfidenceBlending:
    def test_higher_confidence_scores_higher(self):
        low = compute_recommendation_score(**_kwargs(confidence=20, setup_status="DEVELOPING"))
        high = compute_recommendation_score(**_kwargs(confidence=90, setup_status="DEVELOPING"))
        assert high > low

    def test_confidence_bounds_the_score(self):
        score = compute_recommendation_score(**_kwargs(confidence=100, setup_status="DEVELOPING", risk="VERY HIGH"))
        assert 0 <= score <= 100

    def test_confidence_can_lower_a_well_structured_score(self):
        confident = compute_recommendation_score(**_kwargs(confidence=90, setup_status="DEVELOPING"))
        unconfident = compute_recommendation_score(**_kwargs(confidence=10, setup_status="DEVELOPING"))
        assert unconfident < confident


class TestSetupStatusAdjustment:
    def test_validated_beats_developing(self):
        validated = compute_recommendation_score(**_kwargs(confidence=70, setup_status="VALIDATED"))
        developing = compute_recommendation_score(**_kwargs(confidence=70, setup_status="DEVELOPING"))
        assert validated > developing

    def test_invalidated_is_penalised(self):
        invalidated = compute_recommendation_score(**_kwargs(confidence=70, setup_status="INVALIDATED"))
        waiting = compute_recommendation_score(**_kwargs(confidence=70, setup_status="WAITING_FOR_CONFIRMATION"))
        assert invalidated < waiting
        assert invalidated < compute_recommendation_score(**_kwargs(confidence=70, setup_status="PARTIALLY_CONFIRMED"))

    def test_adjustments_are_applied_verbatim(self):
        validated = compute_recommendation_score(**_kwargs(confidence=70, setup_status="VALIDATED"))
        developing = compute_recommendation_score(**_kwargs(confidence=70, setup_status="DEVELOPING"))
        expected_delta = SETUP_STATUS_SCORE_ADJUST["VALIDATED"] - SETUP_STATUS_SCORE_ADJUST["DEVELOPING"]
        # freshness multiplier is 1.0 for a just-run analysis
        assert validated - developing == expected_delta


class TestRiskAdjustment:
    def test_low_risk_beats_very_high_risk(self):
        low = compute_recommendation_score(**_kwargs(confidence=70, setup_status="VALIDATED", risk="LOW"))
        extreme = compute_recommendation_score(**_kwargs(confidence=70, setup_status="VALIDATED", risk="VERY HIGH"))
        assert low > extreme

    def test_risk_adjustments_applied_verbatim(self):
        low = compute_recommendation_score(**_kwargs(confidence=70, setup_status="VALIDATED", risk="LOW"))
        high = compute_recommendation_score(**_kwargs(confidence=70, setup_status="VALIDATED", risk="HIGH"))
        expected_delta = RISK_SCORE_ADJUST["LOW"] - RISK_SCORE_ADJUST["HIGH"]
        assert low - high == expected_delta

    def test_unknown_risk_is_neutral(self):
        unknown = compute_recommendation_score(**_kwargs(confidence=70, setup_status="VALIDATED", risk="UNKNOWN"))
        without = compute_recommendation_score(**_kwargs(confidence=70, setup_status="VALIDATED"))
        assert unknown == without


class TestScoreAlwaysBounded:
    @pytest.mark.parametrize("confidence,setup,risk", [
        (100, "VALIDATED", "LOW"),
        (0, "INVALIDATED", "VERY HIGH"),
        (50, "DEVELOPING", "HIGH"),
        (100, "PARTIALLY_CONFIRMED", "MODERATE"),
    ])
    def test_bounds(self, confidence, setup, risk):
        score = compute_recommendation_score(
            **_kwargs(confidence=confidence, setup_status=setup, risk=risk)
        )
        assert 0 <= score <= 100

    def test_quality_labels_follow_score(self):
        assert classify_quality(85) == "EXTREME CONVICTION"
        assert classify_quality(70) == "HIGH CONVICTION"
        assert classify_quality(40) == "FAVOURED"
