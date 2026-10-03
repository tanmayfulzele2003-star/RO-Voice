"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";

/** A freshly created invite link, shown once with a copy button. */
export function InviteLink({ token, label }: { token: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const link = typeof window === "undefined" ? `/join?token=${token}` : `${window.location.origin}/join?token=${token}`;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-success/40 bg-success-muted px-3 py-3">
      <p className="text-sm font-medium text-success-muted-foreground">{label}</p>
      <div className="flex flex-wrap items-center gap-2">
        <code className="min-w-0 flex-1 break-all rounded bg-card px-2 py-1 text-xs text-foreground">{link}</code>
        <Button
          type="button"
          variant="secondary"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(link);
              setCopied(true);
            } catch {
              setCopied(false);
            }
          }}
        >
          {copied ? "Copied" : "Copy link"}
        </Button>
      </div>
      <p className="text-xs text-success-muted-foreground">
        Works once and expires in 7 days. It won&apos;t be shown again — send it now.
      </p>
    </div>
  );
}
