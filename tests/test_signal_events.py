"""Tests for the directional notification event policy (notification_service).

Pure-policy tests: identical snapshots always yield the same single event,
data failures never notify, and priority is fixed.
"""
import pytest
from dataclasses import replace

from app.core.thresholds import SignalThresholds
from app.services.notification_service import (
    EVENT_CONFIDENCE_INCREASE,
    EVENT_DIRECTION_CHANGE,
    EVENT_NEW_HIGH_CONFIDENCE,
    EVENT_VALIDATED_SETUP,
    build_event_notification_body,
    compute_event_fingerprint,
    evaluate_signal_events,
    signal_snapshot,
)


def _current(**overrides) -> dict:
    base = {
        "symbol": "BTCUSD",
        "timeframe": "15m",
        "status": "OK",
        "direction": "LONG",
        "confidence": 74,
        "confidence_label": "HIGH",
        "setup_status": "DEVELOPING",
        "risk": "MODERATE",
        "entry": None,
        "sl": None,
        "tp": None,
        "rr": None,
        "fingerprint": "",
    }
    base.update(overrides)
    return base


def _validated(**overrides) -> dict:
    base = _current(
        type=EVENT_VALIDATED_SETUP,
        setup_status="VALIDATED",
        confidence=82,
        entry=100.0,
        sl=99.0,
        tp=104.0,
        rr=4.0,
        fingerprint="fp-levels-1",
        risk="LOW",
        confidence_label="VERY HIGH",
    )
    base.update(overrides)
    return base


class TestEventPriority:
    def test_first_sight_of_high_confidence_notifies(self):
        event = evaluate_signal_events(_current(confidence=85), None)
        assert event is not None
        assert event["type"] == EVENT_NEW_HIGH_CONFIDENCE

    def test_no_event_below_confidence_threshold(self):
        assert evaluate_signal_events(_current(confidence=55), None) is None

    def test_direction_change_beats_confidence_increase(self):
        previous = _current(direction="SHORT", confidence=40)
        current = _current(direction="LONG", confidence=90)
        event = evaluate_signal_events(current, previous)
        assert event["type"] == EVENT_DIRECTION_CHANGE
        assert event["from"] == "SHORT"
        assert event["to"] == "LONG"

    def test_validated_setup_beats_confidence_increase(self):
        previous = _current(confidence=40)
        current = _validated(confidence=95)
        event = evaluate_signal_events(current, previous)
        assert event["type"] == EVENT_VALIDATED_SETUP

    def test_confidence_increase_beats_high_confidence_threshold(self):
        previous = _current(confidence=55)
        current = _current(confidence=75)
        event = evaluate_signal_events(current, previous)
        assert event["type"] == EVENT_CONFIDENCE_INCREASE
        assert event["delta"] == 20

    def test_only_one_event_is_returned(self):
        previous = _current(direction="SHORT", confidence=30)
        current = _validated(direction="LONG", confidence=95)
        events = evaluate_signal_events(current, previous)
        assert events["type"] == EVENT_DIRECTION_CHANGE


class TestEventRules:
    def test_no_event_without_direction_change(self):
        previous = _current(confidence=50)
        current = _current(confidence=52)
        assert evaluate_signal_events(current, previous) is None

    def test_small_confidence_change_is_silent(self):
        previous = _current(confidence=70)
        current = _current(confidence=78)
        assert evaluate_signal_events(current, previous) is None

    def test_confidence_drop_does_not_notify(self):
        previous = _current(confidence=88)
        current = _current(confidence=60)
        assert evaluate_signal_events(current, previous) is None

    def test_validated_setup_only_notifies_with_levels(self):
        current = _validated(entry=None)
        event = evaluate_signal_events(current, None)
        # Without levels there is nothing validated to push (any event that
        # does fire must not be a VALIDATED_SETUP).
        assert event is None or event["type"] != EVENT_VALIDATED_SETUP

    def test_same_validated_levels_do_not_notify_twice(self):
        previous = _validated()
        current = _validated()
        assert evaluate_signal_events(current, previous) is None

    def test_new_validated_levels_notify(self):
        previous = _validated()
        current = _validated(entry=101.0, sl=100.0, tp=105.0, fingerprint="fp-levels-2")
        event = evaluate_signal_events(current, previous)
        assert event["type"] == EVENT_VALIDATED_SETUP
        assert event["entry"] == 101.0

    def test_recovered_validated_setup_after_waiting_notifies(self):
        previous = _current(confidence=40, setup_status="WAITING_FOR_CONFIRMATION")
        event = evaluate_signal_events(_validated(), previous)
        assert event["type"] == EVENT_VALIDATED_SETUP

    @pytest.mark.parametrize("status", [
        "INSUFFICIENT_DATA", "MARKET_DATA_UNAVAILABLE",
        "UPSTREAM_RATE_LIMITED", "INVALID_SYMBOL", "ANALYSIS_ERROR",
    ])
    def test_data_failures_never_notify(self, status):
        current = _current(status=status, direction="NEUTRAL", confidence=90)
        assert evaluate_signal_events(current, None) is None

    def test_neutral_direction_never_notifies(self):
        current = _current(direction="NEUTRAL", confidence=95, status="OK")
        assert evaluate_signal_events(current, None) is None

    def test_previous_data_failure_is_treated_as_no_previous_state(self):
        previous = _current(status="MARKET_DATA_UNAVAILABLE", direction="NEUTRAL", confidence=10)
        event = evaluate_signal_events(_current(confidence=85), previous)
        assert event["type"] == EVENT_NEW_HIGH_CONFIDENCE


