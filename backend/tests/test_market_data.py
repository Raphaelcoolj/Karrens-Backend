import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import httpx

from app.services.market_data import TwelveDataProvider, MarketDataService, TIMEFRAME_MAP
from app.models.market import (
    Instrument,
    Candle,
    Quote,
    MarketSnapshot,
    AssetClass,
    classify_instrument,
    format_display_name,
    to_twelve_data_symbol,
    from_twelve_data_symbol,
)


class TestMarketModels:
    def test_classify_instrument_forex(self):
        assert classify_instrument("EURUSD") == AssetClass.FOREX
        assert classify_instrument("EUR/USD") == AssetClass.FOREX
        assert classify_instrument("GBPUSD") == AssetClass.FOREX

    def test_classify_instrument_metal(self):
        assert classify_instrument("XAUUSD") == AssetClass.METAL
        assert classify_instrument("XAGUSD") == AssetClass.METAL

    def test_classify_instrument_crypto(self):
        assert classify_instrument("BTCUSD") == AssetClass.CRYPTO
        assert classify_instrument("ETHUSD") == AssetClass.CRYPTO

    def test_format_display_name(self):
        assert format_display_name("EURUSD") == "EUR/USD"
        assert format_display_name("EUR/USD") == "EUR/USD"
        assert format_display_name("XAUUSD") == "XAU/USD"

    def test_to_twelve_data_symbol(self):
        assert to_twelve_data_symbol("EUR/USD") == "EURUSD"
        assert to_twelve_data_symbol("EUR-USD") == "EURUSD"
        assert to_twelve_data_symbol("EUR USD") == "EURUSD"

    def test_from_twelve_data_symbol(self):
        assert from_twelve_data_symbol("EURUSD") == "EUR/USD"
        assert from_twelve_data_symbol("XAUUSD") == "XAU/USD"

    def test_candle_model(self):
        candle = Candle(
            timestamp=datetime(2024, 1, 1),
            open=1.1,
            high=1.2,
            low=1.0,
            close=1.15,
            volume=1000,
        )
        assert candle.open == 1.1
        assert candle.volume == 1000

    def test_quote_model(self):
        quote = Quote(
            symbol="EUR/USD",
            bid=1.1,
            ask=1.1001,
            spread=0.0001,
        )
        assert quote.spread == 0.0001

    def test_instrument_model(self):
        inst = Instrument(
            symbol="EURUSD",
            display_name="EUR/USD",
            asset_class=AssetClass.FOREX,
            base_currency="EUR",
            quote_currency="USD",
        )
        assert inst.asset_class == AssetClass.FOREX


class TestTwelveDataProvider:
    def setup_method(self):
        with patch("app.services.market_data.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(TWELVE_DATA_API_KEY="test_api_key")
            self.provider = TwelveDataProvider()

    def test_convert_interval(self):
        assert self.provider._convert_interval("1m") == "1min"
        assert self.provider._convert_interval("4h") == "4h"
        assert self.provider._convert_interval("1d") == "1day"
        assert self.provider._convert_interval("1w") == "1week"

    def test_to_td_symbol(self):
        assert self.provider._to_td_symbol("EUR/USD") == "EUR/USD"
        assert self.provider._to_td_symbol("EUR-USD") == "EUR/USD"
        assert self.provider._to_td_symbol("EURUSD") == "EUR/USD"

    def test_from_td_symbol(self):
        assert self.provider._from_td_symbol("EURUSD") == "EUR/USD"
        assert self.provider._from_td_symbol("XAUUSD") == "XAU/USD"

    def test_parse_td_datetime(self):
        dt = self.provider._parse_td_datetime("2024-01-15 10:30:00")
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.hour == 10

    def test_parse_td_datetime_date_only(self):
        dt = self.provider._parse_td_datetime("2024-01-15")
        assert dt.year == 2024

    def test_parse_td_datetime_invalid(self):
        with pytest.raises(ValueError):
            self.provider._parse_td_datetime("invalid-date")


class TestTwelveDataProviderSearch:
    def setup_method(self):
        with patch("app.services.market_data.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(TWELVE_DATA_API_KEY="test_api_key")
            self.provider = TwelveDataProvider()

    def test_search_pairs_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "symbol": "EURUSD",
                    "instrument_name": "EUR/USD",
                    "exchange": "Forex",
                    "instrument_type": "Currency",
                    "currency": "USD",
                },
                {
                    "symbol": "EURGBP",
                    "instrument_name": "EUR/GBP",
                    "exchange": "Forex",
                    "instrument_type": "Currency",
                    "currency": "GBP",
                },
            ],
            "status": "ok",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)

            import asyncio
            results = asyncio.run(self.provider.search_pairs("EUR"))

            assert len(results) == 2
            assert results[0].symbol == "EURUSD"
            assert results[0].display_name == "EUR/USD"
            assert results[0].asset_class == AssetClass.FOREX

    def test_search_pairs_api_error(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
                "429", request=MagicMock(), response=MagicMock(status_code=429)
            ))

            import asyncio
            with pytest.raises(httpx.HTTPStatusError):
                asyncio.run(self.provider.search_pairs("EUR"))


