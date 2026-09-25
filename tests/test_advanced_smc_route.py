"""Route-level tests for POST /api/analysis/advanced-smc.

Covers the always-on contract:
  * 200 + explicit non-signal status on upstream failures (spec section 18)
  * graceful HTF/LTF degradation (never fake timeframe alignment)
  * the new `directional` block (direction/confidence/setup/risk/levels)
"""
import asyncio
import math
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.main import app
import app.api.advanced_smc as api_mod
from app.strategies.advanced_smc.models import Candle

client = TestClient(app)


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


HTF = _candles(120, base=90.0, trend=0.2)
MID = _candles(200, base=100.0, trend=0.12)
LTF = _candles(200, base=100.0, trend=0.10)

REQUEST = {"symbol": "EURUSD", "htf": "1D", "middle_tf": "15m", "ltf": "1m"}


def _fetch_ok(htf=HTF, mid=MID, ltf=LTF, htf_err=None, mid_err=None, ltf_err=None):
    async def fake(symbol, timeframe, limit=200):
        if timeframe in ("1D", "1W"):
            return htf, htf_err
        if timeframe == "1m":
            return ltf, ltf_err
        return mid, mid_err
    return fake


def _directional(body: dict) -> dict:
    assert "directional" in body
    return body["directional"]


class TestSuccessfulAnalysis:
    def test_returns_directional_block(self, monkeypatch):
        monkeypatch.setattr(api_mod, "_fetch_candles_safe", _fetch_ok())
        res = client.post("/api/analysis/advanced-smc", json=REQUEST)

        assert res.status_code == 200
        body = res.json()
        directional = _directional(body)

        assert directional["status"] == "OK"
        assert directional["direction"] in ("LONG", "SHORT")
        assert isinstance(directional["confidence"], int)
        assert 0 <= directional["confidence"] <= 100
        assert directional["confidence_label"]
        assert directional["setup_status"] in (
            "DEVELOPING", "WAITING_FOR_CONFIRMATION",
            "PARTIALLY_CONFIRMED", "VALIDATED", "INVALIDATED", "NONE",
        )
        assert directional["risk"] in ("LOW", "MODERATE", "HIGH", "VERY HIGH", "UNKNOWN")
        assert directional["reasons"]
        assert body["signal"] == directional["direction"]

    def test_is_deterministic(self, monkeypatch):
        monkeypatch.setattr(api_mod, "_fetch_candles_safe", _fetch_ok())
        first = client.post("/api/analysis/advanced-smc", json=REQUEST).json()["directional"]
        second = client.post("/api/analysis/advanced-smc", json=REQUEST).json()["directional"]

        for key in ("status", "direction", "confidence", "confidence_label", "setup_status", "risk", "reasons"):
            assert first[key] == second[key]

    def test_no_levels_without_validated_setup(self, monkeypatch):
        monkeypatch.setattr(api_mod, "_fetch_candles_safe", _fetch_ok())
        directional = client.post("/api/analysis/advanced-smc", json=REQUEST).json()["directional"]

        if directional["setup_status"] != "VALIDATED":
            assert directional["entry"] is None
            assert directional["sl"] is None
            assert directional["tp"] is None
            assert directional["rr"] is None

    def test_validated_setup_exposes_complete_levels(self, monkeypatch):
        monkeypatch.setattr(api_mod, "_fetch_candles_safe", _fetch_ok())
        directional = client.post("/api/analysis/advanced-smc", json=REQUEST).json()["directional"]

        if directional["setup_status"] == "VALIDATED":
            assert None not in (directional["entry"], directional["sl"], directional["tp"], directional["rr"])

    def test_diagnostics_reports_all_timeframes(self, monkeypatch):
        monkeypatch.setattr(api_mod, "_fetch_candles_safe", _fetch_ok())
        diagnostics = client.post("/api/analysis/advanced-smc", json=REQUEST).json()["diagnostics"]

        assert diagnostics["data_valid"] is True
        assert diagnostics["htf_degraded"] is False
        assert diagnostics["ltf_degraded"] is False
        assert diagnostics["middle_candle_count"] > 0


