"use client";

import type { AnalyzeResponse } from "@/types";

interface SignalPanelProps {
  signal: AnalyzeResponse;
}

export function SignalPanel({ signal }: SignalPanelProps) {
  const dir = signal.direction;
  const dirCls = dir === "LONG" ? "long" : dir === "SHORT" ? "short" : "no-signal";
  const confPct = signal.confidence;
  const confCls = confPct > 70 ? "high" : confPct > 40 ? "medium" : "low";

  return (
    <div className="signal-panel">
      <div className="signal-panel-header">
        <span className="signal-panel-label">AI Signal</span>
        <span className={`signal-direction ${dirCls}`}>{dir}</span>
      </div>

      {dir !== "NO SIGNAL" && (
        <>
          <div className="signal-confidence">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Confidence</span>
              <span style={{ fontFamily: "var(--font-numeric)", fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>{confPct}%</span>
            </div>
            <div className="signal-confidence-bar">
              <div className={`signal-confidence-fill ${confCls}`} style={{ width: `${confPct}%` }} />
            </div>
          </div>

          <div className="signal-levels">
            <div className="signal-level">
              <div className="signal-level-label">Entry</div>
              <div className="signal-level-value">{fmt(signal.entry)}</div>
            </div>
            <div className="signal-level">
              <div className="signal-level-label">Stop Loss</div>
              <div className="signal-level-value" style={{ color: "var(--red-primary)" }}>{fmt(signal.stop_loss)}</div>
            </div>
            <div className="signal-level">
              <div className="signal-level-label">Take Profit</div>
              <div className="signal-level-value" style={{ color: "var(--green-primary)" }}>{fmt(signal.take_profit)}</div>
            </div>
            <div className="signal-level">
              <div className="signal-level-label">Risk / Reward</div>
              <div className="signal-level-value">{signal.risk_reward != null ? signal.risk_reward.toFixed(2) : "—"}</div>
            </div>
          </div>
        </>
      )}

      {signal.triggered_conditions.length > 0 && (
        <div className="signal-conditions">
          <div className="signal-conditions-title">
            {dir === "NO SIGNAL" ? "Analysis" : "Triggered Conditions"}
          </div>
          {signal.triggered_conditions.map((c, i) => (
            <div key={i} className="signal-condition-item">{c}</div>
          ))}
        </div>
      )}

      {signal.invalidating_conditions.length > 0 && (
        <div className="signal-invalidating">
          <div className="signal-conditions-title">Invalidation</div>
          {signal.invalidating_conditions.map((c, i) => (
            <div key={i} className="signal-condition-item">{c}</div>
          ))}
        </div>
      )}

      {signal.reasoning && (
        <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 12, marginTop: 12 }}>
          <div className="signal-conditions-title">Reasoning</div>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>{signal.reasoning}</p>
        </div>
      )}

      {signal.processing_time_ms && (
        <div style={{ marginTop: 12, fontSize: 10, color: "var(--text-muted)" }}>
          Processed in {signal.processing_time_ms}ms via {signal.model_provider}
          {signal.data_provider && <> · Data from {signal.data_provider}</>}
        </div>
      )}
    </div>
  );
}

function fmt(v: number | null | undefined): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1000) return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return v.toFixed(4);
}
