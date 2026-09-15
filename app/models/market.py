from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class AssetClass(str, Enum):
    FOREX = "forex"
    METAL = "metal"
    CRYPTO = "crypto"
    INDEX = "index"
    OTHER = "other"


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class Quote(BaseModel):
    symbol: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    timestamp: Optional[datetime] = None


class Instrument(BaseModel):
    symbol: str
    display_name: str
    asset_class: AssetClass
    base_currency: str = ""
    quote_currency: str = ""
    description: str = ""


class MarketSnapshot(BaseModel):
    symbol: str
    asset_class: AssetClass
    timeframe: str
    timestamp: datetime
    candles: list[Candle] = []
    quote: Optional[Quote] = None
    data_provider: str = ""
    data_timestamp: Optional[datetime] = None


def classify_instrument(symbol: str) -> AssetClass:
    s = symbol.upper().replace("/", "").replace("-", "")
    metals = {"XAUUSD", "XAGUSD", "XAUEUR", "XAGEUR"}
    crypto = {"BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "DOGEUSD"}
    indices = {"US30", "US500", "US100", "NAS100", "SPX500", "DJ30", "DAX40", "FTSE100"}

    if s in metals:
        return AssetClass.METAL
    if s in crypto:
        return AssetClass.CRYPTO
    if s in indices:
        return AssetClass.INDEX
    if len(s) == 6:
        return AssetClass.FOREX
    return AssetClass.OTHER


def format_display_name(symbol: str) -> str:
    s = symbol.upper().replace("/", "").replace("-", "")
    if len(s) == 6:
        return f"{s[:3]}/{s[3:]}"
    return symbol.upper()


def to_twelve_data_symbol(display: str) -> str:
    return display.upper().replace("/", "").replace("-", "").replace(" ", "")


def from_twelve_data_symbol(twelve_sym: str) -> str:
    s = twelve_sym.upper()
    if len(s) == 6:
        return f"{s[:3]}/{s[3:]}"
    return s
