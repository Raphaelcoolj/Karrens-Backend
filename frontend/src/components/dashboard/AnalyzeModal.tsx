"use client";

import { useState } from "react";

interface AnalyzeModalProps {
  selectedPair: string;
  selectedDisplayName: string;
  onAnalyze: (pair: string, timeframe: string) => void;
  onClose: () => void;
  loading: boolean;
}

const TIMEFRAMES = ["1m", "5m", "15m", "1H", "4H", "1D"];

export function AnalyzeModal({
  selectedPair,
  selectedDisplayName,
  onAnalyze,
  onClose,
  loading,
}: AnalyzeModalProps) {
  const [timeframe, setTimeframe] = useState("4H");

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">Analyze Market</div>
        <div className="modal-subtitle">{selectedDisplayName || selectedPair}</div>

        <div className="modal-field">
          <div className="modal-field-label">Timeframe</div>
          <div className="timeframe-controls" style={{ flexWrap: "wrap" }}>
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                className={`timeframe-btn ${timeframe === tf ? "active" : ""}`}
                onClick={() => setTimeframe(tf)}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose} disabled={loading}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={() => onAnalyze(selectedPair, timeframe)}
            disabled={loading || !selectedPair}
          >
            {loading ? "Analyzing..." : "Run Analysis"}
          </button>
        </div>
      </div>
    </div>
  );
}
