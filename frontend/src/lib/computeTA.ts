import type { Candle, TechnicalAnalysis } from "@/types";

export function computeTA(candles: Candle[]): TechnicalAnalysis | null {
  if (candles.length < 5) return null;

  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const volumes = candles.map((c) => c.volume);

  const currentPrice = closes[closes.length - 1];
  const prevPrice = closes[closes.length - 2] || currentPrice;
  const priceChange20 = closes.length >= 20
    ? ((currentPrice - closes[closes.length - 20]) / closes[closes.length - 20]) * 100
    : null;

  const ema9 = ema(closes, 9);
  const ema21 = ema(closes, 21);
  const ema50 = ema(closes, Math.min(50, closes.length));

  let emaAlignment: "bullish" | "bearish" | "neutral" = "neutral";
  if (ema9 > ema21 && ema21 > ema50) emaAlignment = "bullish";
  else if (ema9 < ema21 && ema21 < ema50) emaAlignment = "bearish";

  const rsiVal = rsi(closes, 14);
  let rsiZone: "overbought" | "oversold" | "neutral" = "neutral";
  if (rsiVal > 70) rsiZone = "overbought";
  else if (rsiVal < 30) rsiZone = "oversold";

  const macdCrossoverVal = macdCrossover(closes);

  const atrVal = atr(candles, 14);
  const avgVolume = volumes.length >= 20
    ? volumes.slice(-20).reduce((a, b) => a + b, 0) / 20
    : volumes.reduce((a, b) => a + b, 0) / volumes.length;
  const currentVolume = volumes[volumes.length - 1];
  let volumeSignal: "high" | "low" | "normal" | null = "normal";
  if (currentVolume > avgVolume * 1.5) volumeSignal = "high";
  else if (currentVolume < avgVolume * 0.5) volumeSignal = "low";

  const swingHighs = findSwingPoints(highs, "high");
  const swingLows = findSwingPoints(lows, "low");

  const support = findLevels(lows, "support").slice(0, 3);
  const resistance = findLevels(highs, "resistance").slice(0, 3);

  let trend: "bullish" | "bearish" | "range" = "range";
  if (emaAlignment === "bullish" && rsiVal > 50) trend = "bullish";
  else if (emaAlignment === "bearish" && rsiVal < 50) trend = "bearish";

  let structure: "bullish" | "bearish" | "range" = "range";
  if (swingHighs.length >= 2 && swingLows.length >= 2) {
    const lastHH = swingHighs[swingHighs.length - 1].price > swingHighs[swingHighs.length - 2].price;
    const lastHL = swingLows[swingLows.length - 1].price > swingLows[swingLows.length - 2].price;
    if (lastHH && lastHL) structure = "bullish";
    else if (!lastHH && !lastHL) structure = "bearish";
  }

  const recentVol = closes.length >= 20
    ? Math.abs((closes[closes.length - 1] - closes[closes.length - 20]) / closes[closes.length - 20]) * 100
    : 0;

  return {
    current_price: currentPrice,
    price_change_20: priceChange20,
    market_structure: {
      structure,
      trend,
      details: structure === "bullish" ? "Higher highs and higher lows" : structure === "bearish" ? "Lower highs and lower lows" : "Sideways consolidation",
    },
    swing_points: { swing_highs: swingHighs, swing_lows: swingLows },
    key_levels: { support, resistance },
    volatility: {
      current_atr: atrVal,
      recent_volatility_pct: recentVol,
      volatility_expanding: atrVal > (atr(candles.slice(0, -5), 14) || atrVal) * 1.1,
    },
    momentum: {
      rsi: rsiVal,
      rsi_zone: rsiZone,
      ema_9: ema9,
      ema_21: ema21,
      ema_50: ema50,
      ema_alignment: emaAlignment,
      macd_crossover: macdCrossoverVal,
    },
    volume: {
      current: currentVolume,
      average_20: avgVolume,
      signal: volumeSignal,
    },
  };
}

function ema(data: number[], period: number): number {
  if (data.length === 0) return 0;
  const k = 2 / (period + 1);
  let val = data[0];
  for (let i = 1; i < data.length; i++) {
    val = data[i] * k + val * (1 - k);
  }
  return val;
}

function rsi(data: number[], period: number): number {
  if (data.length < period + 1) return 50;
  let gains = 0;
  let losses = 0;
  for (let i = data.length - period; i < data.length; i++) {
    const diff = data[i] - data[i - 1];
    if (diff > 0) gains += diff;
    else losses -= diff;
  }
  if (losses === 0) return 100;
  const rs = gains / losses;
  return 100 - 100 / (1 + rs);
}

function macdCrossover(data: number[]): "bullish" | "bearish" | null {
  if (data.length < 35) return null;
  const ema12 = ema(data, 12);
  const ema26 = ema(data, 26);
  const macdNow = ema12 - ema26;

  const prev = data.slice(0, -1);
  const ema12p = ema(prev, 12);
  const ema26p = ema(prev, 26);
  const macdPrev = ema12p - ema26p;

  if (macdPrev <= 0 && macdNow > 0) return "bullish";
  if (macdPrev >= 0 && macdNow < 0) return "bearish";
  return null;
}

function atr(candles: Candle[], period: number): number {
  if (candles.length < period + 1) {
    return candles.reduce((sum, c) => sum + (c.high - c.low), 0) / candles.length;
  }
  let sum = 0;
  for (let i = candles.length - period; i < candles.length; i++) {
    const tr = Math.max(
      candles[i].high - candles[i].low,
      Math.abs(candles[i].high - candles[i - 1].close),
      Math.abs(candles[i].low - candles[i - 1].close)
    );
    sum += tr;
  }
  return sum / period;
}

function findSwingPoints(prices: number[], type: "high" | "low"): Array<{ index: number; price: number }> {
  const points: Array<{ index: number; price: number }> = [];
  const lookback = 3;
  for (let i = lookback; i < prices.length - lookback; i++) {
    if (type === "high") {
      let isHigh = true;
      for (let j = i - lookback; j <= i + lookback; j++) {
        if (j !== i && prices[j] >= prices[i]) { isHigh = false; break; }
      }
      if (isHigh) points.push({ index: i, price: prices[i] });
    } else {
      let isLow = true;
      for (let j = i - lookback; j <= i + lookback; j++) {
        if (j !== i && prices[j] <= prices[i]) { isLow = false; break; }
      }
      if (isLow) points.push({ index: i, price: prices[i] });
    }
  }
  return points.slice(-5);
}

function findLevels(prices: number[], type: "support" | "resistance"): number[] {
  const sorted = [...prices].sort((a, b) => type === "support" ? a - b : b - a);
  const levels: number[] = [];
  const step = Math.max(1, Math.floor(sorted.length / 4));
  for (let i = 0; i < sorted.length && levels.length < 3; i += step) {
    const val = sorted[i];
    if (!levels.some((l) => Math.abs(l - val) / val < 0.005)) {
      levels.push(val);
    }
  }
  return levels;
}
