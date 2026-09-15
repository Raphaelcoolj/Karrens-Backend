import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  padding?: number;
}

export function Card({ children, className = "", padding }: CardProps) {
  return (
    <div
      className={`analysis-section ${className}`}
      style={padding !== undefined ? { padding } : undefined}
    >
      {children}
    </div>
  );
}

interface CardTitleProps {
  children: ReactNode;
}

export function CardTitle({ children }: CardTitleProps) {
  return <div className="analysis-section-title">{children}</div>;
}
