"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition, type FormEvent } from "react";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { ApiError, apiClient } from "@/lib/apiClient";
import type { BusinessProfile, ProfileField } from "@/types/api";

const profileSchema = z.object({
  name: z.string().trim().min(1, "Business name is required").max(200),
  agent_name: z.string().trim().min(1, "Agent name is required").max(100),
  industry: z.string().trim().max(200),
  description: z.string().trim().max(2000),
  products: z.string().trim().max(4000),
  call_objective: z.string().trim().min(1, "Call objective is required").max(2000),
  greeting: z.string().trim().max(1000),
  language: z.string().trim().max(50),
});

type EditableField = ProfileField & { rowId: number };

const TEXTAREA_CLASS =
  "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

let nextRowId = 1;
const toRow = (field: ProfileField): EditableField => ({ ...field, rowId: nextRowId++ });
const blankRow = (): EditableField =>
  toRow({ key: "", label: "", description: "", required: true });

export function ProfileForm({ profile }: { profile?: BusinessProfile }) {
  const router = useRouter();
  const [fields, setFields] = useState<EditableField[]>(
    profile ? profile.fields.map(toRow) : [blankRow(), blankRow(), blankRow()],
  );
  const [isDefault, setIsDefault] = useState(profile?.is_default ?? false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function updateField(rowId: number, patch: Partial<ProfileField>) {
    setFields((rows) => rows.map((row) => (row.rowId === rowId ? { ...row, ...patch } : row)));
  }

  function moveField(index: number, delta: number) {
    setFields((rows) => {
      const target = index + delta;
      if (target < 0 || target >= rows.length) return rows;
      const copy = [...rows];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy;
    });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const formData = new FormData(event.currentTarget);
    const result = profileSchema.safeParse(
      Object.fromEntries(
        Object.keys(profileSchema.shape).map((key) => [key, String(formData.get(key) ?? "")]),
      ),
    );

    const fieldErrors: Record<string, string> = {};
    if (!result.success) {
      for (const issue of result.error.issues) {
        const key = issue.path[0];
        if (typeof key === "string") fieldErrors[key] = issue.message;
      }
    }
    const filledFields = fields.filter((f) => f.label.trim());
    if (filledFields.length === 0) {
      fieldErrors.fields = "Add at least one piece of information for the agent to collect.";
    }
    setErrors(fieldErrors);
    if (!result.success || Object.keys(fieldErrors).length > 0) return;

    const orNull = (value: string) => (value ? value : null);
    const payload = {
      name: result.data.name,
      agent_name: result.data.agent_name,
      industry: orNull(result.data.industry),
      description: orNull(result.data.description),
      products: orNull(result.data.products),
      call_objective: result.data.call_objective,
      greeting: orNull(result.data.greeting),
      language: orNull(result.data.language),
      is_default: isDefault,
      fields: filledFields.map(({ key, label, description, required }) => ({
        key: key.trim(),
        label: label.trim(),
        description: description.trim(),
        required,
      })),
    };

    startTransition(async () => {
      try {
        if (profile) {
          await apiClient.updateProfile(profile.id, payload);
        } else {
          await apiClient.createProfile(payload);
        }
        router.push("/profiles");
        router.refresh();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        setFormError(err instanceof ApiError ? err.message : "Unexpected error. Please try again.");
      }
    });
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Field label="Business name" htmlFor="name" error={errors.name}>
          <Input id="name" name="name" defaultValue={profile?.name} placeholder="Sunrise Hotels" />
        </Field>
        <Field label="Agent name (persona)" htmlFor="agent_name" error={errors.agent_name}>
          <Input
            id="agent_name"
            name="agent_name"
            defaultValue={profile?.agent_name}
            placeholder="Priya"
          />
        </Field>
        <Field label="Industry (optional)" htmlFor="industry" error={errors.industry}>
          <Input
            id="industry"
            name="industry"
            defaultValue={profile?.industry ?? ""}
            placeholder="Hospitality"
          />
        </Field>
        <Field label="Language (optional)" htmlFor="language" error={errors.language}>
          <Input
            id="language"
            name="language"
            defaultValue={profile?.language ?? ""}
            placeholder="Leave empty to match the customer's language"
          />
        </Field>
        <div className="md:col-span-2">
          <Field label="About the business (optional)" htmlFor="description" error={errors.description}>
            <textarea
              id="description"
              name="description"
              rows={2}
              defaultValue={profile?.description ?? ""}
              className={TEXTAREA_CLASS}
            />
          </Field>
        </div>
        <div className="md:col-span-2">
          <Field
            label="Products / services the agent can talk about (optional)"
            htmlFor="products"
            error={errors.products}
          >
            <textarea
              id="products"
              name="products"
              rows={3}
              defaultValue={profile?.products ?? ""}
              className={TEXTAREA_CLASS}
            />
          </Field>
        </div>
        <div className="md:col-span-2">
          <Field label="Call objective" htmlFor="call_objective" error={errors.call_objective}>
            <textarea
              id="call_objective"
              name="call_objective"
              rows={2}
              defaultValue={profile?.call_objective ?? ""}
              placeholder="Qualify the lead and collect their requirements so the sales team can send a quotation."
              className={TEXTAREA_CLASS}
            />
          </Field>
        </div>
        <div className="md:col-span-2">
          <Field label="Opening greeting (optional)" htmlFor="greeting" error={errors.greeting}>
            <Input
              id="greeting"
              name="greeting"
              defaultValue={profile?.greeting ?? ""}
              placeholder="Leave empty for an automatic greeting"
            />
          </Field>
        </div>
      </section>

      <section aria-labelledby="fields-heading" className="flex flex-col gap-3">
        <div>
          <h2 id="fields-heading" className="text-sm font-semibold text-foreground">
            Information to collect
          </h2>
          <p className="text-sm text-muted-foreground">
            The agent works through this checklist during the call, never re-asking for something
            it already has. Required items are asked first.
          </p>
        </div>
        <ol className="flex flex-col gap-3">
          {fields.map((field, index) => (
            <li
              key={field.rowId}
              className="grid grid-cols-1 gap-2 rounded-lg border border-border p-3 md:grid-cols-[1fr_2fr_auto]"
            >
              <div>
                <label className="sr-only" htmlFor={`label-${field.rowId}`}>
                  Field {index + 1} label
                </label>
                <Input
                  id={`label-${field.rowId}`}
                  value={field.label}
                  placeholder="e.g. Budget"
                  onChange={(e) => updateField(field.rowId, { label: e.target.value })}
                />
              </div>
              <div>
                <label className="sr-only" htmlFor={`desc-${field.rowId}`}>
                  Field {index + 1} description
                </label>
                <Input
                  id={`desc-${field.rowId}`}
                  value={field.description}
                  placeholder="Hint for the agent, e.g. approximate budget range"
                  onChange={(e) => updateField(field.rowId, { description: e.target.value })}
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1.5 text-sm text-foreground">
                  <input
                    type="checkbox"
                    checked={field.required}
                    onChange={(e) => updateField(field.rowId, { required: e.target.checked })}
                  />
                  Required
                </label>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label={`Move field ${index + 1} up`}
                  onClick={() => moveField(index, -1)}
                  disabled={index === 0}
                >
                  ↑
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label={`Move field ${index + 1} down`}
                  onClick={() => moveField(index, 1)}
                  disabled={index === fields.length - 1}
                >
                  ↓
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label={`Remove field ${index + 1}`}
                  onClick={() => setFields((rows) => rows.filter((r) => r.rowId !== field.rowId))}
                >
                  ✕
                </Button>
              </div>
            </li>
          ))}
        </ol>
        {errors.fields ? (
          <p role="alert" className="text-sm text-danger">
            {errors.fields}
          </p>
        ) : null}
        <div>
          <Button type="button" variant="secondary" onClick={() => setFields((r) => [...r, blankRow()])}>
            Add field
          </Button>
        </div>
      </section>

      <label className="flex items-center gap-2 text-sm text-foreground">
        <input
          type="checkbox"
          checked={isDefault}
          disabled={profile?.is_default}
          onChange={(e) => setIsDefault(e.target.checked)}
        />
        Default profile (used for customers without a profile, and for inbound calls)
      </label>

      {formError ? (
        <p role="alert" className="text-sm text-danger">
          {formError}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={() => router.push("/profiles")}>
          Cancel
        </Button>
        <Button type="submit" disabled={isPending}>
          {isPending ? "Saving…" : profile ? "Save profile" : "Create profile"}
        </Button>
      </div>
    </form>
  );
}
