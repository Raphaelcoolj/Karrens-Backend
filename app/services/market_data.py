from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime
import httpx
import time
import logging

from app.core.config import get_settings
from app.models.market import (
    Candle,
    Quote,
    Instrument,
    MarketSnapshot,
    AssetClass,
    Timeframe,
    classify_instrument,
    format_display_name,
)

logger = logging.getLogger(__name__)

TIMEFRAME_MAP = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
    "1w": "1week",
}


class MarketDataProvider(ABC):
    @abstractmethod
    async def search_pairs(self, query: str) -> list[Instrument]:
        pass

    @abstractmethod
    async def get_klines(
        self, symbol: str, interval: str, limit: int = 200
    ) -> list[Candle]:
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Quote:
        pass

    @abstractmethod
    async def get_full_snapshot(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> MarketSnapshot:
        pass


class TwelveDataProvider(MarketDataProvider):
    BASE_URL = "https://api.twelvedata.com"
    _cache: dict = {}
    _cache_ttl = 60

    def __init__(self):
        settings = get_settings()
        self._api_key = settings.TWELVE_DATA_API_KEY
        if not self._api_key:
            logger.warning("TWELVE_DATA_API_KEY not configured")

    def _cached(self, key: str):
        entry = self._cache.get(key)
        if entry and time.time() - entry[1] < self._cache_ttl:
            return entry[0]
        return None

    def _set_cache(self, key: str, value):
        self._cache[key] = (value, time.time())

    def _to_td_symbol(self, display_symbol: str) -> str:
        s = display_symbol.upper().replace("-", "").replace(" ", "")
        if "/" not in s and len(s) == 6:
            return f"{s[:3]}/{s[3:]}"
        return s

    def _from_td_symbol(self, td_symbol: str) -> str:
        s = td_symbol.upper()
        if len(s) == 6:
            return f"{s[:3]}/{s[3:]}"
        return s

    def _convert_interval(self, interval: str) -> str:
        return TIMEFRAME_MAP.get(interval, interval)

    def _parse_td_datetime(self, dt_str: str) -> datetime:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(dt_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Unable to parse datetime: {dt_str}")

    async def search_pairs(self, query: str) -> list[Instrument]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.BASE_URL}/symbol_search",
                params={"symbol": query, "apikey": self._api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("data", []):
            symbol = item.get("symbol", "")
            instrument_type = item.get("instrument_type", "").lower()

            asset_class = AssetClass.OTHER
            if "forex" in instrument_type or "currency" in instrument_type:
                asset_class = AssetClass.FOREX
            elif "commodity" in instrument_type or "metal" in instrument_type:
                asset_class = AssetClass.METAL
            elif "crypto" in instrument_type:
                asset_class = AssetClass.CRYPTO
            elif "index" in instrument_type:
                asset_class = AssetClass.INDEX
            else:
                asset_class = classify_instrument(symbol)

            display = self._from_td_symbol(symbol)
            base = ""
            quote = ""
            if "/" in display:
                base, quote = display.split("/", 1)

            results.append(
                Instrument(
                    symbol=symbol,
                    display_name=display,
                    asset_class=asset_class,
                    base_currency=base,
                    quote_currency=quote,
                    description=item.get("instrument_name", ""),
                )
            )
        return results

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 200
    ) -> list[Candle]:
        cache_key = f"klines:{symbol}:{interval}:{limit}"
        cached = self._cached(cache_key)
        if cached is not None:
            return cached

        td_symbol = self._to_td_symbol(symbol)
        td_interval = self._convert_interval(interval)

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.BASE_URL}/time_series",
                params={
                    "symbol": td_symbol,
                    "interval": td_interval,
                    "outputsize": limit,
                    "apikey": self._api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        if "values" not in data:
            raise ValueError(f"No candle data returned for {symbol}")

        candles = []
        for v in data["values"]:
            candles.append(
                Candle(
                    timestamp=self._parse_td_datetime(v["datetime"]),
                    open=float(v["open"]),
                    high=float(v["high"]),
                    low=float(v["low"]),
                    close=float(v["close"]),
                    volume=float(v.get("volume", 0) or 0),
                )
            )
        result = list(reversed(candles))
        self._set_cache(cache_key, result)
        return result

    async def get_ticker(self, symbol: str) -> Quote:
        cache_key = f"ticker:{symbol}"
        cached = self._cached(cache_key)
        if cached is not None:
            return cached

        td_symbol = self._to_td_symbol(symbol)

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.BASE_URL}/quote",
                params={"symbol": td_symbol, "apikey": self._api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        bid = float(data.get("bid", 0) or 0)
        ask = float(data.get("ask", 0) or 0)
        close = float(data.get("close", 0) or 0)
        spread = ask - bid if bid and ask else None

        result = Quote(
            symbol=self._from_td_symbol(data.get("symbol", td_symbol)),
            bid=bid if bid else (close if close else None),
            ask=ask if ask else (close if close else None),
            spread=round(spread, 5) if spread else None,
            timestamp=self._parse_td_datetime(data.get("datetime", "")) if data.get("datetime") else None,
        )
        self._set_cache(cache_key, result)
        return result

    async def get_full_snapshot(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> MarketSnapshot:
        candles = await self.get_klines(symbol, timeframe, limit)
        quote = await self.get_ticker(symbol)

        return MarketSnapshot(
            symbol=symbol,
            asset_class=classify_instrument(symbol),
            timeframe=timeframe,
            timestamp=candles[-1].timestamp if candles else datetime.utcnow(),
            candles=candles,
            quote=quote,
            data_provider="twelve_data",
            data_timestamp=datetime.utcnow(),
        )


class BinanceProvider(MarketDataProvider):
    BASE_URL = "https://api.binance.com/api/v3"

    async def search_pairs(self, query: str) -> list[Instrument]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.BASE_URL}/exchangeInfo")
            resp.raise_for_status()
            data = resp.json()
            results = []
            q = query.upper()
            for s in data.get("symbols", []):
                if q in s["symbol"] and s["status"] == "TRADING":
                    base = s["baseAsset"]
                    quote = s["quoteAsset"]
                    display = f"{base}/{quote}"
                    results.append(
                        Instrument(
                            symbol=s["symbol"],
                            display_name=display,
                            asset_class=classify_instrument(s["symbol"]),
                            base_currency=base,
                            quote_currency=quote,
                        )
                    )
                    if len(results) >= 20:
                        break
            return results

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 200
    ) -> list[Candle]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.BASE_URL}/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
            )
            resp.raise_for_status()
            raw = resp.json()
            return [
                Candle(
                    timestamp=datetime.fromtimestamp(k[0] / 1000),
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                )
                for k in raw
            ]

    async def get_ticker(self, symbol: str) -> Quote:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.BASE_URL}/ticker/24hr", params={"symbol": symbol}
            )
            resp.raise_for_status()
            t = resp.json()
            last_price = float(t["lastPrice"])
            return Quote(
                symbol=symbol,
                bid=last_price,
                ask=last_price,
                spread=0.0,
                timestamp=datetime.utcnow(),
            )

    async def get_full_snapshot(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> MarketSnapshot:
        candles = await self.get_klines(symbol, timeframe, limit)
        quote = await self.get_ticker(symbol)

        return MarketSnapshot(
            symbol=symbol,
            asset_class=classify_instrument(symbol),
            timeframe=timeframe,
            timestamp=candles[-1].timestamp if candles else datetime.utcnow(),
            candles=candles,
            quote=quote,
            data_provider="binance",
            data_timestamp=datetime.utcnow(),
        )


def _create_default_provider() -> MarketDataProvider:
    settings = get_settings()
    if settings.TWELVE_DATA_API_KEY:
        return TwelveDataProvider()
    return BinanceProvider()


class MarketDataService:
    def __init__(self, provider: Optional[MarketDataProvider] = None):
        self._provider = provider or _create_default_provider()

    @property
    def provider(self) -> MarketDataProvider:
        return self._provider

    @provider.setter
    def provider(self, provider: MarketDataProvider):
        self._provider = provider

    async def search_pairs(self, query: str) -> list[Instrument]:
        return await self._provider.search_pairs(query)

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 200
    ) -> list[Candle]:
        return await self._provider.get_klines(symbol, interval, limit)

    async def get_ticker(self, symbol: str) -> Quote:
        return await self._provider.get_ticker(symbol)

    async def get_full_market_data(
        self, symbol: str, interval: str, limit: int = 200
    ) -> MarketSnapshot:
        return await self._provider.get_full_snapshot(symbol, interval, limit)
