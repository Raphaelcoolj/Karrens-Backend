import type { Direction } from "@/types";

interface BadgeProps {
  direction: Direction;
}

export function DirectionBadge({ direction }: BadgeProps) {
  const cls = direction === "LONG" ? "long" : direction === "SHORT" ? "short" : "no-signal";
  return <span className={`badge ${cls}`}>{direction}</span>;
}

interface StatusBadgeProps {
  valid: boolean;
}

export function StatusBadge({ valid }: StatusBadgeProps) {
  return (
    <span className={`badge ${valid ? "valid" : "rejected"}`}>
      {valid ? "Valid" : "Rejected"}
    </span>
  );
}
