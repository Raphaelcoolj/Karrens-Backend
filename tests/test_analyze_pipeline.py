"""Tests for the deterministic /api/analyze pipeline (run_analysis).

Contract:
  * the signal does NOT depend on the AI provider (narrative only)
  * trade levels only appear when the canonical setup is validated, and are
    always geometrically valid (never fabricated)
  * upstream data failures surface as an explicit non-signal status
"""
import asyncio
import json
import math
from datetime import datetime, timedelta

import httpx
import pytest

import app.services.analysis_pipeline as ap
from app.models.signal import Direction
from app.strategies.advanced_smc.models import Candle


def _candles(count: int = 200, base: float = 100.0, trend: float = 0.12) -> list[Candle]:
    out, prev = [], base
    for i in range(count):
        center = base + trend * i
        wave = math.sin(i / 4.0) * 2.0
        o = prev
        c = center + wave
        out.append(
            Candle(
                timestamp=datetime(2026, 1, 1) + timedelta(hours=i),
                open=o, high=max(o, c) + 0.6, low=min(o, c) - 0.6,
                close=c, volume=1000 + i,
            )
        )
        prev = c
    return out


class _Snapshot:
    def __init__(self, candles):
        self.candles = candles
        self.data_provider = "test-provider"
        self.data_timestamp = datetime(2026, 1, 1)
        self.quote = None


def _install(monkeypatch, candles=None, error=None, ai_payload=None):
    async def get_full(pair, timeframe, limit=500):
        if error is not None:
            raise error
        return _Snapshot(candles or [])

    async def generate(**kwargs):
        if ai_payload is None:
            return {"success": False, "error": "provider down", "provider": None}
        return {"success": True, "response": json.dumps(ai_payload), "provider": "test-ai"}

    monkeypatch.setattr(ap.market_data_service, "get_full_market_data", get_full)
    monkeypatch.setattr(ap.ai_service, "generate", generate)


def _run(pair="EURUSD", timeframe="1h"):
    return asyncio.run(ap.run_analysis(pair, timeframe))


def _price_range(candles):
    return min(c.low for c in candles), max(c.high for c in candles)


class TestDirectionDoesNotDependOnAI:
    def test_signal_is_produced_when_ai_is_down(self, monkeypatch):
        _install(monkeypatch, candles=_candles())
        analysis = _run()

        assert analysis.data_status == "OK"
        assert analysis.signal is not None
        assert analysis.signal.direction in (Direction.LONG, Direction.SHORT)
        assert 0 <= analysis.signal.confidence <= 100

    def test_ai_narrative_does_not_change_direction_or_levels(self, monkeypatch):
        _install(monkeypatch, candles=_candles())
        without_ai = _run()

        _install(
            monkeypatch,
            candles=_candles(),
            ai_payload={
                "direction": "SHORT",
                "confidence": 99,
                "entry": 999.0,
                "stop_loss": 1000.0,
                "take_profit": 1.0,
                "reasoning": "AI claims a short at 999.",
            },
        )
        with_ai = _run()

        assert with_ai.signal.direction == without_ai.signal.direction
        assert with_ai.signal.confidence == without_ai.signal.confidence
        assert with_ai.signal.entry == without_ai.signal.entry

    def test_ai_proposed_levels_are_never_used(self, monkeypatch):
        candles = _candles()
        _install(
            monkeypatch,
            candles=candles,
            ai_payload={
                "direction": "SHORT",
                "entry": 999.0,
                "stop_loss": 1000.0,
                "take_profit": 1.0,
                "reasoning": "Fabricated levels.",
            },
        )
        analysis = _run()
        low, high = _price_range(candles)

        if analysis.signal.entry is not None:
            assert low <= analysis.signal.entry <= high

    def test_ai_failure_still_returns_reasoning_from_evidence(self, monkeypatch):
        _install(monkeypatch, candles=_candles())
        analysis = _run()

        assert analysis.signal.reasoning
        assert analysis.signal.triggered_conditions
        assert analysis.signal.market_context in ("", None)


