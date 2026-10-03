"use client";

import type { FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { apiClient } from "@/lib/apiClient";
import type { SettingsView } from "@/types/api";
import { ActionNote } from "./ActionNote";
import { SourceBadge } from "./SourceBadge";
import { useAction } from "./useAction";

export function GeminiSettingsCard({ settings }: { settings: SettingsView }) {
  const { run, isPending, message } = useAction();
  const key = settings.google_api_key;

  async function test() {
    const result = await apiClient.testGemini();
    return { ok: result.ok, text: result.message };
  }

  function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = String(new FormData(event.currentTarget).get("google_api_key") ?? "").trim();
    run(async () => {
      if (value) await apiClient.updatePlatformSettings({ google_api_key: value });
      return test();
    });
  }

  return (
    <form onSubmit={handleSave} noValidate className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <Field label="Gemini API key" htmlFor="google_api_key">
            <Input
              id="google_api_key"
              name="google_api_key"
              type="password"
              autoComplete="new-password"
              placeholder={key.is_set ? `${key.value} (leave empty to keep)` : "AIza…"}
            />
          </Field>
        </div>
        <SourceBadge setting={key} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={isPending}>
          {isPending ? "Checking…" : "Save and test"}
        </Button>
        <p className="text-sm text-muted-foreground">
          Create a key at{" "}
          <a
            href="https://aistudio.google.com/apikey"
            target="_blank"
            rel="noreferrer"
            className="text-primary underline-offset-2 hover:underline"
          >
            aistudio.google.com/apikey
          </a>
          . It powers the voice conversation and the call summaries, and is stored encrypted.
        </p>
      </div>
      <ActionNote message={message} />
    </form>
  );
}