class TestThresholdPolicy:
    def test_high_confidence_trigger_is_configurable(self):
        th = replace(SignalThresholds(), notify_min_confidence=55)
        assert evaluate_signal_events(_current(confidence=60), None, th) is not None
        assert evaluate_signal_events(_current(confidence=50), None, th) is None

    def test_confidence_delta_is_configurable(self):
        th = replace(SignalThresholds(), notify_min_confidence_delta=25)
        previous = _current(confidence=70)
        current = _current(confidence=80)
        # +10 is a real move but below the configured delta, and the pair was
        # already above the high-confidence threshold.
        assert evaluate_signal_events(current, previous, th) is None

    def test_events_can_be_disabled_individually(self):
        # Same direction, tiny confidence move: only the direction trigger can fire.
        previous = _current(direction="SHORT", confidence=74)
        current = _current(direction="LONG", confidence=76)

        disabled = replace(SignalThresholds(), notify_on_direction_change=False)
        assert evaluate_signal_events(current, previous, disabled) is None

        disabled = replace(SignalThresholds(), notify_on_high_confidence=False)
        assert evaluate_signal_events(current, None, disabled) is None

        disabled = replace(SignalThresholds(), notify_on_validated_setup=False)
        assert evaluate_signal_events(_validated(confidence=65), None, disabled) is None


class TestEventFingerprints:
    def test_direction_pair_fingerprint_differs_by_pair(self):
        e1 = {"type": EVENT_DIRECTION_CHANGE, "from": "SHORT", "to": "LONG"}
        e2 = {"type": EVENT_DIRECTION_CHANGE, "from": "LONG", "to": "SHORT"}
        assert compute_event_fingerprint("BTCUSD", "15m", e1) != compute_event_fingerprint("BTCUSD", "15m", e2)

    def test_confidence_events_bucket_by_tens(self):
        e1 = {"type": EVENT_NEW_HIGH_CONFIDENCE, "confidence": 74}
        e2 = {"type": EVENT_NEW_HIGH_CONFIDENCE, "confidence": 76}
        e3 = {"type": EVENT_NEW_HIGH_CONFIDENCE, "confidence": 81}
        assert compute_event_fingerprint("BTCUSD", "15m", e1) == compute_event_fingerprint("BTCUSD", "15m", e2)
        assert compute_event_fingerprint("BTCUSD", "15m", e1) != compute_event_fingerprint("BTCUSD", "15m", e3)

    def test_validated_fingerprint_follows_levels(self):
        e1 = _validated()
        e2 = _validated(entry=101.0)
        assert compute_event_fingerprint("BTCUSD", "15m", e1) != compute_event_fingerprint("BTCUSD", "15m", e2)

    def test_same_event_same_fingerprint(self):
        e = _validated()
        assert compute_event_fingerprint("BTCUSD", "15m", e) == compute_event_fingerprint("BTCUSD", "15m", e)


class TestSnapshotAndBody:
    def test_snapshot_carries_signal_hierarchy(self):
        signal = type("Sig", (), {
            "status": "OK", "direction": "LONG", "confidence": 74,
            "confidence_label": "HIGH", "setup_status": "VALIDATED",
            "risk": "MODERATE", "entry": 100.0, "sl": 99.0, "tp": 104.0, "rr": 4.0,
        })()
        snap = signal_snapshot("btcusd", "15m", signal)
        assert snap["symbol"] == "BTCUSD"
        assert snap["direction"] == "LONG"
        assert snap["confidence"] == 74
        assert snap["setup_status"] == "VALIDATED"
        assert snap["fingerprint"]  # levels fingerprint computed

    def test_snapshot_without_levels_has_no_fingerprint(self):
        signal = type("Sig", (), {
            "status": "OK", "direction": "SHORT", "confidence": 61,
            "confidence_label": "MODERATE", "setup_status": "DEVELOPING",
            "risk": "HIGH", "entry": None, "sl": None, "tp": None, "rr": None,
        })()
        snap = signal_snapshot("ETHUSD", "1h", signal)
        assert snap["fingerprint"] == ""

    def test_body_shows_direction_confidence_setup_and_risk(self):
        body = build_event_notification_body(_current())
        assert "LONG" in body
        assert "74/100" in body
        assert "Setup: DEVELOPING" in body
        assert "Risk: MODERATE" in body

    def test_validated_body_includes_levels(self):
        body = build_event_notification_body(_validated())
        assert "Entry: 100.0" in body
        assert "SL: 99.0" in body
        assert "TP: 104.0" in body

    def test_direction_change_body_names_both_directions(self):
        event = {
            "type": EVENT_DIRECTION_CHANGE, "symbol": "EURUSD", "timeframe": "15m",
            "from": "LONG", "to": "SHORT", "direction": "SHORT",
            "confidence": 66, "confidence_label": "MODERATE",
            "setup_status": "DEVELOPING", "risk": "HIGH",
        }
        body = build_event_notification_body(event)
        assert "LONG → SHORT" in body or "LONG -> SHORT" in body
