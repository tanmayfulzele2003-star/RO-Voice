"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition, type FormEvent } from "react";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { ApiError, apiClient } from "@/lib/apiClient";
import { endSession } from "@/lib/session";
import type { BusinessProfile, Customer } from "@/types/api";

// Mirrors backend/audiocall/phone.py: strip separators, then E.164.
const normalizePhone = (raw: string) => raw.trim().replace(/[\s\-().]/g, "").replace(/^00/, "+");

const customerSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200, "Name is too long"),
  phone: z
    .string()
    .transform(normalizePhone)
    .pipe(
      z
        .string()
        .min(1, "Phone is required")
        .regex(
          /^\+[1-9]\d{7,14}$/,
          "Use international format: + country code + number, e.g. +919876543210",
        ),
    ),
  company: z.string().trim().max(200, "Company name is too long").optional(),
  purpose: z.string().trim().max(200, "Purpose is too long").optional(),
  product: z.string().trim().max(200, "Product is too long").optional(),
  profile_id: z.string().optional(),
});

const SELECT_CLASS =
  "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

interface CustomerFormProps {
  mode: "create" | "edit";
  customer?: Customer;
  profiles: BusinessProfile[];
  onSuccess?: () => void;
}

export function CustomerForm({ mode, customer, profiles, onSuccess }: CustomerFormProps) {
  const router = useRouter();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const formData = new FormData(event.currentTarget);
    const result = customerSchema.safeParse({
      name: String(formData.get("name") ?? ""),
      phone: String(formData.get("phone") ?? ""),
      company: String(formData.get("company") ?? ""),
      purpose: String(formData.get("purpose") ?? ""),
      product: String(formData.get("product") ?? ""),
      profile_id: String(formData.get("profile_id") ?? ""),
    });

    if (!result.success) {
      const fieldErrors: Record<string, string> = {};
      for (const issue of result.error.issues) {
        const key = issue.path[0];
        if (typeof key === "string") fieldErrors[key] = issue.message;
      }
      setErrors(fieldErrors);
      return;
    }
    setErrors({});

    const input = {
      name: result.data.name,
      phone: result.data.phone,
      company: result.data.company || null,
      purpose: result.data.purpose || null,
      product: result.data.product || null,
      profile_id: result.data.profile_id || null,
    };

    startTransition(async () => {
      try {
        if (mode === "create") {
          await apiClient.createCustomer(input);
        } else if (customer) {
          await apiClient.updateCustomer(customer.id, input);
        }
        router.refresh();
        onSuccess?.();
        if (mode === "edit") {
          router.push("/customers");
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          endSession();
          return;
        }
        setFormError(err instanceof ApiError ? err.message : "Unexpected error. Please try again.");
      }
    });
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <Field label="Full name" htmlFor="name" error={errors.name}>
        <Input
          id="name"
          name="name"
          defaultValue={customer?.name}
          required
          aria-invalid={Boolean(errors.name)}
        />
      </Field>
      <Field label="Phone (with country code)" htmlFor="phone" error={errors.phone}>
        <Input
          id="phone"
          name="phone"
          type="tel"
          defaultValue={customer?.phone}
          placeholder="+919876543210"
          required
          aria-invalid={Boolean(errors.phone)}
        />
      </Field>
      <Field label="Company (optional)" htmlFor="company" error={errors.company}>
        <Input id="company" name="company" defaultValue={customer?.company ?? ""} />
      </Field>
      <Field label="Business profile" htmlFor="profile_id" error={errors.profile_id}>
        <select
          id="profile_id"
          name="profile_id"
          defaultValue={customer?.profile_id ?? ""}
          className={SELECT_CLASS}
        >
          <option value="">
            Default ({profiles.find((p) => p.is_default)?.name ?? "default profile"})
          </option>
          {profiles
            .filter((p) => !p.is_default)
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
        </select>
      </Field>
      <Field label="Purpose of call (optional)" htmlFor="purpose" error={errors.purpose}>
        <Input
          id="purpose"
          name="purpose"
          defaultValue={customer?.purpose ?? ""}
          placeholder="Product enquiry"
        />
      </Field>
      <Field label="Product of interest (optional)" htmlFor="product" error={errors.product}>
        <Input
          id="product"
          name="product"
          defaultValue={customer?.product ?? ""}
          placeholder="Commercial RO System"
        />
      </Field>
      {formError ? (
        <p role="alert" className="text-sm text-danger">
          {formError}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button type="submit" disabled={isPending}>
          {isPending ? "Saving…" : mode === "create" ? "Add customer" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}
