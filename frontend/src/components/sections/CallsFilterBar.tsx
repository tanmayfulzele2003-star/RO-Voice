"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

const STATUS_OPTIONS = [
  "queued",
  "ringing",
  "in_progress",
  "completed",
  "failed",
  "no_answer",
  "disconnected",
] as const;

const LEAD_STATUS_OPTIONS = ["interested", "not_interested", "uncertain"] as const;

const OUTCOME_OPTIONS: { value: string; label: string }[] = [
  { value: "qualified", label: "Qualified lead" },
  { value: "not_interested", label: "Not interested" },
  { value: "callback", label: "Call back" },
  { value: "transferred", label: "Transferred to a person" },
  { value: "incomplete", label: "Incomplete" },
  { value: "no_answer", label: "No answer" },
  { value: "no_conversation", label: "No conversation" },
  { value: "failed", label: "Failed" },
];

const SELECT_CLASS =
  "rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

function FilterSelect({
  id,
  label,
  value,
  onChange,
  options,
  allLabel,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  allLabel: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-foreground">
        {label}
      </label>
      <select
        id={id}
        defaultValue={value}
        onChange={(event) => onChange(event.target.value)}
        className={SELECT_CLASS}
      >
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

const SEARCH_DEBOUNCE_MS = 400;

export function CallsFilterBar({ profiles }: { profiles: { id: string; name: string }[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [customerName, setCustomerName] = useState(searchParams.get("customer_name") ?? "");

  function updateParams(updates: Record<string, string>) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(updates)) {
      if (value) {
        params.set(key, value);
      } else {
        params.delete(key);
      }
    }
    params.delete("offset"); // any filter change resets pagination
    router.push(params.size > 0 ? `${pathname}?${params.toString()}` : pathname);
  }

  // Debounce the free-text search so we don't navigate on every keystroke.
  useEffect(() => {
    const currentValue = searchParams.get("customer_name") ?? "";
    if (customerName === currentValue) return;
    const handle = setTimeout(() => {
      updateParams({ customer_name: customerName });
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
    // Only re-run when the debounced value changes, not on every searchParams
    // change (that would fight with the debounce timer).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerName]);

  return (
    <form
      role="search"
      aria-label="Filter calls"
      className="flex flex-wrap items-end gap-3"
      onSubmit={(event) => event.preventDefault()}
    >
      <div>
        <label htmlFor="customer_name" className="mb-1.5 block text-sm font-medium text-foreground">
          Search customer
        </label>
        <input
          id="customer_name"
          type="search"
          value={customerName}
          onChange={(event) => setCustomerName(event.target.value)}
          placeholder="Customer name…"
          className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        />
      </div>

      <div>
        <label htmlFor="status" className="mb-1.5 block text-sm font-medium text-foreground">
          Status
        </label>
        <select
          id="status"
          defaultValue={searchParams.get("status") ?? ""}
          onChange={(event) => updateParams({ status: event.target.value })}
          className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option.replace("_", " ")}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="lead_status" className="mb-1.5 block text-sm font-medium text-foreground">
          Lead status
        </label>
        <select
          id="lead_status"
          defaultValue={searchParams.get("lead_status") ?? ""}
          onChange={(event) => updateParams({ lead_status: event.target.value })}
          className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <option value="">All leads</option>
          {LEAD_STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option.replace("_", " ")}
            </option>
          ))}
        </select>
      </div>

      <FilterSelect
        id="outcome"
        label="Outcome"
        value={searchParams.get("outcome") ?? ""}
        onChange={(value) => updateParams({ outcome: value })}
        options={OUTCOME_OPTIONS}
        allLabel="All outcomes"
      />

      <FilterSelect
        id="follow_up"
        label="Follow-up"
        value={searchParams.get("follow_up") ?? ""}
        onChange={(value) => updateParams({ follow_up: value })}
        options={[
          { value: "true", label: "Required" },
          { value: "false", label: "Not required" },
        ]}
        allLabel="Any"
      />

      <FilterSelect
        id="channel"
        label="Channel"
        value={searchParams.get("channel") ?? ""}
        onChange={(value) => updateParams({ channel: value })}
        options={[
          { value: "phone", label: "Phone" },
          { value: "browser", label: "Browser" },
        ]}
        allLabel="All channels"
      />

      <FilterSelect
        id="direction"
        label="Direction"
        value={searchParams.get("direction") ?? ""}
        onChange={(value) => updateParams({ direction: value })}
        options={[
          { value: "outbound", label: "Outbound" },
          { value: "inbound", label: "Inbound" },
        ]}
        allLabel="Both directions"
      />

      {profiles.length > 1 ? (
        <FilterSelect
          id="profile_id"
          label="Business"
          value={searchParams.get("profile_id") ?? ""}
          onChange={(value) => updateParams({ profile_id: value })}
          options={profiles.map((p) => ({ value: p.id, label: p.name }))}
          allLabel="All businesses"
        />
      ) : null}

      <div>
        <label htmlFor="date_from" className="mb-1.5 block text-sm font-medium text-foreground">
          From
        </label>
        <input
          id="date_from"
          type="date"
          defaultValue={(searchParams.get("date_from") ?? "").slice(0, 10)}
          onChange={(event) =>
            updateParams({ date_from: event.target.value ? `${event.target.value}T00:00:00Z` : "" })
          }
          className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        />
      </div>

      <div>
        <label htmlFor="date_to" className="mb-1.5 block text-sm font-medium text-foreground">
          To
        </label>
        <input
          id="date_to"
          type="date"
          defaultValue={(searchParams.get("date_to") ?? "").slice(0, 10)}
          onChange={(event) =>
            updateParams({ date_to: event.target.value ? `${event.target.value}T23:59:59Z` : "" })
          }
          className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        />
      </div>
    </form>
  );
}
