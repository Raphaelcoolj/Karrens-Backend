"use client";

const LOADING_STEPS = [
  "Fetching market data",
  "Evaluating strategy",
  "Generating signal",
  "Validating risk",
];

interface LoadingStateProps {
  currentStep?: number;
}

export function LoadingState({ currentStep = 0 }: LoadingStateProps) {
  return (
    <div className="loading-overlay">
      <div className="loading-spinner" />
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 8 }}>
        Analyzing market...
      </div>
      {LOADING_STEPS.map((step, i) => (
        <div
          key={step}
          className="loading-step"
          style={{
            color: i <= currentStep ? "var(--text-secondary)" : "var(--text-muted)",
            fontWeight: i === currentStep ? 600 : 400,
          }}
        >
          {i <= currentStep ? "✓" : "○"} {step}
        </div>
      ))}
    </div>
  );
}

export function EmptyState() {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
          <path d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
      </div>
      <div className="empty-state-title">No analysis yet</div>
      <div className="empty-state-text">
        Select a market and strategy to begin analysis.
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-state">
      <div className="error-state-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <div className="error-state-title">Analysis unavailable</div>
      <div className="error-state-text">{message}</div>
      {onRetry && (
        <button className="btn btn-secondary" onClick={onRetry}>Retry</button>
      )}
    </div>
  );
}

export function NoSignalState() {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
        </svg>
      </div>
      <div className="empty-state-title">NO SIGNAL</div>
      <div className="empty-state-text">
        Current market conditions do not meet the strategy requirements.
      </div>
    </div>
  );
}
