"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, apiClient } from "@/lib/apiClient";
import type { CampaignAction, CampaignStatus } from "@/types/api";

const ACTIONS: Record<CampaignStatus, { action: CampaignAction; label: string; variant: "primary" | "secondary" | "danger" }[]> = {
  draft: [
    { action: "start", label: "Start calling", variant: "primary" },
    { action: "cancel", label: "Cancel", variant: "secondary" },
  ],
  running: [
    { action: "pause", label: "Pause", variant: "secondary" },
    { action: "cancel", label: "Cancel campaign", variant: "danger" },
  ],
  paused: [
    { action: "start", label: "Resume", variant: "primary" },
    { action: "cancel", label: "Cancel campaign", variant: "danger" },
  ],
  completed: [],
  cancelled: [],
};

export function CampaignControls({
  campaignId,
  status,
}: {
  campaignId: string;
  status: CampaignStatus;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function run(work: () => Promise<unknown>, after?: () => void) {
    setError(null);
    startTransition(async () => {
      try {
        await work();
        if (after) after();
        else router.refresh();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        setError(err instanceof ApiError ? err.message : "Something went wrong.");
      }
    });
  }

  const canDelete = status === "draft" || status === "completed" || status === "cancelled";

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {ACTIONS[status].map(({ action, label, variant }) => (
          <Button
            key={action}
            variant={variant}
            disabled={isPending}
            onClick={() => {
              if (action === "cancel" && !window.confirm("Cancel this campaign? Customers not yet called won't be called.")) {
                return;
              }
              run(() => apiClient.changeCampaignStatus(campaignId, action));
            }}
          >
            {label}
          </Button>
        ))}
        {canDelete ? (
          <Button
            variant="ghost"
            disabled={isPending}
            onClick={() => {
              if (!window.confirm("Delete this campaign? Its calls stay in the call history.")) return;
              run(
                () => apiClient.deleteCampaign(campaignId),
                () => {
                  router.push("/campaigns");
                  router.refresh();
                },
              );
            }}
          >
            Delete
          </Button>
        ) : null}
        {status === "paused" ? (
          <p className="text-sm text-muted-foreground">
            Paused: calls already connected finish, no new ones start.
          </p>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
