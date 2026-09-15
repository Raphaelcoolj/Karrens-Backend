import pytest
from app.services.ai_provider import parse_ai_signal_response


class TestParseAISignalResponse:
    def test_valid_json(self):
        response = '''{"direction": "LONG", "confidence": 75, "entry": 103450.25, "stop_loss": 101200.50, "take_profit": 110800.75, "risk_reward": 3.43, "reasoning": "Bullish setup", "triggered_conditions": [], "invalidating_conditions": [], "market_context": "Uptrend"}'''
        result = parse_ai_signal_response(response)
        assert result["direction"] == "LONG"
        assert result["confidence"] == 75
        assert result["entry"] == 103450.25

    def test_json_in_codeblock(self):
        response = '''```json
{"direction": "SHORT", "confidence": 60, "entry": 4521.37, "stop_loss": 4600.00, "take_profit": 4300.00, "risk_reward": 2.81, "reasoning": "Bearish", "triggered_conditions": [], "invalidating_conditions": [], "market_context": "Downtrend"}
```'''
        result = parse_ai_signal_response(response)
        assert result["direction"] == "SHORT"

    def test_no_thousands_separator(self):
        response = '{"direction": "LONG", "entry": 103450.25}'
        result = parse_ai_signal_response(response)
        assert result["entry"] == 103450.25
        assert "," not in str(result["entry"])

    def test_invalid_json(self):
        response = "This is not JSON at all."
        result = parse_ai_signal_response(response)
        assert result.get("parse_error") is True

    def test_no_signal_direction(self):
        response = '{"direction": "NO SIGNAL", "confidence": 0, "reasoning": "Insufficient data"}'
        result = parse_ai_signal_response(response)
        assert result["direction"] == "NO SIGNAL"
        assert result["confidence"] == 0

    def test_small_price_preserved(self):
        response = '{"direction": "LONG", "entry": 0.00001247, "stop_loss": 0.00001100, "take_profit": 0.00001600}'
        result = parse_ai_signal_response(response)
        assert result["entry"] == 0.00001247
        assert result["stop_loss"] == 0.000011
        assert result["take_profit"] == 0.000016
