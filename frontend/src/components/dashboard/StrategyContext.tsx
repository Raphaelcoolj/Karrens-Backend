"use client";

import type { StrategyDocument } from "@/types";

interface StrategyContextProps {
  strategy: StrategyDocument | null;
}

export function StrategyContext({ strategy }: StrategyContextProps) {
  if (!strategy) {
    return (
      <div className="strategy-panel">
        <div className="strategy-panel-title">Active Strategy</div>
        <p style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No strategy selected. Choose a strategy to apply rules to analysis.</p>
      </div>
    );
  }

  const meta = strategy.metadata as Record<string, string | number>;
  const rules = (meta as Record<string, unknown>).extracted_rules as Record<string, number> | undefined;

  return (
    <div className="strategy-panel">
      <div className="strategy-panel-title">Active Strategy</div>
      <div className="strategy-name">{strategy.name}</div>

      {rules && Object.keys(rules).length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 6 }}>Extracted Rules</div>
          {Object.entries(rules).map(([key, count]) => (
            <div key={key} className="strategy-rule">
              <span className="strategy-rule-check">✓</span>
              <span>{formatRuleKey(key)} ({count})</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 16, fontSize: 11, color: "var(--text-tertiary)" }}>
        <span>Source: {strategy.source_type.toUpperCase()}</span>
        <span>Chunks: {String(meta.total_chunks ?? "—")}</span>
        <span>Sections: {String(meta.total_sections ?? "—")}</span>
      </div>
    </div>
  );
}

function formatRuleKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
