import pytest
from datetime import datetime, timedelta
from app.services.recommendation_engine import (
    compute_recommendation_fingerprint,
    compute_multi_tf_score,
    compute_structure_score,
    compute_rr_score,
    compute_freshness_penalty,
    compute_setup_completeness,
    compute_recommendation_score,
    classify_quality,
    classify_asset,
    determine_recommendation_status,
    generate_reasons,
    generate_negative_factors,
    determine_ltf_confirmation,
)


# ──────────────────────────────────────────────
# Recommendation Fingerprint
# ──────────────────────────────────────────────

class TestRecommendationFingerprint:
    def test_identical_state_same_fingerprint(self):
        fp1 = compute_recommendation_fingerprint("BTCUSD", "15m", "LONG", "VALIDATED", 77.20, 75.80, 82.50, "BULLISH")
        fp2 = compute_recommendation_fingerprint("BTCUSD", "15m", "LONG", "VALIDATED", 77.20, 75.80, 82.50, "BULLISH")
        assert fp1 == fp2

    def test_different_symbol_different_fingerprint(self):
        fp1 = compute_recommendation_fingerprint("BTCUSD", "15m", "LONG", "VALIDATED", 77.20, 75.80, 82.50, "BULLISH")
        fp2 = compute_recommendation_fingerprint("ETHUSD", "15m", "LONG", "VALIDATED", 77.20, 75.80, 82.50, "BULLISH")
        assert fp1 != fp2

    def test_different_direction_different_fingerprint(self):
        fp1 = compute_recommendation_fingerprint("BTCUSD", "15m", "LONG", "VALIDATED", 77.20, 75.80, 82.50, "BULLISH")
        fp2 = compute_recommendation_fingerprint("BTCUSD", "15m", "SHORT", "VALIDATED", 77.20, 75.80, 82.50, "BULLISH")
        assert fp1 != fp2

    def test_different_status_different_fingerprint(self):
        fp1 = compute_recommendation_fingerprint("BTCUSD", "15m", "LONG", "VALIDATED", 77.20, 75.80, 82.50, "BULLISH")
        fp2 = compute_recommendation_fingerprint("BTCUSD", "15m", "LONG", "WATCH", 77.20, 75.80, 82.50, "BULLISH")
        assert fp1 != fp2

    def test_different_entry_different_fingerprint(self):
        fp1 = compute_recommendation_fingerprint("BTCUSD", "15m", "LONG", "VALIDATED", 77.20, 75.80, 82.50, "BULLISH")
        fp2 = compute_recommendation_fingerprint("BTCUSD", "15m", "LONG", "VALIDATED", 78.00, 75.80, 82.50, "BULLISH")
        assert fp1 != fp2

    def test_fingerprint_is_hex_32(self):
        fp = compute_recommendation_fingerprint("EURUSD", "4H", "SHORT", "WATCH", 1.17342, None, None, "BEARISH")
        assert len(fp) == 32
        assert all(c in "0123456789abcdef" for c in fp)


# ──────────────────────────────────────────────
# Multi-TF Score
# ──────────────────────────────────────────────

class TestMultiTFScore:
    def test_all_aligned_long(self):
        score = compute_multi_tf_score("LONG", "LONG", "LONG", "LONG")
        assert score == 100

    def test_all_aligned_short(self):
        score = compute_multi_tf_score("SHORT", "SHORT", "SHORT", "SHORT")
        assert score == 100

    def test_htf_middle_aligned_no_ltf(self):
        score = compute_multi_tf_score("LONG", "LONG", "NONE", "LONG")
        assert score == 65

    def test_only_htf_aligned(self):
        score = compute_multi_tf_score("LONG", "NEUTRAL", "NONE", "LONG")
        assert score == 35

    def test_only_middle_aligned(self):
        score = compute_multi_tf_score("NEUTRAL", "LONG", "NONE", "LONG")
        assert score == 30

    def test_no_alignment(self):
        score = compute_multi_tf_score("SHORT", "SHORT", "SHORT", "LONG")
        assert score == 0

    def test_neutral_direction_zero(self):
        score = compute_multi_tf_score("LONG", "LONG", "LONG", "NEUTRAL")
        assert score == 0

    def test_htf_middle_ltf_all_conflicting(self):
        score = compute_multi_tf_score("SHORT", "SHORT", "SHORT", "LONG")
        assert score == 0


