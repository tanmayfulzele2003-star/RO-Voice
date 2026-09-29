import type { ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="w-full overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-max text-left text-sm">{children}</table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return <thead className="border-b border-border bg-muted">{children}</thead>;
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-border">{children}</tbody>;
}

export function TR({ children }: { children: ReactNode }) {
  return <tr className="hover:bg-muted/50">{children}</tr>;
}

export function TH(props: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className="px-4 py-3 font-medium text-muted-foreground"
      {...props}
    />
  );
}

export function TD(props: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className="px-4 py-3 align-middle" {...props} />;
}
