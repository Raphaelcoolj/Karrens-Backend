# Karren — Market Data Architecture Specification

## Overview

Karren is a **private FX-first trading intelligence system** with Twelve Data as the initial market-data provider and a clean provider abstraction for future expansion.

---

## 1. Primary Market: Forex

Forex is the **primary asset class for Karren V1**.

The system must be designed primarily around FX analysis rather than crypto.

### Supported Instruments

**Forex Majors:**
```
EUR/USD
GBP/USD
USD/JPY
USD/CHF
AUD/USD
USD/CAD
NZD/USD
```

**Forex Crosses:**
```
EUR/GBP
EUR/JPY
GBP/JPY
AUD/JPY
```

**Metals (where supported by provider):**
```
XAU/USD
XAG/USD
```

Crypto support can be added later. Do not let crypto-specific assumptions leak into the core market-analysis architecture.

---

## 2. Market Data Provider — Twelve Data

Use **Twelve Data as the initial primary market-data provider**.

### Capabilities

- Forex pair search/discovery
- Current/latest prices
- OHLC/candlestick data
- Historical market data
- Intraday data
- Multiple timeframes
- Volume where available
- Other relevant market metadata

### Security

The Twelve Data API key must be stored server-side in environment variables.

**Never expose the API key to the frontend.**

### Architecture Flow

```
Frontend
   ↓
Karren FastAPI
   ↓
Market Data Service
   ↓
Twelve Data
```

The frontend must NOT call Twelve Data directly.

---

## 3. Market Data Abstraction

Do NOT tightly couple the analysis engine directly to Twelve Data.

Create a market-data interface/service abstraction.

### Provider Interface

```python
class MarketDataProvider(ABC):
    async def search_pairs(self, query: str) -> list[Instrument]
    async def get_quote(self, symbol: str) -> Quote
    async def get_candles(self, symbol: str, timeframe: Timeframe, limit: int) -> list[Candle]
    async def get_historical_data(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime) -> list[Candle]
```

### Implementation

```
TwelveDataProvider  (implements MarketDataProvider)
```

The purpose is to allow another provider to be added later without rewriting Karren's analysis engine.

**Do not build additional providers now.**

---

## 4. Pair Search

Karren must allow the user to search for instruments.

### User Flow

```
Search market...

GBP/USD
EUR/USD
USD/JPY
XAU/USD
```

1. User searches for an instrument
2. User selects an instrument
3. User selects a timeframe
4. User clicks "Analyze"

### Requirements

- The UI should use human-readable symbols where possible
- The backend maps them to the format required by Twelve Data
- Do not make users manually enter provider-specific symbols unless necessary

---

## 5. Timeframes

Support the timeframes that Twelve Data can reliably provide and that are useful for the analysis engine.

### Required Timeframes

```
1m
5m
15m
30m
1H
4H
1D
1W
```

### Constraints

- Do not assume every timeframe is available for every provider response
- Validate returned data before analysis
- Handle missing timeframes gracefully

---

## 6. Forex-Specific Considerations

Do not treat forex exactly like a centralized exchange market.

Forex is decentralized and different feeds/brokers can have slightly different prices.

### Required Metadata

Karren should preserve with every market snapshot:

```
data_provider
data_timestamp
instrument
timeframe
```

### UI Requirements

- Where appropriate, display the data timestamp in the UI
- Do not falsely imply that Karren has access to a single universal FX price

---

## 7. Market Data Pipeline

The intended pipeline is:

```
User
 ↓
Search Pair
 ↓
Select Pair + Timeframe
 ↓
FastAPI
 ↓
Market Data Service
 ↓
Twelve Data
 ↓
OHLCV / Quote Data
 ↓
Data Validation / Normalization
 ↓
Analysis Engine
 ↓
Strategy Layer
 ↓
Groq / Mistral
 ↓
Signal Validation
 ↓
Result
```

---

## 8. Data Normalization

Normalize Twelve Data responses into Karren's internal market-data format.

**Do NOT allow Twelve Data's response format to propagate throughout the entire codebase.**

### Internal Models

```python
class MarketSnapshot:
    symbol: str
    asset_class: AssetClass
    timeframe: Timeframe
    timestamp: datetime
    candles: list[Candle]
    quote: Quote | None
    provider: str

class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None

class Quote:
    bid: float
    ask: float
    spread: float
    timestamp: datetime

class Instrument:
    symbol: str
    display_name: str
    asset_class: AssetClass
    provider_symbol: str
```

The analysis engine should operate on Karren's normalized representation.

---

## 9. Price Formatting

This is a strict global requirement.

### NEVER use thousands separators.

**Incorrect:**
```
103,450.25
```

**Correct:**
```
103450.25
```

### Decimal Rules

- Decimals must be preserved when required by the instrument
- Do not unnecessarily add trailing zeros

