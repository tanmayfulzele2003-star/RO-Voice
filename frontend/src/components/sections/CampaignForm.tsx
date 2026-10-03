"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { ApiError, apiClient } from "@/lib/apiClient";
import { formatPhone } from "@/lib/formatters";
import type { Customer } from "@/types/api";

const SELECT_CLASS =
  "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

function intInRange(raw: FormDataEntryValue | null, min: number, max: number): number | null {
  const value = Number(raw);
  return Number.isInteger(value) && value >= min && value <= max ? value : null;
}

export function CampaignForm({
  customers,
  profiles,
}: {
  customers: Customer[];
  profiles: { id: string; name: string }[];
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return customers;
    return customers.filter(
      (c) =>
        c.name.toLowerCase().includes(term) ||
        c.phone.includes(term) ||
        (c.company ?? "").toLowerCase().includes(term),
    );
  }, [customers, search]);
  const allVisibleSelected = visible.length > 0 && visible.every((c) => selected.has(c.id));

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleVisible() {
    setSelected((current) => {
      const next = new Set(current);
      for (const c of visible) {
        if (allVisibleSelected) next.delete(c.id);
        else next.add(c.id);
      }
      return next;
    });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const data = new FormData(event.currentTarget);
    const name = String(data.get("name") ?? "").trim();
    const maxConcurrent = intInRange(data.get("max_concurrent"), 1, 50);
    const maxAttempts = intInRange(data.get("max_attempts"), 1, 5);
    const retryDelay = intInRange(data.get("retry_delay_minutes"), 1, 1440);

    const fieldErrors: Record<string, string> = {};
    if (!name) fieldErrors.name = "Give the campaign a name.";
    if (maxConcurrent == null) fieldErrors.max_concurrent = "A whole number from 1 to 50.";
    if (maxAttempts == null) fieldErrors.max_attempts = "A whole number from 1 to 5.";
    if (retryDelay == null) fieldErrors.retry_delay_minutes = "A whole number of minutes, 1–1440.";
    if (selected.size === 0) fieldErrors.customers = "Select at least one customer to call.";
    setErrors(fieldErrors);
    if (Object.keys(fieldErrors).length > 0) return;

    startTransition(async () => {
      try {
        const campaign = await apiClient.createCampaign({
          name,
          profile_id: String(data.get("profile_id") ?? "") || null,
          customer_ids: [...selected],
          max_concurrent: maxConcurrent!,
          max_attempts: maxAttempts!,
          retry_delay_minutes: retryDelay!,
        });
        router.push(`/campaigns/${campaign.id}`);
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
        <Field label="Campaign name" htmlFor="name" error={errors.name}>
          <Input id="name" name="name" placeholder="Diwali offer follow-ups" />
        </Field>
        <Field label="Business profile" htmlFor="profile_id">
          <select id="profile_id" name="profile_id" defaultValue="" className={SELECT_CLASS}>
            <option value="">Each customer&apos;s own profile</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Calls at once" htmlFor="max_concurrent" error={errors.max_concurrent}>
          <Input id="max_concurrent" name="max_concurrent" type="number" min={1} max={50} defaultValue={3} />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Attempts per customer" htmlFor="max_attempts" error={errors.max_attempts}>
            <Input id="max_attempts" name="max_attempts" type="number" min={1} max={5} defaultValue={2} />
          </Field>
          <Field label="Retry after (minutes)" htmlFor="retry_delay_minutes" error={errors.retry_delay_minutes}>
            <Input
              id="retry_delay_minutes"
              name="retry_delay_minutes"
              type="number"
              min={1}
              max={1440}
              defaultValue={30}
            />
          </Field>
        </div>
        <p className="text-sm text-muted-foreground md:col-span-2">
          The server&apos;s overall line limit (<code>MAX_CONCURRENT_CALLS</code>) still applies,
          shared with other campaigns, manual calls and inbound calls. Only unanswered or failed
          calls are retried.
        </p>
      </section>

      <section aria-labelledby="customers-heading" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="customers-heading" className="text-sm font-semibold text-foreground">
              Customers to call
            </h2>
            <p className="text-sm text-muted-foreground" aria-live="polite">
              {selected.size} of {customers.length} selected
            </p>
          </div>
          <div className="flex items-end gap-2">
            <div>
              <label htmlFor="customer-search" className="sr-only">
                Search customers
              </label>
              <Input
                id="customer-search"
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search name, phone, company…"
              />
            </div>
            <Button type="button" variant="secondary" onClick={toggleVisible} disabled={visible.length === 0}>
              {allVisibleSelected ? "Clear these" : search ? "Select matches" : "Select all"}
            </Button>
          </div>
        </div>
        {customers.length === 0 ? (
          <p className="text-sm text-muted-foreground">Add customers first, then create a campaign.</p>
        ) : (
          <ul className="max-h-96 divide-y divide-border overflow-y-auto rounded-lg border border-border">
            {visible.map((c) => (
              <li key={c.id}>
                <label className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-muted/50">
                  <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
                  <span className="flex-1 text-sm text-foreground">
                    {c.name}
                    {c.company ? <span className="text-muted-foreground"> · {c.company}</span> : null}
                  </span>
                  <span className="text-sm text-muted-foreground">{formatPhone(c.phone)}</span>
                </label>
              </li>
            ))}
            {visible.length === 0 ? (
              <li className="px-3 py-4 text-sm text-muted-foreground">No customers match.</li>
            ) : null}
          </ul>
        )}
        {errors.customers ? (
          <p role="alert" className="text-sm text-danger">
            {errors.customers}
          </p>
        ) : null}
      </section>

      {formError ? (
        <p role="alert" className="text-sm text-danger">
          {formError}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={() => router.push("/campaigns")}>
          Cancel
        </Button>
        <Button type="submit" disabled={isPending}>
          {isPending ? "Creating…" : "Create campaign"}
        </Button>
      </div>
    </form>
  );
}
