"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition, type FormEvent } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { ApiError, apiClient } from "@/lib/apiClient";
import { endSession } from "@/lib/session";
import { formatDateTime, formatPhone } from "@/lib/formatters";
import type { PhoneNumber, PhoneNumberInput } from "@/types/api";

const SELECT_CLASS =
  "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

const LINK_BUTTON_CLASS =
  "text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-50";

type Toggle = "is_active" | "inbound_enabled" | "outbound_enabled";

const TOGGLES: { key: Toggle; label: string }[] = [
  { key: "is_active", label: "Active" },
  { key: "outbound_enabled", label: "Outbound" },
  { key: "inbound_enabled", label: "Inbound" },
];

export function NumbersManager({
  numbers,
  profiles,
}: {
  numbers: PhoneNumber[];
  profiles: { id: string; name: string }[];
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [formError, setFormError] = useState<string | null>(null);
  const [rowMessage, setRowMessage] = useState<{ id: string; text: string; ok: boolean } | null>(
    null,
  );
  const [busyId, setBusyId] = useState<string | null>(null);

  function errorText(err: unknown, fallback: string) {
    if (err instanceof ApiError && err.status === 401) {
      endSession();
      return null;
    }
    return err instanceof ApiError ? err.message : fallback;
  }

  function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const number = String(data.get("number") ?? "").trim();
    if (!number) {
      setFormError("Enter the number in international format, e.g. +14155550100.");
      return;
    }
    const input: PhoneNumberInput = {
      number,
      label: String(data.get("label") ?? "").trim() || null,
      profile_id: String(data.get("profile_id") ?? "") || null,
      inbound_enabled: data.get("inbound_enabled") === "on",
      outbound_enabled: data.get("outbound_enabled") === "on",
      is_active: true,
    };
    startTransition(async () => {
      try {
        await apiClient.createNumber(input);
        form.reset();
        router.refresh();
      } catch (err) {
        const text = errorText(err, "Failed to add the number.");
        if (text) setFormError(text);
      }
    });
  }

  async function runRowAction(id: string, action: () => Promise<unknown>, success?: string) {
    setBusyId(id);
    setRowMessage(null);
    try {
      await action();
      if (success) setRowMessage({ id, text: success, ok: true });
      router.refresh();
    } catch (err) {
      const text = errorText(err, "Something went wrong.");
      if (text) setRowMessage({ id, text, ok: false });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <h2 className="mb-3 text-sm font-semibold text-foreground">Add a number</h2>
        <form onSubmit={handleAdd} noValidate className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <Field label="Twilio number" htmlFor="number">
            <Input id="number" name="number" type="tel" placeholder="+14155550100" required />
          </Field>
          <Field label="Label (optional)" htmlFor="label">
            <Input id="label" name="label" placeholder="Sales — Mumbai" />
          </Field>
          <Field label="Business" htmlFor="profile_id">
            <select id="profile_id" name="profile_id" defaultValue="" className={SELECT_CLASS}>
              <option value="">Shared pool (any business)</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
          <fieldset className="flex flex-col justify-end gap-1.5">
            <legend className="sr-only">Directions</legend>
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input type="checkbox" name="outbound_enabled" defaultChecked />
              Place outbound calls
            </label>
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input type="checkbox" name="inbound_enabled" defaultChecked />
              Answer inbound calls
            </label>
          </fieldset>
          <div className="flex flex-wrap items-center gap-3 md:col-span-4">
            <Button type="submit" disabled={isPending}>
              {isPending ? "Adding…" : "Add number"}
            </Button>
            <p className="text-sm text-muted-foreground">
              Add numbers you already own on Twilio, then use <strong>Sync to Twilio</strong> so
              calls to the number reach the agent.
            </p>
          </div>
          {formError ? (
            <p role="alert" className="text-sm text-danger md:col-span-4">
              {formError}
            </p>
          ) : null}
        </form>
      </Card>

      {numbers.length === 0 ? (
        <EmptyState
          title="No numbers yet"
          description="Outbound calls use TWILIO_PHONE_NUMBER from the backend's environment until you add one here."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Number</TH>
              <TH>Business</TH>
              <TH>Status</TH>
              <TH>Last used</TH>
              <TH>
                <span className="sr-only">Actions</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {numbers.map((n) => (
              <TR key={n.id}>
                <TD>
                  <p className="font-medium text-foreground">{formatPhone(n.number)}</p>
                  {n.label ? <p className="text-xs text-muted-foreground">{n.label}</p> : null}
                </TD>
                <TD>
                  <label className="sr-only" htmlFor={`profile-${n.id}`}>
                    Business for {n.number}
                  </label>
                  <select
                    id={`profile-${n.id}`}
                    value={n.profile_id ?? ""}
                    disabled={busyId === n.id}
                    onChange={(e) =>
                      runRowAction(n.id, () =>
                        apiClient.updateNumber(n.id, { profile_id: e.target.value || null }),
                      )
                    }
                    className={SELECT_CLASS}
                  >
                    <option value="">Shared pool</option>
                    {profiles.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </TD>
                <TD>
                  <div className="flex flex-wrap gap-3">
                    {TOGGLES.map((toggle) => (
                      <label key={toggle.key} className="flex items-center gap-1.5 text-sm text-foreground">
                        <input
                          type="checkbox"
                          checked={n[toggle.key]}
                          disabled={busyId === n.id}
                          onChange={(e) =>
                            runRowAction(n.id, () =>
                              apiClient.updateNumber(n.id, { [toggle.key]: e.target.checked }),
                            )
                          }
                        />
                        {toggle.label}
                      </label>
                    ))}
                  </div>
                  {!n.is_active ? (
                    <div className="mt-1">
                      <Badge tone="warning">Not in use</Badge>
                    </div>
                  ) : null}
                </TD>
                <TD>{formatDateTime(n.last_used_at)}</TD>
                <TD>
                  <div className="flex flex-wrap items-center gap-4">
                    <button
                      type="button"
                      className={LINK_BUTTON_CLASS}
                      disabled={busyId === n.id}
                      onClick={() =>
                        runRowAction(
                          n.id,
                          () => apiClient.syncNumberToTwilio(n.id),
                          "Twilio now sends calls on this number to the agent.",
                        )
                      }
                    >
                      Sync to Twilio
                    </button>
                    <button
                      type="button"
                      className="text-sm font-medium text-danger underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger disabled:opacity-50"
                      disabled={busyId === n.id}
                      onClick={() => {
                        if (window.confirm(`Remove ${n.number} from the pool?`)) {
                          runRowAction(n.id, () => apiClient.deleteNumber(n.id));
                        }
                      }}
                    >
                      Remove
                    </button>
                  </div>
                  {rowMessage?.id === n.id ? (
                    <p
                      role={rowMessage.ok ? "status" : "alert"}
                      className={`mt-1 max-w-xs text-xs ${rowMessage.ok ? "text-success" : "text-danger"}`}
                    >
                      {rowMessage.text}
                    </p>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
