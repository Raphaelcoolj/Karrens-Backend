import type { Direction, StrategyDocument, AnalysisResult } from "@/types";

export interface MockMarketCard {
  symbol: string;
  displayName: string;
  price: number;
  change: number;
  changePct: number;
}

export const MOCK_MARKETS: MockMarketCard[] = [
  { symbol: "BTCUSD", displayName: "BTC/USD", price: 103450.25, change: 2491.30, changePct: 2.41 },
  { symbol: "ETHUSD", displayName: "ETH/USD", price: 4012.84, change: 68.32, changePct: 1.73 },
  { symbol: "US500", displayName: "S&P 500", price: 6482.11, change: -20.34, changePct: -0.31 },
  { symbol: "US30", displayName: "NASDAQ", price: 21781.32, change: 104.52, changePct: 0.48 },
  { symbol: "EURUSD", displayName: "EUR/USD", price: 1.0842, change: 0.0023, changePct: 0.21 },
  { symbol: "XAUUSD", displayName: "GOLD", price: 2648.30, change: 18.70, changePct: 0.71 },
];

export const MOCK_CHART_DATA = Array.from({ length: 60 }, (_, i) => {
  const base = 103450;
  const trend = Math.sin(i / 10) * 800;
  const noise = (Math.random() - 0.5) * 400;
  const price = base + trend + noise;
  return {
    time: i,
    open: price - 50,
    high: price + 80 + Math.random() * 120,
    low: price - 80 - Math.random() * 120,
    close: price + (Math.random() - 0.4) * 100,
  };
});

export const MOCK_SIGNAL = {
  pair: "BTCUSD",
  timeframe: "4h",
  direction: "LONG" as Direction,
  entry: 103450.25,
  stop_loss: 101200.50,
  take_profit: 110800.75,
  risk_reward: 3.27,
  confidence: 82,
  reasoning:
    "Bitcoin shows strong bullish structure with higher highs and higher lows on the 4H timeframe. RSI at 62 supports continued momentum without being overbought. Price is holding above the 50 EMA with expanding volume on the recent push.",
  triggered_conditions: [
    "Bullish market structure confirmed",
    "RSI supports momentum",
    "Price above key support at 101,200",
    "Volume confirmation present",
  ],
  invalidating_conditions: [
    "Break below 101,200 support level",
    "RSI divergence on daily timeframe",
  ],
  model_provider: "groq",
  processing_time_ms: 2340,
  data_provider: "twelve_data",
};

export const MOCK_TECHNICAL_ANALYSIS = {
  current_price: 103450.25,
  price_change_20: 2.41,
  market_structure: {
    structure: "bullish",
    trend: "bullish",
    details: "Higher highs and higher lows",
  },
  swing_points: {
    swing_highs: [
      { index: 45, price: 104200.00 },
      { index: 30, price: 103100.00 },
    ],
    swing_lows: [
      { index: 38, price: 101800.00 },
      { index: 20, price: 100500.00 },
    ],
  },
  key_levels: {
    support: [101200.50, 99800.00, 97500.00],
    resistance: [105800.00, 108200.00, 112000.00],
  },
  volatility: {
    current_atr: 1850.42,
    recent_volatility_pct: 3.2,
    volatility_expanding: false,
  },
  momentum: {
    rsi: 62.4,
    rsi_zone: "neutral",
    ema_9: 103120.50,
    ema_21: 102480.30,
    ema_50: 100950.00,
    ema_alignment: "bullish",
    macd_crossover: "bullish",
  },
  volume: {
    current: 14500,
    average_20: 11200,
    signal: "high",
  },
};

export const MOCK_STRATEGIES: StrategyDocument[] = [
  {
    id: "strat1",
    name: "Momentum Breakout v2",
    source_type: "pdf",
    original_filename: "momentum_breakout.pdf",
    cloudinary_url: null,
    status: "ready",
    version: 2,
    metadata: { total_sections: 5, total_chunks: 8, text_length: 4200 },
    created_at: "2025-09-10T14:00:00Z",
    updated_at: "2025-09-10T14:00:00Z",
  },
  {
    id: "strat2",
    name: "ICT Structure",
    source_type: "txt",
    original_filename: "ict_structure.txt",
    cloudinary_url: null,
    status: "ready",
    version: 1,
    metadata: { total_sections: 4, total_chunks: 6, text_length: 3100 },
    created_at: "2025-09-08T10:00:00Z",
    updated_at: "2025-09-08T10:00:00Z",
  },
];

export const MOCK_HISTORY: AnalysisResult[] = [
  {
    id: "a1",
    pair: "BTCUSD",
    timeframe: "4h",
    strategy_id: "strat1",
    market_data_snapshot: {},
    technical_analysis: {},
    strategy_context: null,
    ai_reasoning: "Strong bullish structure",
    signal: {
      pair: "BTCUSD",
      timeframe: "4h",
      direction: "LONG",
      entry: 103450.25,
      stop_loss: 101200.50,
      take_profit: 110800.75,
      risk_reward: 3.27,
      confidence: 82,
      reasoning: "",
      triggered_conditions: [],
      invalidating_conditions: [],
      strategy_alignment: null,
      market_context: "",
    },
    timestamp: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
    model_provider: "groq",
    model_name: null,
    processing_time_ms: 2340,
  },
  {
    id: "a2",
    pair: "ETHUSD",
    timeframe: "4h",
    strategy_id: null,
    market_data_snapshot: {},
    technical_analysis: {},
    strategy_context: null,
    ai_reasoning: "Bearish rejection at resistance",
    signal: {
      pair: "ETHUSD",
      timeframe: "4h",
      direction: "SHORT",
      entry: 4018.00,
      stop_loss: 4100.00,
      take_profit: 3850.00,
      risk_reward: 2.05,
      confidence: 74,
      reasoning: "",
      triggered_conditions: [],
      invalidating_conditions: [],
      strategy_alignment: null,
      market_context: "",
    },
    timestamp: new Date(Date.now() - 18 * 60 * 1000).toISOString(),
    model_provider: "groq",
    model_name: null,
    processing_time_ms: 1890,
  },
  {
    id: "a3",
    pair: "EURUSD",
    timeframe: "1h",
    strategy_id: null,
    market_data_snapshot: {},
    technical_analysis: {},
    strategy_context: null,
    ai_reasoning: "Consolidation, no clear signal",
    signal: {
      pair: "EURUSD",
      timeframe: "1h",
      direction: "NO SIGNAL",
      entry: null,
      stop_loss: null,
      take_profit: null,
      risk_reward: null,
      confidence: 41,
      reasoning: "",
      triggered_conditions: [],
      invalidating_conditions: [],
      strategy_alignment: null,
      market_context: "",
    },
    timestamp: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
    model_provider: "mistral",
    model_name: null,
    processing_time_ms: 3100,
  },
];
