"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { apiClient } from "@/lib/apiClient";
import { ActionNote } from "./ActionNote";
import { useAction } from "./useAction";

const SELECT_CLASS =
  "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

const LINK_CLASS =
  "inline-flex items-center rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

export function TestCallCard({
  profiles,
  canCallPhone,
}: {
  profiles: { id: string; name: string; is_default: boolean }[];
  canCallPhone: boolean;
}) {
  const { run, isPending, message } = useAction();
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [callId, setCallId] = useState<string | null>(null);

  function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    run(async () => {
      const customer = await apiClient.createCustomer({
        name: String(data.get("name") ?? "").trim() || "Test caller",
        phone: String(data.get("phone") ?? "").trim(),
        purpose: "Test call",
        profile_id: String(data.get("profile_id") ?? "") || null,
      });
      setCustomerId(customer.id);
      return { ok: true, text: "Saved. Now place the call." };
    }, { refresh: false });
  }

  function callPhone() {
    if (!customerId) return;
    run(async () => {
      const call = await apiClient.startCall(customerId);
      setCallId(call.call_id);
      return { ok: true, text: "Calling your phone now. Answer it and talk to the agent." };
    });
  }

  const defaultProfile = profiles.find((p) => p.is_default)?.id ?? profiles[0]?.id ?? "";

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={handleSave} noValidate className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Field label="Your name" htmlFor="test_name">
          <Input id="test_name" name="name" placeholder="Rahul" />
        </Field>
        <Field label="Your phone" htmlFor="test_phone">
          <Input id="test_phone" name="phone" type="tel" placeholder="+919876543210" required />
        </Field>
        <Field label="Business" htmlFor="test_profile">
          <select id="test_profile" name="profile_id" defaultValue={defaultProfile} className={SELECT_CLASS}>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="flex items-end">
          <Button type="submit" variant="secondary" disabled={isPending || customerId !== null}>
            {customerId ? "Saved" : "Save me as a test customer"}
          </Button>
        </div>
      </form>

      {customerId ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" onClick={callPhone} disabled={isPending || !canCallPhone || callId !== null}>
            Call my phone
          </Button>
          <Link href={`/customers/${customerId}/call`} className={LINK_CLASS}>
            Try it in the browser instead
          </Link>
          {callId ? (
            <Link href={`/calls/${callId}`} className="text-sm font-medium text-primary underline-offset-2 hover:underline">
              Watch the call
            </Link>
          ) : null}
          {!canCallPhone ? (
            <p className="text-sm text-muted-foreground">
              Phone calls need Twilio, a number and a public URL (steps above). The browser call
              works right away.
            </p>
          ) : null}
        </div>
      ) : null}
      <ActionNote message={message} />
    </div>
  );
}
