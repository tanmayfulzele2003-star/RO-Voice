import type { ReactNode } from "react";
import { Card } from "@/components/ui/Card";

export function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">{value}</p>
    </Card>
  );
}

export function StatTileRow({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">{children}</div>
  );
}
