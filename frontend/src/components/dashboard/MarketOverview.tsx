"use client";

import type { MarketCard } from "@/types";

interface MarketOverviewProps {
  markets: MarketCard[];
  selectedSymbol: string;
  onSelect: (symbol: string, displayName: string) => void;
}

export function MarketOverview({ markets, selectedSymbol, onSelect }: MarketOverviewProps) {
  return (
    <div className="market-overview">
      {markets.map((m) => (
        <div
          key={m.symbol}
          className={`market-card ${selectedSymbol === m.symbol ? "selected" : ""}`}
          onClick={() => onSelect(m.symbol, m.displayName)}
        >
          <div className="market-card-symbol">{m.displayName}</div>
          <div className="market-card-price">{formatNum(m.price)}</div>
          <div className={`market-card-change ${m.changePct >= 0 ? "positive" : "negative"}`}>
            {m.changePct >= 0 ? "+" : ""}{m.changePct.toFixed(2)}%
          </div>
        </div>
      ))}
    </div>
  );
}

function formatNum(n: number): string {
  if (n >= 1000) return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n === 0) return "—";
  return n.toFixed(4);
}
