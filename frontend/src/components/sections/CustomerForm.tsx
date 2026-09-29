"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition, type FormEvent } from "react";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { ApiError, apiClient } from "@/lib/apiClient";
import type { Customer } from "@/types/api";

const customerSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200, "Name is too long"),
  phone: z.string().trim().min(1, "Phone is required").max(32, "Phone is too long"),
  company: z.string().trim().max(200, "Company name is too long").optional(),
});

interface CustomerFormProps {
  mode: "create" | "edit";
  customer?: Customer;
  onSuccess?: () => void;
}

export function CustomerForm({ mode, customer, onSuccess }: CustomerFormProps) {
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

    const company = result.data.company ? result.data.company : null;

    startTransition(async () => {
      try {
        if (mode === "create") {
          await apiClient.createCustomer({
            name: result.data.name,
            phone: result.data.phone,
            company,
          });
        } else if (customer) {
          await apiClient.updateCustomer(customer.id, {
            name: result.data.name,
            phone: result.data.phone,
            company,
          });
        }
        router.refresh();
        onSuccess?.();
        if (mode === "edit") {
          router.push("/customers");
        }
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
      <Field label="Phone (E.164 format)" htmlFor="phone" error={errors.phone}>
        <Input
          id="phone"
          name="phone"
          defaultValue={customer?.phone}
          placeholder="+15551234567"
          required
          aria-invalid={Boolean(errors.phone)}
        />
      </Field>
      <Field label="Company (optional)" htmlFor="company" error={errors.company}>
        <Input id="company" name="company" defaultValue={customer?.company ?? ""} />
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
