"use client";

import type { FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { apiClient } from "@/lib/apiClient";
import type { SettingsView } from "@/types/api";
import { ActionNote } from "./ActionNote";
import { SourceBadge } from "./SourceBadge";
import { useAction } from "./useAction";

export function PublicUrlCard({ settings }: { settings: SettingsView }) {
  const { run, isPending, message } = useAction();
  const url = settings.public_url;

  async function test() {
    const result = await apiClient.testPublicUrl();
    return { ok: result.ok, text: result.message };
  }

  function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = String(new FormData(event.currentTarget).get("public_url") ?? "").trim();
    run(async () => {
      await apiClient.updatePlatformSettings({ public_url: value });
      return test();
    });
  }

  return (
    <form onSubmit={handleSave} noValidate className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <Field label="Public URL of this server" htmlFor="public_url">
            <Input
              id="public_url"
              name="public_url"
              type="url"
              defaultValue={url.value}
              placeholder="https://calls.example.com"
            />
          </Field>
        </div>
        <SourceBadge setting={url} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={isPending}>
          {isPending ? "Checking…" : "Save and check"}
        </Button>
        <Button type="button" variant="secondary" disabled={isPending} onClick={() => run(test, { refresh: false })}>
          Check reachability
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Twilio sends call audio here, so it must be reachable from the internet. With the Docker
        HTTPS setup it&apos;s your domain. For a quick test on your own computer, run{" "}
        <code>ngrok http 8000</code> and paste the https address it shows.
      </p>
      <ActionNote message={message} />
    </form>
  );
}
