import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { StatTile, StatTileRow } from "@/components/sections/StatTile";
import { SetupBanner } from "@/components/sections/setup/SetupBanner";
import { ErrorState } from "@/components/ui/States";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { ApiError } from "@/lib/apiClient";
import { getServerApiClient } from "@/lib/serverApiClient";
import { formatDuration } from "@/lib/formatters";
import type { SetupChecklist, StatsOverview } from "@/types/api";

export const metadata: Metadata = {
  title: "Overview",
  description: "Call volume, outcomes, and lead stats at a glance.",
};

export default async function DashboardPage() {
  let stats: StatsOverview | null = null;
  let checklist: SetupChecklist | null = null;
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    [stats, checklist] = await Promise.all([
      apiClient.getStatsOverview(),
      apiClient.getSetupChecklist().catch(() => null), // the banner is optional
    ]);
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load dashboard stats.";
  }

  return (
    <PageShell
      title="Overview"
      description="Snapshot of every call the AI agent has placed or received."
    >
      <SetupBanner checklist={checklist} />
      {loadError || !stats ? (
        <ErrorState message={loadError ?? "Failed to load dashboard stats."} />
      ) : (
        <StatTileRow>
          <StatTile label="Total calls" value={String(stats.total_calls)} />
          <StatTile label="Completed" value={String(stats.completed_calls)} />
          <StatTile label="Failed" value={String(stats.failed_calls)} />
          <StatTile label="Interested leads" value={String(stats.interested_leads)} />
          <StatTile label="Follow-ups needed" value={String(stats.follow_ups_required)} />
          <StatTile label="Avg. duration" value={formatDuration(stats.avg_duration_seconds)} />
        </StatTileRow>
      )}
    </PageShell>
  );
}