# ──────────────────────────────────────────────
# Structure Score
# ──────────────────────────────────────────────

class TestStructureScore:
    def test_full_structure(self):
        score = compute_structure_score(
            has_bos=True, has_choch=True, idm_count=3, idm_swept=True,
            ifc_count=2, fvg_count=1, ob_count=1, liquidity_sweeps=2, entry_scheme_found=True,
        )
        assert score == 100

    def test_no_structure(self):
        score = compute_structure_score(
            has_bos=False, has_choch=False, idm_count=0, idm_swept=False,
            ifc_count=0, fvg_count=0, ob_count=0, liquidity_sweeps=0, entry_scheme_found=False,
        )
        assert score == 0

    def test_bos_only(self):
        score = compute_structure_score(
            has_bos=True, has_choch=False, idm_count=0, idm_swept=False,
            ifc_count=0, fvg_count=0, ob_count=0, liquidity_sweeps=0, entry_scheme_found=False,
        )
        assert score == 15

    def test_entry_scheme_only(self):
        score = compute_structure_score(
            has_bos=False, has_choch=False, idm_count=0, idm_swept=False,
            ifc_count=0, fvg_count=0, ob_count=0, liquidity_sweeps=0, entry_scheme_found=True,
        )
        assert score == 20

    def test_idm_swept_only(self):
        score = compute_structure_score(
            has_bos=False, has_choch=False, idm_count=1, idm_swept=True,
            ifc_count=0, fvg_count=0, ob_count=0, liquidity_sweeps=0, entry_scheme_found=False,
        )
        assert score == 23

    def test_capped_at_100(self):
        score = compute_structure_score(
            has_bos=True, has_choch=True, idm_count=5, idm_swept=True,
            ifc_count=5, fvg_count=5, ob_count=5, liquidity_sweeps=5, entry_scheme_found=True,
        )
        assert score == 100


# ──────────────────────────────────────────────
# RR Score
# ──────────────────────────────────────────────

class TestRRScore:
    def test_no_rr(self):
        assert compute_rr_score(None) == 0

    def test_low_rr(self):
        assert compute_rr_score(0.5) == 0

    def test_rr_one(self):
        assert compute_rr_score(1.0) == 40

    def test_rr_two(self):
        assert compute_rr_score(2.0) == 60

    def test_rr_three(self):
        assert compute_rr_score(3.0) == 80

    def test_rr_five(self):
        assert compute_rr_score(5.0) == 100

    def test_rr_ten(self):
        assert compute_rr_score(10.0) == 100


# ──────────────────────────────────────────────
# Freshness Penalty
# ──────────────────────────────────────────────

class TestFreshnessPenalty:
    def test_very_fresh(self):
        penalty = compute_freshness_penalty(datetime.utcnow(), "15m")
        assert penalty == 1.0

    def test_no_timestamp(self):
        penalty = compute_freshness_penalty(None, "15m")
        assert penalty == 0.5

    def test_aging(self):
        penalty = compute_freshness_penalty(datetime.utcnow() - timedelta(minutes=25), "15m")
        assert penalty == 0.8

    def test_stale(self):
        penalty = compute_freshness_penalty(datetime.utcnow() - timedelta(minutes=45), "15m")
        assert penalty == 0.5

    def test_very_stale(self):
        penalty = compute_freshness_penalty(datetime.utcnow() - timedelta(hours=2), "15m")
        assert penalty == 0.2

    def test_daily_fresh(self):
        penalty = compute_freshness_penalty(datetime.utcnow() - timedelta(hours=8), "1D")
        assert penalty == 1.0

    def test_daily_stale(self):
        penalty = compute_freshness_penalty(datetime.utcnow() - timedelta(days=3), "1D")
        assert penalty == 0.2


# ──────────────────────────────────────────────
# Setup Completeness
# ──────────────────────────────────────────────

class TestSetupCompleteness:
    def test_full_setup(self):
        score = compute_setup_completeness(True, True, True, True, True, True, True)
        assert score == 100

    def test_empty_setup(self):
        score = compute_setup_completeness(False, False, False, False, False, False, False)
        assert score == 0

    def test_half_setup(self):
        score = compute_setup_completeness(True, True, True, False, False, False, False)
        assert score == 33


