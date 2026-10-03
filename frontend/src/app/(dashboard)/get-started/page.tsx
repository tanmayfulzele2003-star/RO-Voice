import type { ReactNode } from "react";
import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { FinishSetupButton } from "@/components/sections/setup/FinishSetupButton";
import { GeminiSettingsCard } from "@/components/sections/setup/GeminiSettingsCard";
import { PublicUrlCard } from "@/components/sections/setup/PublicUrlCard";
import { TemplatePicker } from "@/components/sections/setup/TemplatePicker";
import { TestCallCard } from "@/components/sections/setup/TestCallCard";
import { TwilioSettingsCard } from "@/components/sections/setup/TwilioSettingsCard";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type {
  BusinessProfile,
  ChecklistKey,
  Me,
  OrgSettingsView,
  ProfileTemplate,
  SettingsView,
  SetupChecklist,
} from "@/types/api";

export const metadata: Metadata = {
  title: "Get started",
  description: "Connect your accounts and make your first AI call.",
};

function Step({
  number,
  title,
  done,
  description,
  children,
}: {
  number: number;
  title: string;
  done: boolean;
  description: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card>
      <section aria-labelledby={`step-${number}`} className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 id={`step-${number}`} className="text-base font-semibold text-foreground">
              {number}. {title}
            </h2>
            <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
          </div>
          {done ? <Badge tone="success">Done</Badge> : <Badge>To do</Badge>}
        </div>
        {children}
      </section>
    </Card>
  );
}

export default async function GetStartedPage() {
  let checklist: SetupChecklist | null = null;
  let me: Me | null = null;
  let orgSettings: OrgSettingsView | null = null;
  let platform: SettingsView | null = null;
  let templates: ProfileTemplate[] = [];
  let profiles: BusinessProfile[] = [];
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    [me, checklist, templates, profiles] = await Promise.all([
      apiClient.getMe(),
      apiClient.getSetupChecklist(),
      apiClient.listProfileTemplates(),
      apiClient.listProfiles(),
    ]);
    // Connection settings are admin-only; others just see progress.
    if (me.role === "admin" || me.role === "owner") orgSettings = await apiClient.getOrgSettings();
    if (me.is_platform_admin) platform = await apiClient.getPlatformSettings();
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load setup.";
  }

  if (loadError || !checklist || !me) {
    return (
      <PageShell title="Get started">
        <ErrorState message={loadError ?? "Failed to load setup."} />
      </PageShell>
    );
  }

  const done = Object.fromEntries(checklist.items.map((i) => [i.key, i.done])) as Partial<
    Record<ChecklistKey, boolean>
  >;
  const doneCount = checklist.items.filter((i) => i.done).length;
  // A customer company's checklist leaves out the platform's steps.
  const canCallPhone = Boolean(done.twilio && done.number && (done.public_url ?? true));
  let step = 0;

  return (
    <PageShell
      title="Get started"
      description={`${doneCount} of ${checklist.items.length} done. Each step saves on its own, so you can come back any time.`}
    >
      <Step
        number={++step}
        title="Connect Twilio"
        done={Boolean(done.twilio && done.number)}
        description="Twilio places and receives the phone calls. Connect your account, then add the numbers the agent should use."
      >
        {orgSettings ? (
          <TwilioSettingsCard
            settings={orgSettings.settings}
            usesPlatform={orgSettings.uses_platform_twilio && orgSettings.platform_twilio_available}
          />
        ) : (
          <p className="text-sm text-muted-foreground">An admin of your company connects Twilio.</p>
        )}
      </Step>
      {platform ? (
        <>
          <Step
            number={++step}
            title="Connect Gemini"
            done={Boolean(done.gemini)}
            description="Google's Gemini is the voice and brain of the agent. Shared by every company on this installation."
          >
            <GeminiSettingsCard settings={platform} />
          </Step>
          <Step
            number={++step}
            title="Set the public URL"
            done={Boolean(done.public_url)}
            description="The address Twilio uses to reach this server during calls."
          >
            <PublicUrlCard settings={platform} />
          </Step>
        </>
      ) : null}
      <Step
        number={++step}
        title="Set up your business"
        done={Boolean(done.profile)}
        description="Who the agent represents, what it sells and what it asks callers."
      >
        <TemplatePicker templates={templates} />
      </Step>
      <Step
        number={++step}
        title="Make a test call"
        done={Boolean(done.test_call)}
        description="Talk to your agent the way a customer would."
      >
        <TestCallCard
          profiles={profiles.map((p) => ({ id: p.id, name: p.name, is_default: p.is_default }))}
          canCallPhone={canCallPhone}
        />
      </Step>
      <FinishSetupButton complete={checklist.complete} />
    </PageShell>
  );
}
