import statistics
from typing import Optional


def ema(data: list[float], period: int) -> list[Optional[float]]:
    if len(data) < period:
        return [None] * len(data)
    result = [None] * (period - 1)
    multiplier = 2 / (period + 1)
    result.append(sum(data[:period]) / period)
    for i in range(period, len(data)):
        result.append((data[i] - result[-1]) * multiplier + result[-1])
    return result


def sma(data: list[float], period: int) -> list[Optional[float]]:
    if len(data) < period:
        return [None] * len(data)
    result = [None] * (period - 1)
    window_sum = sum(data[:period])
    result.append(window_sum / period)
    for i in range(period, len(data)):
        window_sum += data[i] - data[i - period]
        result.append(window_sum / period)
    return result


def rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    if len(closes) < period + 1:
        return [None] * len(closes)
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result = [None] * period
    rs = avg_gain / avg_loss if avg_loss != 0 else 100
    result.append(100 - (100 / (1 + rs)))
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        result.append(100 - (100 / (1 + rs)))
    return result


def macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict:
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = []
    for f, s in zip(ema_fast, ema_slow):
        if f is not None and s is not None:
            macd_line.append(f - s)
        else:
            macd_line.append(None)
    valid_macd = [v for v in macd_line if v is not None]
    signal_line = ema(valid_macd, signal_period) if len(valid_macd) >= signal_period else []
    histogram = []
    si = 0
    for v in macd_line:
        if v is None:
            histogram.append(None)
        elif si < len(signal_line) and signal_line[si] is not None:
            histogram.append(v - signal_line[si])
            si += 1
        else:
            histogram.append(None)
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> list[Optional[float]]:
    if len(closes) < 2:
        return [None] * len(closes)
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return [None] * len(trs)
    result = [None] * (period - 1)
    result.append(sum(trs[:period]) / period)
    for i in range(period, len(trs)):
        result.append((result[-1] * (period - 1) + trs[i]) / period)
    return result