# ──────────────────────────────────────────────
# Full Recommendation Score
# ──────────────────────────────────────────────

class TestRecommendationScore:
    def test_validated_long_high_quality(self):
        score = compute_recommendation_score(
            trade_status="VALIDATED",
            direction="LONG",
            assessment_score=72,
            htf_bias="LONG",
            middle_bias="LONG",
            ltf_confirmation="LONG",
            has_bos=True,
            has_choch=True,
            idm_count=2,
            idm_swept=True,
            ifc_count=2,
            fvg_count=1,
            ob_count=1,
            liquidity_sweeps=2,
            entry_scheme_found=True,
            rr=3.5,
            last_analysis=datetime.utcnow(),
            timeframe="15m",
            has_entry=True,
        )
        assert score >= 65
        assert score <= 100

    def test_neutral_no_setup_zero(self):
        score = compute_recommendation_score(
            trade_status="NO_SETUP",
            direction="NEUTRAL",
            assessment_score=50,
            htf_bias="NEUTRAL",
            middle_bias="NEUTRAL",
            ltf_confirmation="NONE",
            has_bos=False,
            has_choch=False,
            idm_count=0,
            idm_swept=False,
            ifc_count=0,
            fvg_count=0,
            ob_count=0,
            liquidity_sweeps=0,
            entry_scheme_found=False,
            rr=None,
            last_analysis=datetime.utcnow(),
            timeframe="15m",
            has_entry=False,
        )
        assert score == 0

    def test_watch_low_score(self):
        score = compute_recommendation_score(
            trade_status="WAITING_FOR_CONFIRMATION",
            direction="LONG",
            assessment_score=40,
            htf_bias="LONG",
            middle_bias="NEUTRAL",
            ltf_confirmation="NONE",
            has_bos=False,
            has_choch=False,
            idm_count=1,
            idm_swept=False,
            ifc_count=0,
            fvg_count=0,
            ob_count=0,
            liquidity_sweeps=0,
            entry_scheme_found=False,
            rr=None,
            last_analysis=datetime.utcnow(),
            timeframe="15m",
            has_entry=False,
        )
        assert 15 <= score <= 50

    def test_stale_analysis_lower_score(self):
        fresh = compute_recommendation_score(
            trade_status="VALIDATED", direction="LONG", assessment_score=72,
            htf_bias="LONG", middle_bias="LONG", ltf_confirmation="LONG",
            has_bos=True, has_choch=True, idm_count=2, idm_swept=True,
            ifc_count=2, fvg_count=1, ob_count=1, liquidity_sweeps=2,
            entry_scheme_found=True, rr=3.5,
            last_analysis=datetime.utcnow(), timeframe="15m", has_entry=True,
        )
        stale = compute_recommendation_score(
            trade_status="VALIDATED", direction="LONG", assessment_score=72,
            htf_bias="LONG", middle_bias="LONG", ltf_confirmation="LONG",
            has_bos=True, has_choch=True, idm_count=2, idm_swept=True,
            ifc_count=2, fvg_count=1, ob_count=1, liquidity_sweeps=2,
            entry_scheme_found=True, rr=3.5,
            last_analysis=datetime.utcnow() - timedelta(hours=2), timeframe="15m", has_entry=True,
        )
        assert fresh > stale

    def test_no_rr_lower_score(self):
        with_rr = compute_recommendation_score(
            trade_status="VALIDATED", direction="LONG", assessment_score=72,
            htf_bias="LONG", middle_bias="LONG", ltf_confirmation="LONG",
            has_bos=True, has_choch=True, idm_count=2, idm_swept=True,
            ifc_count=2, fvg_count=1, ob_count=1, liquidity_sweeps=2,
            entry_scheme_found=True, rr=3.5,
            last_analysis=datetime.utcnow(), timeframe="15m", has_entry=True,
        )
        without_rr = compute_recommendation_score(
            trade_status="VALIDATED", direction="LONG", assessment_score=72,
            htf_bias="LONG", middle_bias="LONG", ltf_confirmation="LONG",
            has_bos=True, has_choch=True, idm_count=2, idm_swept=True,
            ifc_count=2, fvg_count=1, ob_count=1, liquidity_sweeps=2,
            entry_scheme_found=True, rr=None,
            last_analysis=datetime.utcnow(), timeframe="15m", has_entry=True,
        )
        assert with_rr > without_rr