class TestTwelveDataProviderCandles:
    def setup_method(self):
        with patch("app.services.market_data.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(TWELVE_DATA_API_KEY="test_api_key")
            self.provider = TwelveDataProvider()

    def test_get_klines_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "values": [
                {"datetime": "2024-01-15 11:00:00", "open": "1.105", "high": "1.115", "low": "1.1", "close": "1.11", "volume": "1200"},
                {"datetime": "2024-01-15 10:00:00", "open": "1.1", "high": "1.11", "low": "1.09", "close": "1.105", "volume": "1000"},
            ],
            "status": "ok",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)

            import asyncio
            candles = asyncio.run(self.provider.get_klines("EUR/USD", "1h", 2))

            assert len(candles) == 2
            assert candles[0].open == 1.1
            assert candles[1].close == 1.11

    def test_get_klines_no_values(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)

            import asyncio
            with pytest.raises(ValueError, match="No candle data"):
                asyncio.run(self.provider.get_klines("INVALID", "1h", 200))


class TestTwelveDataProviderQuote:
    def setup_method(self):
        with patch("app.services.market_data.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(TWELVE_DATA_API_KEY="test_api_key")
            self.provider = TwelveDataProvider()

    def test_get_ticker_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "symbol": "EUR/USD",
            "bid": "1.1",
            "ask": "1.1001",
            "datetime": "2024-01-15 10:00:00",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)

            import asyncio
            quote = asyncio.run(self.provider.get_ticker("EUR/USD"))

            assert quote.symbol == "EUR/USD"
            assert quote.bid == 1.1
            assert quote.ask == 1.1001
            assert quote.spread == pytest.approx(0.0001, abs=0.00001)


class TestTwelveDataProviderSnapshot:
    def setup_method(self):
        with patch("app.services.market_data.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(TWELVE_DATA_API_KEY="test_api_key")
            self.provider = TwelveDataProvider()

    def test_get_full_snapshot(self):
        mock_klines_response = MagicMock()
        mock_klines_response.status_code = 200
        mock_klines_response.json.return_value = {
            "values": [
                {"datetime": "2024-01-15 10:00:00", "open": "1.1", "high": "1.11", "low": "1.09", "close": "1.105", "volume": "1000"},
            ],
            "status": "ok",
        }
        mock_klines_response.raise_for_status = MagicMock()

        mock_quote_response = MagicMock()
        mock_quote_response.status_code = 200
        mock_quote_response.json.return_value = {
            "symbol": "EUR/USD",
            "bid": "1.1",
            "ask": "1.1001",
            "datetime": "2024-01-15 10:00:00",
        }
        mock_quote_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=[mock_klines_response, mock_quote_response])

            import asyncio
            snapshot = asyncio.run(self.provider.get_full_snapshot("EUR/USD", "1h", 1))

            assert snapshot.symbol == "EUR/USD"
            assert snapshot.asset_class == AssetClass.FOREX
            assert snapshot.data_provider == "twelve_data"
            assert len(snapshot.candles) == 1
            assert snapshot.quote is not None