def bollinger_bands(
    closes: list[float], period: int = 20, std_dev: float = 2.0
) -> dict:
    mid = sma(closes, period)
    upper = []
    lower = []
    for i, c in enumerate(closes):
        if mid[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            window = closes[max(0, i - period + 1) : i + 1]
            std = float(statistics.stdev(window)) if len(window) > 1 else 0
            upper.append(mid[i] + std_dev * std)
            lower.append(mid[i] - std_dev * std)
    return {"upper": upper, "middle": mid, "lower": lower}


def find_swing_points(
    highs: list[float], lows: list[float], lookback: int = 5
) -> dict:
    swing_highs = []
    swing_lows = []
    for i in range(lookback, len(highs) - lookback):
        if all(highs[i] >= highs[i - j] for j in range(1, lookback + 1)) and all(
            highs[i] >= highs[i + j] for j in range(1, lookback + 1)
        ):
            swing_highs.append({"index": i, "price": highs[i]})
        if all(lows[i] <= lows[i - j] for j in range(1, lookback + 1)) and all(
            lows[i] <= lows[i + j] for j in range(1, lookback + 1)
        ):
            swing_lows.append({"index": i, "price": lows[i]})
    return {"swing_highs": swing_highs, "swing_lows": swing_lows}


def detect_market_structure(
    swing_highs: list[dict], swing_lows: list[dict]
) -> dict:
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return {"structure": "undetermined", "details": "Insufficient swing points"}

    recent_highs = swing_highs[-3:]
    recent_lows = swing_lows[-3:]

    hh = all(
        recent_highs[i]["price"] > recent_highs[i - 1]["price"]
        for i in range(1, len(recent_highs))
    )
    hl = all(
        recent_lows[i]["price"] > recent_lows[i - 1]["price"]
        for i in range(1, len(recent_lows))
    )
    lh = all(
        recent_highs[i]["price"] < recent_highs[i - 1]["price"]
        for i in range(1, len(recent_highs))
    )
    ll = all(
        recent_lows[i]["price"] < recent_lows[i - 1]["price"]
        for i in range(1, len(recent_lows))
    )

    if hh and hl:
        return {"structure": "bullish", "trend": "uptrend", "details": "Higher highs and higher lows"}
    elif lh and ll:
        return {"structure": "bearish", "trend": "downtrend", "details": "Lower highs and lower lows"}
    elif hl and lh:
        return {"structure": "range", "trend": "sideways", "details": "Higher lows and lower highs - consolidation"}
    else:
        return {"structure": "mixed", "trend": "unclear", "details": "Mixed structure signals"}


def find_key_levels(
    swing_highs: list[dict], swing_lows: list[dict], closes: list[float]
) -> dict:
    all_prices = [s["price"] for s in swing_highs] + [s["price"] for s in swing_lows]
    if not all_prices:
        return {"support": [], "resistance": []}

    current = closes[-1] if closes else 0
    support = sorted([p for p in all_prices if p < current], reverse=True)[:3]
    resistance = sorted([p for p in all_prices if p > current])[:3]
    return {"support": support, "resistance": resistance}


def calculate_volatility_metrics(
    closes: list[float], highs: list[float], lows: list[float]
) -> dict:
    if len(closes) < 20:
        return {}

    returns = [(closes[i] - closes[i - 1]) / closes[i - 1] * 100 for i in range(1, len(closes))]
    atr_vals = atr(highs, lows, closes)
    current_atr = next((v for v in reversed(atr_vals) if v is not None), None)

    recent_vol = float(statistics.stdev(returns[-20:])) if len(returns) >= 20 else None
    older_vol = float(statistics.stdev(returns[-40:-20])) if len(returns) >= 40 else None

    vol_expansion = None
    if recent_vol is not None and older_vol is not None and older_vol > 0:
        vol_expansion = recent_vol > older_vol

    return {
        "current_atr": current_atr,
        "recent_volatility_pct": round(recent_vol, 4) if recent_vol else None,
        "volatility_expanding": vol_expansion,
    }


def calculate_momentum_metrics(closes: list[float]) -> dict:
    rsi_vals = rsi(closes)
    macd_vals = macd(closes)
    ema_9 = ema(closes, 9)
    ema_21 = ema(closes, 21)
    ema_50 = ema(closes, 50)

    current_rsi = next((v for v in reversed(rsi_vals) if v is not None), None)
    current_ema_9 = next((v for v in reversed(ema_9) if v is not None), None)
    current_ema_21 = next((v for v in reversed(ema_21) if v is not None), None)
    current_ema_50 = next((v for v in reversed(ema_50) if v is not None), None)

    valid_macd = [v for v in macd_vals["macd"] if v is not None]
    valid_signal = [v for v in macd_vals["signal"] if v is not None]
    macd_cross = None
    if len(valid_macd) >= 2 and len(valid_signal) >= 2:
        if valid_macd[-1] > valid_signal[-1] and valid_macd[-2] <= valid_signal[-2]:
            macd_cross = "bullish"
        elif valid_macd[-1] < valid_signal[-1] and valid_macd[-2] >= valid_signal[-2]:
            macd_cross = "bearish"

    return {
        "rsi": round(current_rsi, 2) if current_rsi else None,
        "rsi_zone": (
            "overbought" if current_rsi and current_rsi > 70
            else "oversold" if current_rsi and current_rsi < 30
            else "neutral"
        ),
        "ema_9": current_ema_9,
        "ema_21": current_ema_21,
        "ema_50": current_ema_50,
        "ema_alignment": (
            "bullish" if current_ema_9 and current_ema_21 and current_ema_9 > current_ema_21
            else "bearish" if current_ema_9 and current_ema_21 and current_ema_9 < current_ema_21
            else "neutral"
        ),
        "macd_crossover": macd_cross,
    }


def analyze_market(klines: list[dict]) -> dict:
    if not klines or len(klines) < 50:
        return {"error": "Insufficient data for analysis"}

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]

    swings = find_swing_points(highs, lows, lookback=5)
    structure = detect_market_structure(swings["swing_highs"], swings["swing_lows"])
    levels = find_key_levels(swings["swing_highs"], swings["swing_lows"], closes)
    volatility = calculate_volatility_metrics(closes, highs, lows)
    momentum = calculate_momentum_metrics(closes)

    current_price = closes[-1]
    price_change_20 = ((current_price - closes[-20]) / closes[-20] * 100) if len(closes) >= 20 else None

    vol_avg = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else None
    current_vol = volumes[-1]
    vol_signal = None
    if vol_avg and current_vol:
        vol_ratio = current_vol / vol_avg
        vol_signal = "high" if vol_ratio > 1.5 else "low" if vol_ratio < 0.5 else "normal"

    return {
        "current_price": current_price,
        "price_change_20": round(price_change_20, 2) if price_change_20 else None,
        "market_structure": structure,
        "key_levels": levels,
        "swing_points": swings,
        "volatility": volatility,
        "momentum": momentum,
        "volume": {"current": current_vol, "average_20": vol_avg, "signal": vol_signal},
    }
