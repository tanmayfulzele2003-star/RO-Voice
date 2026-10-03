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
import type { BusinessProfile, ChecklistKey, ProfileTemplate, SettingsView, SetupChecklist } from "@/types/api";

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
  let settings: SettingsView | null = null;
  let templates: ProfileTemplate[] = [];
  let profiles: BusinessProfile[] = [];
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    [checklist, settings, templates, profiles] = await Promise.all([
      apiClient.getSetupChecklist(),
      apiClient.getSettings(),
      apiClient.listProfileTemplates(),
      apiClient.listProfiles(),
    ]);
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load setup.";
  }

  if (loadError || !checklist || !settings) {
    return (
      <PageShell title="Get started">
        <ErrorState message={loadError ?? "Failed to load setup."} />
      </PageShell>
    );
  }

  const done = Object.fromEntries(checklist.items.map((i) => [i.key, i.done])) as Record<ChecklistKey, boolean>;
  const doneCount = checklist.items.filter((i) => i.done).length;
  const canCallPhone = done.twilio && done.number && done.public_url;

  return (
    <PageShell
      title="Get started"
      description={`${doneCount} of ${checklist.items.length} done. Each step saves on its own, so you can come back any time.`}
    >
      <Step
        number={1}
        title="Connect Twilio"
        done={done.twilio && done.number}
        description="Twilio places and receives the phone calls. Connect your account, then add the numbers the agent should use."
      >
        <TwilioSettingsCard settings={settings} />
      </Step>
      <Step
        number={2}
        title="Connect Gemini"
        done={done.gemini}
        description="Google's Gemini is the voice and brain of the agent."
      >
        <GeminiSettingsCard settings={settings} />
      </Step>
      <Step
        number={3}
        title="Set the public URL"
        done={done.public_url}
        description="The address Twilio uses to reach this server during calls."
      >
        <PublicUrlCard settings={settings} />
      </Step>
      <Step
        number={4}
        title="Set up your business"
        done={done.profile}
        description="Who the agent represents, what it sells and what it asks callers."
      >
        <TemplatePicker templates={templates} />
      </Step>
      <Step
        number={5}
        title="Make a test call"
        done={done.test_call}
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
