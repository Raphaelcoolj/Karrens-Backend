import pytest
from app.analysis.engine import (
    ema, sma, rsi, macd, atr, bollinger_bands,
    find_swing_points, detect_market_structure, find_key_levels,
    calculate_volatility_metrics, calculate_momentum_metrics,
    analyze_market,
)


def make_klines(prices):
    return [{"open": p, "high": p * 1.01, "low": p * 0.99, "close": p, "volume": 1000} for p in prices]


class TestEMA:
    def test_basic(self):
        data = [10, 11, 12, 13, 14]
        result = ema(data, 3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] is not None
        assert result[2] == pytest.approx(11.0, abs=0.01)

    def test_insufficient_data(self):
        result = ema([1, 2], 5)
        assert all(v is None for v in result)


class TestSMA:
    def test_basic(self):
        data = [1, 2, 3, 4, 5]
        result = sma(data, 3)
        assert result[2] == pytest.approx(2.0)

    def test_insufficient_data(self):
        result = sma([1, 2], 5)
        assert all(v is None for v in result)


class TestRSI:
    def test_basic(self):
        closes = [44 + i * 0.5 for i in range(20)]
        result = rsi(closes)
        assert len(result) == len(closes)
        assert result[-1] is not None

    def test_insufficient_data(self):
        result = rsi([1, 2, 3])
        assert all(v is None for v in result)


class TestMACD:
    def test_basic(self):
        closes = [100 + i * 0.5 for i in range(50)]
        result = macd(closes)
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result


class TestATR:
    def test_basic(self):
        highs = [101 + i for i in range(20)]
        lows = [99 + i for i in range(20)]
        closes = [100 + i for i in range(20)]
        result = atr(highs, lows, closes)
        assert len(result) == 20
        assert result[-1] is not None

    def test_insufficient_data(self):
        result = atr([101], [99], [100])
        assert result[0] is None


class TestBollingerBands:
    def test_basic(self):
        closes = [100 + i * 0.5 for i in range(30)]
        result = bollinger_bands(closes)
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        assert result["upper"][-1] > result["lower"][-1]


class TestSwingPoints:
    def test_finds_highs_and_lows(self):
        prices = [10, 11, 12, 13, 12, 11, 10, 11, 12, 13, 14, 13, 12]
        highs = [p * 1.01 for p in prices]
        lows = [p * 0.99 for p in prices]
        result = find_swing_points(highs, lows, lookback=2)
        assert len(result["swing_highs"]) >= 1
        assert len(result["swing_lows"]) >= 1


class TestMarketStructure:
    def test_bullish(self):
        swing_highs = [{"index": 0, "price": 100}, {"index": 5, "price": 110}, {"index": 10, "price": 120}]
        swing_lows = [{"index": 2, "price": 90}, {"index": 7, "price": 95}, {"index": 12, "price": 100}]
        result = detect_market_structure(swing_highs, swing_lows)
        assert result["structure"] == "bullish"

    def test_bearish(self):
        swing_highs = [{"index": 0, "price": 120}, {"index": 5, "price": 110}, {"index": 10, "price": 100}]
        swing_lows = [{"index": 2, "price": 100}, {"index": 7, "price": 90}, {"index": 12, "price": 80}]
        result = detect_market_structure(swing_highs, swing_lows)
        assert result["structure"] == "bearish"

    def test_insufficient_data(self):
        result = detect_market_structure([{"index": 0, "price": 100}], [])
        assert result["structure"] == "undetermined"


class TestKeyLevels:
    def test_support_and_resistance(self):
        swing_highs = [{"index": 0, "price": 110}, {"index": 5, "price": 120}]
        swing_lows = [{"index": 2, "price": 90}, {"index": 7, "price": 95}]
        closes = [100]
        result = find_key_levels(swing_highs, swing_lows, closes)
        assert len(result["support"]) >= 1
        assert len(result["resistance"]) >= 1
        assert all(s < 100 for s in result["support"])
        assert all(r > 100 for r in result["resistance"])


class TestAnalyzeMarket:
    def test_basic_analysis(self):
        prices = [100 + i * 0.5 for i in range(100)]
        klines = make_klines(prices)
        result = analyze_market(klines)
        assert "current_price" in result
        assert "market_structure" in result
        assert "momentum" in result

    def test_insufficient_data(self):
        klines = make_klines([100, 101, 102])
        result = analyze_market(klines)
        assert "error" in result


class TestPriceFormatting:
    def test_no_thousands_separator(self):
        prices = [103450.25, 4521.37, 2.847, 0.00001247]
        for p in prices:
            formatted = str(p)
            assert "," not in formatted
            assert "." in formatted or "e" in formatted
