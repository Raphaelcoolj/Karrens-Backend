import pytest
from app.services.analysis_pipeline import validate_signal


class TestValidateSignal:
    def test_valid_long(self):
        data = {
            "direction": "LONG",
            "confidence": 75,
            "entry": 103450.25,
            "stop_loss": 101200.50,
            "take_profit": 110800.75,
            "reasoning": "Test signal",
            "triggered_conditions": ["Bullish structure"],
            "invalidating_conditions": [],
        }
        result = validate_signal(data, 103450.0)
        assert result["valid"] is True
        assert result["direction"] == "LONG"
        assert result["entry"] == 103450.25
        assert result["stop_loss"] == 101200.50
        assert result["take_profit"] == 110800.75
        assert result["risk_reward"] == pytest.approx(3.27, abs=0.01)
        assert "," not in str(result["entry"])
        assert "," not in str(result["stop_loss"])
        assert "," not in str(result["take_profit"])

    def test_valid_short(self):
        data = {
            "direction": "SHORT",
            "confidence": 68,
            "entry": 4521.37,
            "stop_loss": 4600.00,
            "take_profit": 4300.00,
            "reasoning": "Bearish setup",
            "triggered_conditions": [],
            "invalidating_conditions": [],
        }
        result = validate_signal(data, 4520.0)
        assert result["valid"] is True
        assert result["direction"] == "SHORT"
        assert result["risk_reward"] == pytest.approx(2.81, abs=0.01)

    def test_no_signal(self):
        data = {"direction": "NO SIGNAL", "confidence": 0, "reasoning": "Weak evidence"}
        result = validate_signal(data, 100)
        assert result["valid"] is False
        assert result["direction"] == "NO SIGNAL"
        assert result["entry"] is None

    def test_invalid_long_sl_above_entry(self):
        data = {
            "direction": "LONG",
            "confidence": 70,
            "entry": 100,
            "stop_loss": 110,
            "take_profit": 120,
        }
        result = validate_signal(data, 100)
        assert result["valid"] is False
        assert result["direction"] == "NO SIGNAL"

    def test_invalid_short_sl_below_entry(self):
        data = {
            "direction": "SHORT",
            "confidence": 70,
            "entry": 100,
            "stop_loss": 90,
            "take_profit": 80,
        }
        result = validate_signal(data, 100)
        assert result["valid"] is False
        assert result["direction"] == "NO SIGNAL"

    def test_missing_levels(self):
        data = {"direction": "LONG", "confidence": 70, "entry": 100}
        result = validate_signal(data, 100)
        assert result["valid"] is False

    def test_no_thousands_separator_in_output(self):
        data = {
            "direction": "LONG",
            "confidence": 75,
            "entry": 103450.25,
            "stop_loss": 101200.50,
            "take_profit": 110800.75,
        }
        result = validate_signal(data, 103450.0)
        for field in ["entry", "stop_loss", "take_profit"]:
            val = str(result[field])
            assert "," not in val, f"{field} has thousands separator: {val}"

    def test_small_price_precision(self):
        data = {
            "direction": "LONG",
            "confidence": 70,
            "entry": 0.00001247,
            "stop_loss": 0.00001100,
            "take_profit": 0.00001600,
        }
        result = validate_signal(data, 0.000012)
        assert result["valid"] is True
        assert result["entry"] == 0.00001247

    def test_rejects_comma_formatted_string_prices(self):
        data = {
            "direction": "LONG",
            "confidence": 70,
            "entry": "1,351.42",
            "stop_loss": "1,340.00",
            "take_profit": "1,370.00",
        }
        result = validate_signal(data, 1351.0)
        assert result["valid"] is False
        assert result["direction"] == "NO SIGNAL"

    def test_forex_five_decimal_precision(self):
        data = {
            "direction": "LONG",
            "confidence": 80,
            "entry": 1.35142,
            "stop_loss": 1.34680,
            "take_profit": 1.36520,
        }
        result = validate_signal(data, 1.35100)
        assert result["valid"] is True
        assert result["entry"] == 1.35142
        assert result["stop_loss"] == 1.34680
        assert result["take_profit"] == 1.36520
        assert result["risk_reward"] == pytest.approx(2.98, abs=0.01)
