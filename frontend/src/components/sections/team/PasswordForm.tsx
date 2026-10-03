"use client";

import type { FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { apiClient } from "@/lib/apiClient";
import { ActionNote } from "../setup/ActionNote";
import { useAction } from "../setup/useAction";

export function PasswordForm() {
  const { run, isPending, message, setMessage } = useAction();
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const current = String(data.get("current") ?? "");
    const next = String(data.get("next") ?? "");
    if (next.length < 8) return setMessage({ ok: false, text: "Use at least 8 characters." });
    if (next !== String(data.get("confirm") ?? "")) return setMessage({ ok: false, text: "The new passwords don't match." });
    run(
      async () => {
        await apiClient.changePassword(current, next);
        form.reset();
        return { ok: true, text: "Password changed." };
      },
      { refresh: false },
    );
  }
  return (
    <form onSubmit={handleSubmit} noValidate className="flex max-w-sm flex-col gap-4">
      <Field label="Current password" htmlFor="current">
        <Input id="current" name="current" type="password" autoComplete="current-password" />
      </Field>
      <Field label="New password" htmlFor="next">
        <Input id="next" name="next" type="password" autoComplete="new-password" />
      </Field>
      <Field label="Confirm new password" htmlFor="confirm">
        <Input id="confirm" name="confirm" type="password" autoComplete="new-password" />
      </Field>
      <div>
        <Button type="submit" disabled={isPending}>
          {isPending ? "Saving…" : "Change password"}
        </Button>
      </div>
      <ActionNote message={message} />
    </form>
  );
}