# ──────────────────────────────────────────────
# Quality Classification
# ──────────────────────────────────────────────

class TestClassifyQuality:
    def test_extreme(self):
        assert classify_quality(85) == "EXTREME CONVICTION"

    def test_high(self):
        assert classify_quality(70) == "HIGH CONVICTION"

    def test_moderate(self):
        assert classify_quality(55) == "MODERATE"

    def test_favoured(self):
        assert classify_quality(40) == "FAVOURED"

    def test_low(self):
        assert classify_quality(20) == "LOW"

    def test_boundary_extreme(self):
        assert classify_quality(80) == "EXTREME CONVICTION"

    def test_boundary_high(self):
        assert classify_quality(65) == "HIGH CONVICTION"


# ──────────────────────────────────────────────
# Asset Classification
# ──────────────────────────────────────────────

class TestClassifyAsset:
    def test_crypto(self):
        assert classify_asset("BTCUSD") == "crypto"
        assert classify_asset("ETHUSD") == "crypto"

    def test_forex(self):
        assert classify_asset("EURUSD") == "forex"
        assert classify_asset("GBPUSD") == "forex"

    def test_commodity(self):
        assert classify_asset("XAUUSD") == "commodity"

    def test_unknown(self):
        assert classify_asset("XYZABC") == "unknown"


# ──────────────────────────────────────────────
# Recommendation Status
# ──────────────────────────────────────────────

class TestRecommendationStatus:
    def test_validated_with_entry(self):
        assert determine_recommendation_status("VALIDATED", "LONG", True, 75) == "VALIDATED"

    def test_validated_no_entry(self):
        assert determine_recommendation_status("VALIDATED", "LONG", False, 75) == "WAITING_FOR_CONFIRMATION"

    def test_invalidated(self):
        assert determine_recommendation_status("INVALIDATED", "LONG", True, 75) == "INVALIDATED"

    def test_waiting(self):
        assert determine_recommendation_status("WAITING_FOR_CONFIRMATION", "SHORT", False, 60) == "WAITING_FOR_CONFIRMATION"

    def test_watch_with_direction(self):
        assert determine_recommendation_status("NO_SETUP", "LONG", False, 30) == "WATCH"

    def test_neutral_low_score(self):
        assert determine_recommendation_status("NO_SETUP", "NEUTRAL", False, 10) == "WATCH"


# ──────────────────────────────────────────────
# Reasons Generation
# ──────────────────────────────────────────────

class TestGenerateReasons:
    def test_full_reasons(self):
        reasons = generate_reasons(
            "LONG", "LONG", "LONG", "LONG",
            True, True, 2, True, 1, "scheme_1", "VALIDATED", True,
        )
        assert "HTF long structure" in reasons
        assert "Middle-TF long structure" in reasons
        assert "LTF confirmation present" in reasons
        assert "BOS detected" in reasons
        assert "CHoCH confirmed" in reasons
        assert "IDM liquidity swept" in reasons
        assert "IFC confirmation present" in reasons
        assert "Entry scheme scheme_1" in reasons
        assert "Entry validated" in reasons

    def test_no_reasons_neutral(self):
        reasons = generate_reasons(
            "NEUTRAL", "NEUTRAL", "NEUTRAL", "NONE",
            False, False, 0, False, 0, "", "NO_SETUP", False,
        )
        assert len(reasons) <= 3
        assert all("neutral" in r.lower() for r in reasons)

    def test_pending_ltf(self):
        reasons = generate_reasons(
            "LONG", "LONG", "LONG", "NONE",
            False, False, 0, False, 0, "", "WAITING_FOR_CONFIRMATION", False,
        )
        assert "LTF confirmation pending" in reasons
        assert "Awaiting entry confirmation" in reasons

    def test_idm_pending_sweep(self):
        reasons = generate_reasons(
            "LONG", "LONG", "LONG", "LONG",
            True, False, 2, False, 0, "", "WAITING_FOR_CONFIRMATION", False,
        )
        assert "2 IDM(s) pending sweep" in reasons


