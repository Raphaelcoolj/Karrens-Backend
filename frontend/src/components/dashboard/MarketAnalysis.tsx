"use client";

import type { TechnicalAnalysis } from "@/types";

interface MarketAnalysisProps {
  ta: TechnicalAnalysis;
}

export function MarketAnalysis({ ta }: MarketAnalysisProps) {
  return (
    <div className="grid-2" style={{ marginBottom: 12 }}>
      <div className="analysis-section">
        <div className="analysis-section-title">Market Structure</div>
        <div className="analysis-row">
          <span className="analysis-row-label">Trend</span>
          <span className={`analysis-row-value ${ta.market_structure.trend === "bullish" ? "positive" : ta.market_structure.trend === "bearish" ? "negative" : ""}`}>
            {capitalize(ta.market_structure.trend)}
          </span>
        </div>
        <div className="analysis-row">
          <span className="analysis-row-label">Structure</span>
          <span className="analysis-row-value">{capitalize(ta.market_structure.structure)}</span>
        </div>
        <div className="analysis-row">
          <span className="analysis-row-label">Details</span>
          <span className="analysis-row-value" style={{ fontSize: 11 }}>{ta.market_structure.details}</span>
        </div>
      </div>

      <div className="analysis-section">
        <div className="analysis-section-title">Momentum</div>
        <div className="analysis-row">
          <span className="analysis-row-label">RSI</span>
          <span className={`analysis-row-value ${ta.momentum.rsi_zone === "oversold" ? "positive" : ta.momentum.rsi_zone === "overbought" ? "negative" : ""}`}>
            {ta.momentum.rsi.toFixed(1)}
          </span>
        </div>
        <div className="analysis-row">
          <span className="analysis-row-label">EMA Alignment</span>
          <span className={`analysis-row-value ${ta.momentum.ema_alignment === "bullish" ? "positive" : ta.momentum.ema_alignment === "bearish" ? "negative" : ""}`}>
            {capitalize(ta.momentum.ema_alignment)}
          </span>
        </div>
        <div className="analysis-row">
          <span className="analysis-row-label">MACD</span>
          <span className={`analysis-row-value ${ta.momentum.macd_crossover === "bullish" ? "positive" : ta.momentum.macd_crossover === "bearish" ? "negative" : ""}`}>
            {ta.momentum.macd_crossover ? capitalize(ta.momentum.macd_crossover) : "—"}
          </span>
        </div>
      </div>

      <div className="analysis-section">
        <div className="analysis-section-title">Volatility</div>
        <div className="analysis-row">
          <span className="analysis-row-label">ATR</span>
          <span className="analysis-row-value">{ta.volatility.current_atr.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
        </div>
        <div className="analysis-row">
          <span className="analysis-row-label">Volatility %</span>
          <span className="analysis-row-value">{ta.volatility.recent_volatility_pct.toFixed(1)}%</span>
        </div>
        <div className="analysis-row">
          <span className="analysis-row-label">Expanding</span>
          <span className={`analysis-row-value ${ta.volatility.volatility_expanding ? "positive" : ""}`}>
            {ta.volatility.volatility_expanding ? "Yes" : "No"}
          </span>
        </div>
      </div>

      <div className="analysis-section">
        <div className="analysis-section-title">Volume</div>
        <div className="analysis-row">
          <span className="analysis-row-label">Current</span>
          <span className="analysis-row-value">{ta.volume.current.toLocaleString()}</span>
        </div>
        <div className="analysis-row">
          <span className="analysis-row-label">Avg (20)</span>
          <span className="analysis-row-value">{ta.volume.average_20.toLocaleString()}</span>
        </div>
        <div className="analysis-row">
          <span className="analysis-row-label">Signal</span>
          <span className={`analysis-row-value ${ta.volume.signal === "high" ? "positive" : ta.volume.signal === "low" ? "negative" : ""}`}>
            {ta.volume.signal ? capitalize(ta.volume.signal) : "Normal"}
          </span>
        </div>
      </div>

      <div className="analysis-section" style={{ gridColumn: "span 2" }}>
        <div className="analysis-section-title">Key Levels</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 6 }}>Resistance</div>
            {ta.key_levels.resistance.map((r, i) => (
              <div key={i} className="analysis-row">
                <span className="analysis-row-label">R{i + 1}</span>
                <span className="analysis-row-value negative">{r.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
              </div>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 6 }}>Support</div>
            {ta.key_levels.support.map((s, i) => (
              <div key={i} className="analysis-row">
                <span className="analysis-row-label">S{i + 1}</span>
                <span className="analysis-row-value positive">{s.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
