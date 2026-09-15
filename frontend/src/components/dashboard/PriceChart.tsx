"use client";

import type { Candle } from "@/types";

interface PriceChartProps {
  pair: string;
  displayName: string;
  price: number;
  change: number;
  changePct: number;
  timeframe: string;
  candles: Candle[];
  onTimeframeChange: (tf: string) => void;
}

const TIMEFRAMES = ["1m", "5m", "15m", "1H", "4H", "1D"];

export function PriceChart({
  pair,
  displayName,
  price,
  change,
  changePct,
  timeframe,
  candles,
  onTimeframeChange,
}: PriceChartProps) {
  const data = candles.length > 0 ? candles : [];
  const closes = data.map((d) => d.close);
  const min = closes.length > 0 ? Math.min(...closes) : price;
  const max = closes.length > 0 ? Math.max(...closes) : price;
  const range = max - min || 1;
  const w = 600;
  const h = 180;
  const pad = 10;

  const points = data.map((d, i) => {
    const x = pad + (i / Math.max(data.length - 1, 1)) * (w - pad * 2);
    const y = pad + ((max - d.close) / range) * (h - pad * 2);
    return `${x},${y}`;
  });
  const pathD = points.length > 0 ? `M${points.join(" L")}` : "";

  const isPositive = changePct >= 0;
  const color = isPositive ? "var(--green-primary)" : "var(--red-primary)";

  return (
    <div className="chart-container">
      <div className="chart-header">
        <div>
          <div className="chart-pair">{displayName}</div>
          <div className="chart-subtitle">{pair}</div>
        </div>
        <div className="timeframe-controls">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              className={`timeframe-btn ${timeframe === tf ? "active" : ""}`}
              onClick={() => onTimeframeChange(tf)}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      <div className="chart-price-row">
        <span className="chart-price">{formatPrice(price)}</span>
        <span className={`chart-change ${isPositive ? "positive" : "negative"}`}>
          {isPositive ? "+" : ""}{formatPrice(change)} ({isPositive ? "+" : ""}{changePct.toFixed(2)}%)
        </span>
      </div>

      {data.length > 0 ? (
        <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: 180 }}>
          <defs>
            <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.15} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>

          {[0.25, 0.5, 0.75].map((pct) => {
            const y = pad + pct * (h - pad * 2);
            const val = max - pct * range;
            return (
              <g key={pct}>
                <line x1={pad} y1={y} x2={w - pad} y2={y} stroke="var(--border-subtle)" strokeWidth={0.5} />
                <text x={w - pad + 4} y={y + 3} fill="var(--text-muted)" fontSize={8} fontFamily="var(--font-numeric)">
                  {formatPrice(val)}
                </text>
              </g>
            );
          })}

          <path
            d={`${pathD} L${w - pad},${h - pad} L${pad},${h - pad} Z`}
            fill="url(#chartGrad)"
          />
          <path d={pathD} fill="none" stroke={color} strokeWidth={1.5} />

          {data.length > 0 && (
            <circle
              cx={pad + ((data.length - 1) / Math.max(data.length - 1, 1)) * (w - pad * 2)}
              cy={pad + ((max - data[data.length - 1].close) / range) * (h - pad * 2)}
              r={3}
              fill={color}
            />
          )}
        </svg>
      ) : (
        <div style={{ height: 180, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: 12 }}>
          Loading chart data...
        </div>
      )}
    </div>
  );
}

function formatPrice(n: number): string {
  if (Math.abs(n) >= 1000) return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n === 0) return "—";
  return n.toFixed(4);
}