**Examples:**
```
1.17342
0.00001247
103450.25
4521.37
```

### Scope

This applies to:
- Current price
- Entry
- Stop loss
- Take profit
- Support
- Resistance
- Targets
- Other displayed price levels

The frontend formatting layer must enforce this consistently.

---

## 10. Signal Format

For a forex setup, Karren might produce:

```
GBP/USD — 4H

SIGNAL: LONG

Entry: 1.35142
Stop Loss: 1.34680
Take Profit: 1.36520

Risk/Reward: 1:2.98

Confidence: 81%
```

**Never format those values as:**
```
1,35142
```

Or introduce comma separators anywhere in price values.

---

## 11. Default Analysis Framework

Do NOT change the previously defined default analysis framework.

Karren's default strategy remains: **Smart Multi-Factor Market Analysis**

It is NOT:
- SMC by default
- ICT by default
- Trendline trading by default
- Elliott Wave by default
- Wyckoff by default

### Analysis Dimensions

The default engine should evaluate relevant factors such as:
- Market structure
- Trend
- Support/resistance
- Price action
- Momentum
- Volatility
- Volume where available
- Breakouts/retests
- Multi-timeframe alignment
- Risk/reward
- Conflicting evidence

### Instrument Awareness

The analysis engine should be instrument-aware.

For example, it should not blindly apply crypto-specific assumptions to forex.

---

## 12. Custom Strategies

Users can provide custom strategy documents in:
- PDF
- TXT
- Markdown
- Plain text

**PDF is a first-class strategy input.**

### Example

```
My Forex Strategy.pdf
```

Karren processes it and makes its relevant rules available to the strategy-analysis layer.

### Operating Modes

**Smart Analysis:**
```
Forex market data
 ↓
Smart Multi-Factor Analysis
 ↓
Groq/Mistral
 ↓
Signal
```

**Strategy Analysis:**
```
Forex market data
 ↓
Smart Multi-Factor Analysis
 +
Custom strategy
 ↓
Groq/Mistral
 ↓
Signal
```

---

## 13. AI Providers

### Allowed Providers

```
Groq
Mistral
```

### Fallback Flow

```
Groq
 ↓
if unavailable/fails
 ↓
Mistral
```

### Prohibited

- No OpenAI
- No Anthropic
- No BYOK (Bring Your Own Key)

---

## 14. Private Product

Karren remains a private application.

### Do NOT Add

- Public signup
- Authentication
- Subscriptions
- Payments
- User accounts
- Broker execution
- Automated trading

The purpose is to prove signal quality first.

---

## 15. Implementation Requirements

### Before Implementing Twelve Data Integration

1. Inspect the existing repository
2. Determine whether a market-data service already exists
3. Reuse existing architecture where appropriate
4. Implement Twelve Data behind the market-data abstraction
5. Add tests for:
   - Pair search
   - Quote retrieval
   - Candle retrieval
   - Invalid symbols
   - API failures
   - Malformed responses
   - Rate-limit/API errors
   - Data normalization
6. Verify the analysis engine only consumes Karren's normalized market-data models

**Do not rewrite unrelated parts of the application.**

---

## 16. Final User Flow

```
Search:
GBP/USD

Timeframe:
4H

Strategy:
Smart Multi-Factor Analysis

[ ANALYZE ]
```

### Karren Process

```
GBP/USD
    ↓
Twelve Data
    ↓
Market data
    ↓
Market analysis
    ↓
Optional strategy rules
    ↓
Groq
    ↓
Mistral fallback
    ↓
Signal validation
    ↓
LONG / SHORT / NO SIGNAL
```

---

## Appendix A: Existing Architecture Notes

### Market Data Service — Implemented

- `MarketDataProvider` ABC in `backend/app/services/market_data.py`
- `TwelveDataProvider` — fully implemented (search, klines, ticker, snapshot)
- `BinanceProvider` — retained for crypto fallback (auto-activates if no Twelve Data key)
- `MarketDataService` wrapper class with provider delegation
- Helper functions: `to_twelve_data_symbol()`, `from_twelve_data_symbol()`, `classify_instrument()`, `format_display_name()` in `backend/app/models/market.py`

### Configuration

- `TWELVE_DATA_API_KEY` defined in `backend/app/core/config.py` — actively used by `TwelveDataProvider`
- Provider selection: Twelve Data if key is set, otherwise Binance fallback

### Models

- `AssetClass` enum: forex, metal, crypto, index, other
- `Timeframe` enum: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w
- `MarketSnapshot`, `Candle`, `Quote`, `Instrument` models in `backend/app/models/market.py`
- `MarketSnapshot` includes `data_provider` and `data_timestamp` fields for provenance

### Analysis Engine

- Pure technical analysis in `backend/app/analysis/engine.py`
- Fully decoupled from market data providers — consumes `list[dict]` of klines only
- No crypto-specific assumptions; instrument-agnostic by design