# ──────────────────────────────────────────────
# Negative Factors
# ──────────────────────────────────────────────

class TestGenerateNegativeFactors:
    def test_no_negatives_full_setup(self):
        negatives = generate_negative_factors(
            "LONG", "LONG", "LONG", "LONG",
            True, True, True, 2, 3.5, True, "VALIDATED",
        )
        assert len(negatives) == 0

    def test_htf_conflict(self):
        negatives = generate_negative_factors(
            "SHORT", "LONG", "LONG", "LONG",
            True, True, True, 2, 3.5, True, "VALIDATED",
        )
        assert any("HTF" in n for n in negatives)

    def test_no_bos_no_choch(self):
        negatives = generate_negative_factors(
            "LONG", "LONG", "LONG", "LONG",
            False, False, True, 2, 3.5, True, "WAITING_FOR_CONFIRMATION",
        )
        assert any("BOS/CHoCH" in n for n in negatives)

    def test_idm_not_swept(self):
        negatives = generate_negative_factors(
            "LONG", "LONG", "LONG", "LONG",
            True, True, False, 2, 3.5, True, "WAITING_FOR_CONFIRMATION",
        )
        assert any("IDM not swept" in n for n in negatives)

    def test_no_ifc(self):
        negatives = generate_negative_factors(
            "LONG", "LONG", "LONG", "LONG",
            True, True, True, 0, 3.5, True, "WAITING_FOR_CONFIRMATION",
        )
        assert any("IFC" in n for n in negatives)

    def test_invalid_rr(self):
        negatives = generate_negative_factors(
            "LONG", "LONG", "LONG", "LONG",
            True, True, True, 2, 0.5, True, "VALIDATED",
        )
        assert any("risk/reward" in n for n in negatives)

    def test_no_entry(self):
        negatives = generate_negative_factors(
            "LONG", "LONG", "LONG", "LONG",
            True, True, True, 2, 3.5, False, "WAITING_FOR_CONFIRMATION",
        )
        assert any("entry" in n for n in negatives)


# ──────────────────────────────────────────────
# LTF Confirmation
# ──────────────────────────────────────────────

class TestDetermineLTFConfirmation:
    def test_choch_present(self):
        assert determine_ltf_confirmation(1, 0, 0, "LONG") == "LONG"

    def test_idm_and_sweep(self):
        assert determine_ltf_confirmation(0, 1, 1, "SHORT") == "SHORT"

    def test_no_confirmation(self):
        assert determine_ltf_confirmation(0, 0, 0, "LONG") == "NONE"

    def test_idm_only_no_sweep(self):
        assert determine_ltf_confirmation(0, 1, 0, "LONG") == "NONE"


# ──────────────────────────────────────────────
# No Fabrication
# ──────────────────────────────────────────────

class TestNoFabrication:
    def test_neutral_never_receives_entry(self):
        status = determine_recommendation_status("NO_SETUP", "NEUTRAL", False, 10)
        assert status != "VALIDATED"

    def test_watch_state_no_entry(self):
        status = determine_recommendation_status("NO_SETUP", "LONG", False, 30)
        assert status == "WATCH"

    def test_score_zero_for_neutral_insufficient(self):
        score = compute_recommendation_score(
            trade_status="INSUFFICIENT_DATA", direction="NEUTRAL", assessment_score=0,
            htf_bias="NEUTRAL", middle_bias="NEUTRAL", ltf_confirmation="NONE",
            has_bos=False, has_choch=False, idm_count=0, idm_swept=False,
            ifc_count=0, fvg_count=0, ob_count=0, liquidity_sweeps=0,
            entry_scheme_found=False, rr=None,
            last_analysis=datetime.utcnow(), timeframe="15m", has_entry=False,
        )
        assert score == 0

    def test_reasons_correspond_to_detected_facts(self):
        reasons = generate_reasons(
            "LONG", "NEUTRAL", "NEUTRAL", "NONE",
            False, False, 0, False, 0, "", "NO_SETUP", False,
        )
        assert "BOS detected" not in reasons
        assert "CHoCH confirmed" not in reasons
        assert "IDM liquidity swept" not in reasons
        assert "IFC confirmation present" not in reasons
