import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`@container rounded-lg border border-border bg-card p-5 text-card-foreground shadow-sm ${className}`}
    >
      {children}
    </div>
  );
}
