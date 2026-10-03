import Link from "next/link";
import type { SetupChecklist } from "@/types/api";

export function SetupBanner({ checklist }: { checklist: SetupChecklist | null }) {
  if (!checklist || checklist.complete || checklist.dismissed) return null;
  const done = checklist.items.filter((i) => i.done).length;
  const next = checklist.items.find((i) => !i.done);
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-medium text-foreground">
          Finish setting up — {done} of {checklist.items.length} done
        </p>
        {next ? <p className="text-sm text-muted-foreground">Next: {next.label}. {next.hint}.</p> : null}
      </div>
      <Link
        href="/get-started"
        className="inline-flex shrink-0 items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        Continue setup
      </Link>
    </div>
  );
}
