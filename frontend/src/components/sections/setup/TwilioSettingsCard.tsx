"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { apiClient } from "@/lib/apiClient";
import { formatPhone } from "@/lib/formatters";
import type { SettingsUpdate, SettingsView, TwilioAccountNumber } from "@/types/api";
import { ActionNote } from "./ActionNote";
import { SourceBadge } from "./SourceBadge";
import { useAction } from "./useAction";

export function TwilioSettingsCard({ settings }: { settings: SettingsView }) {
  const { run, isPending, message } = useAction();
  const importer = useAction();
  const [numbers, setNumbers] = useState<TwilioAccountNumber[] | null>(null);

  async function testConnection() {
    const result = await apiClient.testTwilio();
    setNumbers(result.ok ? (result.details?.numbers ?? []) : null);
    return { ok: result.ok, text: result.message };
  }

  function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const update: SettingsUpdate = {
      twilio_account_sid: String(data.get("twilio_account_sid") ?? "").trim(),
      twilio_phone_number: String(data.get("twilio_phone_number") ?? "").trim(),
    };
    const token = String(data.get("twilio_auth_token") ?? "").trim();
    if (token) update.twilio_auth_token = token; // empty = keep the saved token
    run(async () => {
      await apiClient.updateSettings(update);
      return testConnection();
    });
  }

  function importNumber(number: string) {
    importer.run(async () => {
      const row = await apiClient.createNumber({
        number,
        label: null,
        profile_id: null,
        inbound_enabled: true,
        outbound_enabled: true,
        is_active: true,
      });
      setNumbers((list) => list?.map((n) => (n.number === number ? { ...n, registered: true } : n)) ?? null);
      try {
        await apiClient.syncNumberToTwilio(row.id);
        return { ok: true, text: `${number} added. Calls to it now reach the agent.` };
      } catch {
        return {
          ok: true,
          text: `${number} added for outbound calls. Set the public URL, then use Sync to Twilio under Phone numbers so calls to it reach the agent.`,
        };
      }
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={handleSave} noValidate className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Field label="Account SID" htmlFor="twilio_account_sid">
          <Input
            id="twilio_account_sid"
            name="twilio_account_sid"
            defaultValue={settings.twilio_account_sid.value}
            placeholder="AC…"
            autoComplete="off"
          />
        </Field>
        <Field label="Auth Token" htmlFor="twilio_auth_token">
          <Input
            id="twilio_auth_token"
            name="twilio_auth_token"
            type="password"
            autoComplete="new-password"
            placeholder={settings.twilio_auth_token.is_set ? `${settings.twilio_auth_token.value} (leave empty to keep)` : ""}
          />
        </Field>
        <Field label="Default caller number (optional)" htmlFor="twilio_phone_number">
          <Input
            id="twilio_phone_number"
            name="twilio_phone_number"
            type="tel"
            defaultValue={settings.twilio_phone_number.value}
            placeholder="+14155550100 — or add numbers below"
          />
        </Field>
        <div className="flex flex-wrap items-end gap-2">
          <SourceBadge setting={settings.twilio_auth_token} />
        </div>
        <div className="flex flex-wrap items-center gap-3 md:col-span-2">
          <Button type="submit" disabled={isPending}>
            {isPending ? "Checking…" : "Save and test"}
          </Button>
          <Button type="button" variant="secondary" disabled={isPending} onClick={() => run(testConnection, { refresh: false })}>
            Test connection
          </Button>
          <p className="text-sm text-muted-foreground">
            Find both on the{" "}
            <a
              href="https://console.twilio.com"
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-2 hover:underline"
            >
              Twilio console
            </a>{" "}
            home page. The token is stored encrypted.
          </p>
        </div>
        <div className="md:col-span-2">
          <ActionNote message={message} />
        </div>
      </form>

      {numbers ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-foreground">Numbers on this Twilio account</h3>
          {numbers.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No numbers yet. Buy one with Voice capability in the Twilio console, then test again.
            </p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {numbers.map((n) => (
                <li key={n.number} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                  <span>
                    <span className="font-medium text-foreground">{formatPhone(n.number)}</span>
                    {n.friendly_name && n.friendly_name !== n.number ? (
                      <span className="text-muted-foreground"> · {n.friendly_name}</span>
                    ) : null}
                  </span>
                  {n.registered ? (
                    <span className="text-muted-foreground">Added</span>
                  ) : (
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={importer.isPending}
                      onClick={() => importNumber(n.number)}
                    >
                      Add to the agent
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
          <ActionNote message={importer.message} />
        </div>
      ) : null}
    </div>
  );
}
