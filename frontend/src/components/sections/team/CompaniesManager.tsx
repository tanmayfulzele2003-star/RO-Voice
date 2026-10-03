"use client";

import { useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { apiClient } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/formatters";
import type { PlatformOrganization } from "@/types/api";
import { ActionNote } from "../setup/ActionNote";
import { useAction } from "../setup/useAction";
import { InviteLink } from "./InviteLink";

export function CompaniesManager({ orgs, myOrgId }: { orgs: PlatformOrganization[]; myOrgId: string }) {
  const create = useAction();
  const rows = useAction();
  const [link, setLink] = useState<{ token: string; company: string } | null>(null);

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const name = String(data.get("name") ?? "").trim();
    const limit = String(data.get("limit") ?? "").trim();
    if (!name) return create.setMessage({ ok: false, text: "Enter the company's name." });
    create.run(async () => {
      const result = await apiClient.createPlatformOrganization(name, limit ? Number(limit) : null);
      setLink({ token: result.owner_invite.token, company: name });
      form.reset();
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <h2 className="text-base font-semibold text-foreground">Add a company</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Creates an empty company and a link for its owner. They set up their own Twilio account,
          business profiles and team; their data is invisible to every other company.
        </p>
        <form onSubmit={handleCreate} noValidate className="flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1">
            <Field label="Company name" htmlFor="org-name">
              <Input id="org-name" name="name" placeholder="Sunrise Solar Pvt Ltd" />
            </Field>
          </div>
          <Field label="Calls at once (optional)" htmlFor="org-limit">
            <Input id="org-limit" name="limit" type="number" min={1} max={500} placeholder="No limit" />
          </Field>
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Create company"}
          </Button>
        </form>
        <div className="mt-4 flex flex-col gap-2">
          {link ? <InviteLink token={link.token} label={`Owner link for ${link.company}`} /> : null}
          <ActionNote message={create.message} />
        </div>
      </Card>

      <Table>
        <THead>
          <TR>
            <TH>Company</TH>
            <TH>Users</TH>
            <TH>Calls</TH>
            <TH>Call limit</TH>
            <TH>Status</TH>
            <TH>Created</TH>
            <TH>
              <span className="sr-only">Actions</span>
            </TH>
          </TR>
        </THead>
        <TBody>
          {orgs.map((org) => (
            <TR key={org.id}>
              <TD>
                <span className="font-medium text-foreground">{org.name}</span>
                {org.id === myOrgId ? <span className="text-muted-foreground"> (yours)</span> : null}
              </TD>
              <TD>{org.users}</TD>
              <TD>{org.calls}</TD>
              <TD>{org.max_concurrent_calls ?? "—"}</TD>
              <TD>{org.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="warning">Suspended</Badge>}</TD>
              <TD>{formatDateTime(org.created_at)}</TD>
              <TD>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    className="text-sm font-medium text-primary underline-offset-2 hover:underline disabled:opacity-50"
                    disabled={rows.isPending}
                    onClick={() =>
                      rows.run(async () => {
                        const invite = await apiClient.createOwnerInvite(org.id);
                        setLink({ token: invite.token, company: org.name });
                      })
                    }
                  >
                    New owner link
                  </button>
                  {org.id === myOrgId ? null : (
                    <button
                      type="button"
                      className="text-sm font-medium text-danger underline-offset-2 hover:underline disabled:opacity-50"
                      disabled={rows.isPending}
                      onClick={() => {
                        if (!org.is_active || window.confirm(`Suspend ${org.name}? Its users are signed out and calls stop.`)) {
                          rows.run(async () => {
                            await apiClient.updatePlatformOrganization(org.id, { is_active: !org.is_active });
                          });
                        }
                      }}
                    >
                      {org.is_active ? "Suspend" : "Reactivate"}
                    </button>
                  )}
                </div>
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
      <ActionNote message={rows.message} />
    </div>
  );
}
