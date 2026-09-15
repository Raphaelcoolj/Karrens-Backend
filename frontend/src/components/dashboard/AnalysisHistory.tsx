"use client";

import type { AnalysisResult } from "@/types";
import { DirectionBadge, StatusBadge } from "@/components/ui/Badge";

interface AnalysisHistoryProps {
  analyses: AnalysisResult[];
  loading?: boolean;
}

export function AnalysisHistory({ analyses, loading }: AnalysisHistoryProps) {
  if (loading) {
    return (
      <div className="analysis-section">
        <div className="analysis-section-title">Recent Analyses</div>
        <div style={{ padding: 20, textAlign: "center", color: "var(--text-tertiary)", fontSize: 12 }}>Loading...</div>
      </div>
    );
  }

  if (analyses.length === 0) {
    return (
      <div className="analysis-section">
        <div className="analysis-section-title">Recent Analyses</div>
        <div className="empty-state" style={{ padding: 30 }}>
          <div className="empty-state-title" style={{ fontSize: 13 }}>No analyses yet</div>
          <div className="empty-state-text" style={{ fontSize: 12 }}>Run your first analysis to see results here.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="analysis-section">
      <div className="analysis-section-title">Recent Analyses</div>
      <div className="data-table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Asset</th>
              <th>Direction</th>
              <th>Confidence</th>
              <th>Entry</th>
              <th>R:R</th>
              <th>Time</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {analyses.map((a) => {
              const sig = a.signal;
              const dir = sig?.direction ?? "NO SIGNAL";
              const conf = sig?.confidence ?? 0;
              const entry = sig?.entry;
              const rr = sig?.risk_reward;
              const isValid = dir !== "NO SIGNAL" && entry != null;
              return (
                <tr key={a.id}>
                  <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{a.pair}</td>
                  <td><DirectionBadge direction={dir} /></td>
                  <td className="numeric">{conf}%</td>
                  <td className="numeric">{entry != null ? formatEntry(entry) : "—"}</td>
                  <td className="numeric">{rr != null ? rr.toFixed(2) : "—"}</td>
                  <td>{timeAgo(a.timestamp)}</td>
                  <td><StatusBadge valid={isValid} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatEntry(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}