class TestUpstreamFailureMapping:
    @pytest.mark.parametrize("err_status,expected", [
        ("MARKET_DATA_UNAVAILABLE", "MARKET_DATA_UNAVAILABLE"),
        ("UPSTREAM_RATE_LIMITED", "UPSTREAM_RATE_LIMITED"),
        ("INVALID_SYMBOL", "INVALID_SYMBOL"),
    ])
    def test_middle_failure_returns_200_with_explicit_status(self, monkeypatch, err_status, expected):
        fake = _fetch_ok(mid=[], mid_err=err_status)
        monkeypatch.setattr(api_mod, "_fetch_candles_safe", fake)
        res = client.post("/api/analysis/advanced-smc", json=REQUEST)

        assert res.status_code == 200
        body = res.json()
        assert _directional(body)["status"] == expected
        assert body["signal"] == "NEUTRAL"
        assert body["trade_status"]["status"] == "INSUFFICIENT_DATA"
        assert body["trade_status"]["direction"] == "NEUTRAL"
        assert body["directional"]["confidence"] == 0
        assert body["directional"]["entry"] is None

    def test_invalid_timeframe_combo_is_400(self, monkeypatch):
        monkeypatch.setattr(api_mod, "_fetch_candles_safe", _fetch_ok())
        res = client.post(
            "/api/analysis/advanced-smc",
            json={"symbol": "EURUSD", "htf": "15m", "middle_tf": "1D", "ltf": "1m"},
        )
        assert res.status_code == 400


class TestGracefulDegradation:
    def test_htf_failure_is_neutralised_not_faked(self, monkeypatch):
        fake = _fetch_ok(htf=[], htf_err="MARKET_DATA_UNAVAILABLE")
        monkeypatch.setattr(api_mod, "_fetch_candles_safe", fake)
        body = client.post("/api/analysis/advanced-smc", json=REQUEST).json()

        assert body["diagnostics"]["htf_degraded"] is True
        assert body["diagnostics"]["htf_bias"] == "NEUTRAL"
        assert _directional(body)["direction"] in ("LONG", "SHORT")
        joined = " ".join(_directional(body)["reasons"]).lower()
        assert "htf" not in joined  # no HTF evidence may be claimed

    def test_ltf_failure_still_produces_a_direction(self, monkeypatch):
        fake = _fetch_ok(ltf=[], ltf_err="UPSTREAM_RATE_LIMITED")
        monkeypatch.setattr(api_mod, "_fetch_candles_safe", fake)
        body = client.post("/api/analysis/advanced-smc", json=REQUEST).json()

        assert body["diagnostics"]["ltf_degraded"] is True
        assert body["diagnostics"]["ltf_candle_count"] == 0
        assert _directional(body)["direction"] in ("LONG", "SHORT")

    def test_single_timeframe_is_enough_for_a_direction(self, monkeypatch):
        fake = _fetch_ok(htf=[], htf_err="X", ltf=[], ltf_err="Y")
        monkeypatch.setattr(api_mod, "_fetch_candles_safe", fake)
        body = client.post("/api/analysis/advanced-smc", json=REQUEST).json()

        assert body["directional"]["status"] == "OK"
        assert body["directional"]["direction"] in ("LONG", "SHORT")


class TestFetchErrorMapping:
    def test_rate_limit_maps_to_upstream_rate_limited(self, monkeypatch):
        request = httpx.Request("GET", "https://provider.test/klines")
        response = httpx.Response(429, request=request)
        error = httpx.HTTPStatusError("429", request=request, response=response)
        monkeypatch.setattr(api_mod, "_fetch_candles", AsyncMock(side_effect=error))

        candles, status = asyncio.run(api_mod._fetch_candles_safe("BTCUSD", "15m"))
        assert candles == []
        assert status == "UPSTREAM_RATE_LIMITED"

    def test_client_error_maps_to_invalid_symbol(self, monkeypatch):
        request = httpx.Request("GET", "https://provider.test/klines")
        response = httpx.Response(404, request=request)
        error = httpx.HTTPStatusError("404", request=request, response=response)
        monkeypatch.setattr(api_mod, "_fetch_candles", AsyncMock(side_effect=error))

        candles, status = asyncio.run(api_mod._fetch_candles_safe("NOPE", "15m"))
        assert status == "INVALID_SYMBOL"

    def test_timeout_maps_to_market_data_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            api_mod, "_fetch_candles",
            AsyncMock(side_effect=httpx.ConnectError("boom")),
        )
        candles, status = asyncio.run(api_mod._fetch_candles_safe("BTCUSD", "15m"))
        assert status == "MARKET_DATA_UNAVAILABLE"

    def test_empty_candle_payload_maps_to_market_data_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            api_mod, "_fetch_candles",
            AsyncMock(side_effect=ValueError("No candle data returned for BTCUSD")),
        )
        candles, status = asyncio.run(api_mod._fetch_candles_safe("BTCUSD", "15m"))
        assert status == "MARKET_DATA_UNAVAILABLE"

    def test_success_has_no_status(self, monkeypatch):
        monkeypatch.setattr(api_mod, "_fetch_candles", AsyncMock(return_value=HTF))
        candles, status = asyncio.run(api_mod._fetch_candles_safe("BTCUSD", "1D"))
        assert status is None
        assert candles == HTF