class TestLevelsAreNeverFabricated:
    def test_levels_only_when_setup_is_validated(self, monkeypatch):
        _install(monkeypatch, candles=_candles())
        analysis = _run()
        directional = analysis.directional

        if directional.get("setup_status") != "VALIDATED":
            assert analysis.signal.entry is None
            assert analysis.signal.stop_loss is None
            assert analysis.signal.take_profit is None
            assert analysis.signal.risk_reward is None

    def test_levels_are_geometrically_valid(self, monkeypatch):
        _install(monkeypatch, candles=_candles())
        analysis = _run()
        signal = analysis.signal

        if signal.entry is None:
            assert signal.stop_loss is None and signal.take_profit is None
            return

        assert signal.stop_loss is not None and signal.take_profit is not None
        assert signal.risk_reward is not None and signal.risk_reward > 0
        if signal.direction == Direction.LONG:
            assert signal.stop_loss < signal.entry < signal.take_profit
        else:
            assert signal.take_profit < signal.entry < signal.stop_loss


class TestExplicitDataFailures:
    @pytest.mark.parametrize("error,expected", [
        (ValueError("No candle data returned for EURUSD"), "MARKET_DATA_UNAVAILABLE"),
        (httpx.HTTPStatusError(
            "429",
            request=httpx.Request("GET", "https://provider.test"),
            response=httpx.Response(429, request=httpx.Request("GET", "https://provider.test")),
        ), "UPSTREAM_RATE_LIMITED"),
        (httpx.HTTPStatusError(
            "404",
            request=httpx.Request("GET", "https://provider.test"),
            response=httpx.Response(404, request=httpx.Request("GET", "https://provider.test")),
        ), "INVALID_SYMBOL"),
        (httpx.ConnectError("timeout"), "MARKET_DATA_UNAVAILABLE"),
    ])
    def test_failure_maps_to_explicit_status(self, monkeypatch, error, expected):
        _install(monkeypatch, error=error)
        analysis = _run(pair="NOSUCHPAIR")

        assert analysis.data_status == expected
        assert analysis.signal.direction == Direction.NO_SIGNAL
        assert analysis.signal.confidence == 0
        assert analysis.signal.entry is None
        assert analysis.signal.stop_loss is None
        assert analysis.signal.take_profit is None
        assert expected in analysis.signal.reasoning

    def test_empty_candle_payload_is_a_failure(self, monkeypatch):
        _install(monkeypatch, candles=[])
        analysis = _run()

        assert analysis.data_status == "MARKET_DATA_UNAVAILABLE"
        assert analysis.signal.direction == Direction.NO_SIGNAL


class TestDeterminismAndPayload:
    def test_same_candles_same_signal(self, monkeypatch):
        _install(monkeypatch, candles=_candles())
        first = _run()
        second = _run()

        assert first.signal.direction == second.signal.direction
        assert first.signal.confidence == second.signal.confidence
        assert first.directional.get("setup_status") == second.directional.get("setup_status")
        assert first.directional.get("risk") == second.directional.get("risk")
        assert first.signal.reasoning == second.signal.reasoning

    def test_directional_payload_is_complete(self, monkeypatch):
        _install(monkeypatch, candles=_candles())
        analysis = _run()

        assert set(analysis.directional) >= {
            "status", "direction", "confidence", "confidence_label",
            "setup_status", "risk", "reasons",
        }
        assert analysis.directional["confidence_label"]
        assert analysis.directional["risk"] in (
            "LOW", "MODERATE", "HIGH", "VERY HIGH", "UNKNOWN",
        )

    def test_signal_alignment_reflects_setup_status(self, monkeypatch):
        _install(monkeypatch, candles=_candles())
        analysis = _run()

        assert analysis.signal.strategy_alignment == analysis.directional.get("setup_status")