class TestMarketDataService:
    def test_default_provider_with_api_key(self):
        with patch("app.services.market_data.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(TWELVE_DATA_API_KEY="test_key")
            service = MarketDataService()
            assert isinstance(service.provider, TwelveDataProvider)

    def test_default_provider_without_api_key(self):
        with patch("app.services.market_data.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(TWELVE_DATA_API_KEY="")
            from app.services.market_data import BinanceProvider
            service = MarketDataService()
            assert isinstance(service.provider, BinanceProvider)

    def test_custom_provider(self):
        with patch("app.services.market_data.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(TWELVE_DATA_API_KEY="test_key")
            custom = TwelveDataProvider()
            service = MarketDataService(provider=custom)
            assert service.provider is custom


class TestTimeframeMapping:
    def test_all_timeframes_mapped(self):
        for tf in ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]:
            assert tf in TIMEFRAME_MAP

    def test_timeframe_values(self):
        assert TIMEFRAME_MAP["1m"] == "1min"
        assert TIMEFRAME_MAP["5m"] == "5min"
        assert TIMEFRAME_MAP["15m"] == "15min"
        assert TIMEFRAME_MAP["30m"] == "30min"
        assert TIMEFRAME_MAP["1h"] == "1h"
        assert TIMEFRAME_MAP["4h"] == "4h"
        assert TIMEFRAME_MAP["1d"] == "1day"
        assert TIMEFRAME_MAP["1w"] == "1week"


class TestTwelveDataProviderEdgeCases:
    def setup_method(self):
        with patch("app.services.market_data.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(TWELVE_DATA_API_KEY="test_api_key")
            self.provider = TwelveDataProvider()

    def test_search_empty_results(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [], "status": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)

            import asyncio
            results = asyncio.run(self.provider.search_pairs("ZZZZZZ"))
            assert results == []

    def test_search_malformed_response_no_data_key(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)

            import asyncio
            results = asyncio.run(self.provider.search_pairs("EUR"))
            assert results == []

    def test_search_missing_instrument_type(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"symbol": "EURUSD", "instrument_name": "EUR/USD"},
            ],
            "status": "ok",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)

            import asyncio
            results = asyncio.run(self.provider.search_pairs("EUR"))
            assert len(results) == 1
            assert results[0].asset_class == AssetClass.FOREX

    def test_get_klines_malformed_values(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "values": [
                {"datetime": "2024-01-15 10:00:00", "open": "1.1", "high": "1.11", "low": "1.09", "close": "1.105", "volume": "1000"},
            ],
            "status": "ok",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)

            import asyncio
            candles = asyncio.run(self.provider.get_klines("EUR/USD", "1h", 1))
            assert len(candles) == 1
            assert candles[0].open == 1.1
            assert isinstance(candles[0].open, float)

    def test_get_ticker_zero_bid_ask(self):
        self.provider._cache.clear()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "symbol": "EUR/USD",
            "bid": "0",
            "ask": "0",
            "datetime": "2024-01-15 10:00:00",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)

            import asyncio
            quote = asyncio.run(self.provider.get_ticker("EUR/USD"))
            assert quote.bid is None
            assert quote.ask is None
            assert quote.spread is None

    def test_get_klines_api_error(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
                "429", request=MagicMock(), response=MagicMock(status_code=429)
            ))

            import asyncio
            with pytest.raises(httpx.HTTPStatusError):
                asyncio.run(self.provider.get_klines("EUR/USD", "1h", 200))

    def test_get_ticker_api_error(self):
        self.provider._cache.clear()
        with patch("app.services.market_data.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            ))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            import asyncio
            with pytest.raises(httpx.HTTPStatusError):
                asyncio.run(self.provider.get_ticker("GBPUSD"))


class TestInstrumentClassification:
    def test_forex六字符默认分类(self):
        assert classify_instrument("GBPUSD") == AssetClass.FOREX

    def test_non标准符号(self):
        assert classify_instrument("US30") == AssetClass.INDEX
        assert classify_instrument("UNKNOWN") == AssetClass.OTHER

    def test_from_twelve_data_symbol_non_six_char(self):
        result = from_twelve_data_symbol("US30")
        assert result == "US30"

    def test_format_display_name_non_six_char(self):
        result = format_display_name("US30")
        assert result == "US30"
