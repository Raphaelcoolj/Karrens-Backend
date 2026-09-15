export interface MarketCard {
  symbol: string;
  displayName: string;
  price: number;
  change: number;
  changePct: number;
}

export type Direction = "LONG" | "SHORT" | "NO SIGNAL";

export type AssetClass = "forex" | "metal" | "crypto" | "index" | "other";

export type StrategyStatus = "pending" | "processing" | "ready" | "failed";

export interface Instrument {
  symbol: string;
  display_name: string;
  asset_class: AssetClass;
  base_currency: string;
  quote_currency: string;
  description: string;
}

export interface Quote {
  symbol: string;
  bid: number | null;
  ask: number | null;
  spread: number | null;
  timestamp: string | null;
}

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketSnapshot {
  symbol: string;
  asset_class: AssetClass;
  timeframe: string;
  timestamp: string;
  candles: Candle[];
  quote: Quote | null;
  data_provider: string;
  data_timestamp: string | null;
}

export interface Signal {
  id?: string | null;
  pair: string;
  timeframe: string;
  direction: Direction;
  entry: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward: number | null;
  confidence: number;
  reasoning: string;
  triggered_conditions: string[];
  invalidating_conditions: string[];
  strategy_alignment: string | null;
  market_context: string;
  strategy_used?: string | null;
  model_provider?: string | null;
  model_name?: string | null;
  timestamp?: string;
}

export interface AnalyzeResponse {
  pair: string;
  timeframe: string;
  direction: Direction;
  entry: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward: number | null;
  confidence: number;
  reasoning: string;
  triggered_conditions: string[];
  invalidating_conditions: string[];
  strategy_alignment: string | null;
  market_context: string;
  model_provider: string | null;
  processing_time_ms: number | null;
  data_provider: string | null;
  data_timestamp: string | null;
}

export interface AnalysisResult {
  id?: string;
  pair: string;
  timeframe: string;
  strategy_id: string | null;
  market_data_snapshot: Record<string, unknown>;
  technical_analysis: Record<string, unknown>;
  strategy_context: Record<string, unknown> | null;
  ai_reasoning: string;
  signal: Signal | null;
  timestamp: string;
  model_provider: string | null;
  model_name: string | null;
  processing_time_ms: number | null;
}

export interface StrategyDocument {
  id: string;
  name: string;
  source_type: string;
  original_filename: string;
  cloudinary_url: string | null;
  status: StrategyStatus;
  version: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface StrategyRules {
  id?: string;
  strategy_id: string;
  entry_rules: string[];
  exit_rules: string[];
  confirmation_rules: string[];
  invalidation_rules: string[];
  timeframe_requirements: string[];
  indicators: string[];
  market_structure_requirements: string[];
  risk_rules: string[];
  exceptions: string[];
  terminology: Record<string, string>;
  examples: string[];
  raw_text: string;
}

export interface TechnicalAnalysis {
  current_price: number;
  price_change_20: number | null;
  market_structure: {
    structure: string;
    trend: string;
    details: string;
  };
  key_levels: {
    support: number[];
    resistance: number[];
  };
  swing_points: {
    swing_highs: Array<{ index: number; price: number }>;
    swing_lows: Array<{ index: number; price: number }>;
  };
  volatility: {
    current_atr: number;
    recent_volatility_pct: number;
    volatility_expanding: boolean;
  };
  momentum: {
    rsi: number;
    rsi_zone: string;
    ema_9: number;
    ema_21: number;
    ema_50: number;
    ema_alignment: string;
    macd_crossover: string | null;
  };
  volume: {
    current: number;
    average_20: number;
    signal: string | null;
  };
}

export interface AnalyzeRequest {
  pair: string;
  timeframe: string;
  strategy_id?: string | null;
}

export interface HealthResponse {
  status: string;
}

export type NavSection = "overview" | "markets" | "signals" | "strategies" | "history";
