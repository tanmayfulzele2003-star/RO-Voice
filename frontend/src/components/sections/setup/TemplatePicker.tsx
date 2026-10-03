"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { apiClient } from "@/lib/apiClient";
import type { ProfileTemplate } from "@/types/api";
import { ActionNote } from "./ActionNote";
import { useAction } from "./useAction";

const E164 = /^\+[1-9]\d{7,14}$/;

export function TemplatePicker({ templates }: { templates: ProfileTemplate[] }) {
  const { run, isPending, message, setMessage } = useAction();
  const [selectedId, setSelectedId] = useState(templates[0]?.id ?? "");
  const selected = templates.find((t) => t.id === selectedId);

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    const name = String(data.get("business_name") ?? "").trim();
    const agentName = String(data.get("agent_name") ?? "").trim();
    const transfer = String(data.get("transfer_number") ?? "").replace(/[\s\-().]/g, "");
    if (!name || !agentName) {
      setMessage({ ok: false, text: "Enter your business name and the agent's name." });
      return;
    }
    if (transfer && !E164.test(transfer)) {
      setMessage({ ok: false, text: "Transfer number: use international format, e.g. +919876543210." });
      return;
    }
    run(async () => {
      await apiClient.createProfile({
        ...selected.profile,
        name,
        agent_name: agentName,
        transfer_number: transfer || null,
        is_default: data.get("is_default") === "on",
      });
      await apiClient.setSetupFlag("setup_profile", true);
      return { ok: true, text: `${name} is set up. Fine-tune its questions any time under Business profiles.` };
    });
  }

  return (
    <form onSubmit={handleCreate} noValidate className="flex flex-col gap-4">
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-foreground">Start from your industry</legend>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {templates.map((t) => (
            <label
              key={t.id}
              className={`flex cursor-pointer flex-col gap-1 rounded-lg border p-3 text-sm ${
                t.id === selectedId ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50"
              }`}
            >
              <span className="flex items-center gap-2 font-medium text-foreground">
                <input
                  type="radio"
                  name="template"
                  value={t.id}
                  checked={t.id === selectedId}
                  onChange={() => setSelectedId(t.id)}
                />
                {t.title}
              </span>
              <span className="text-muted-foreground">{t.summary}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {selected ? (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3" key={selected.id}>
            <Field label="Business name" htmlFor="business_name">
              <Input id="business_name" name="business_name" defaultValue={selected.profile.name} />
            </Field>
            <Field label="Agent's name" htmlFor="agent_name">
              <Input id="agent_name" name="agent_name" defaultValue={selected.profile.agent_name} />
            </Field>
            <Field label="Transfer to a person (optional)" htmlFor="transfer_number">
              <Input id="transfer_number" name="transfer_number" type="tel" placeholder="+919876543210" />
            </Field>
          </div>
          <p className="text-sm text-muted-foreground">
            The agent will ask about:{" "}
            <span className="text-foreground">{selected.profile.fields.map((f) => f.label).join(", ")}</span>
          </p>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input type="checkbox" name="is_default" defaultChecked />
            Use for all customers and inbound calls by default
          </label>
        </>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={isPending || !selected}>
          {isPending ? "Creating…" : "Create my business profile"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={isPending}
          onClick={() =>
            run(async () => {
              await apiClient.setSetupFlag("setup_profile", true);
              return { ok: true, text: "Keeping your existing profiles." };
            })
          }
        >
          Skip — keep existing profiles
        </Button>
      </div>
      <ActionNote message={message} />
    </form>
  );
}
