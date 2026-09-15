interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  className?: string;
}

export function Skeleton({ width, height, className = "" }: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ width, height }}
    />
  );
}

export function MarketCardSkeleton() {
  return (
    <div className="market-card">
      <Skeleton width={60} height={10} />
      <div style={{ marginTop: 8 }}>
        <Skeleton width={100} height={20} />
      </div>
      <div style={{ marginTop: 6 }}>
        <Skeleton width={50} height={12} />
      </div>
    </div>
  );
}

export function SignalPanelSkeleton() {
  return (
    <div className="signal-panel">
      <Skeleton width={80} height={10} />
      <div style={{ marginTop: 12 }}>
        <Skeleton width={120} height={32} />
      </div>
      <div style={{ marginTop: 20, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} style={{ padding: 12, background: "var(--bg-tertiary)", borderRadius: 6 }}>
            <Skeleton width={60} height={10} />
            <div style={{ marginTop: 6 }}>
              <Skeleton width={80} height={18} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
