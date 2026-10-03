"use client";

import type { FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { apiClient } from "@/lib/apiClient";
import { ActionNote } from "../setup/ActionNote";
import { useAction } from "../setup/useAction";

export function CompanyNameForm({ name, canEdit }: { name: string; canEdit: boolean }) {
  const { run, isPending, message } = useAction();
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = String(new FormData(event.currentTarget).get("company") ?? "").trim();
    if (!value) return;
    run(async () => {
      await apiClient.renameOrganization(value);
      return { ok: true, text: "Company name saved." };
    });
  }
  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-wrap items-end gap-3">
      <div className="min-w-64 flex-1">
        <Field label="Company name" htmlFor="company">
          <Input id="company" name="company" defaultValue={name} disabled={!canEdit} />
        </Field>
      </div>
      {canEdit ? (
        <Button type="submit" variant="secondary" disabled={isPending}>
          Save
        </Button>
      ) : (
        <p className="text-sm text-muted-foreground">Only owners can rename the company.</p>
      )}
      <div className="w-full">
        <ActionNote message={message} />
      </div>
    </form>
  );
}
