"use client";

import { useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { apiClient } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/formatters";
import { ROLE_INFO, ROLES } from "@/lib/roles";
import type { Invite, Me, Role, TeamUser } from "@/types/api";
import { ActionNote } from "../setup/ActionNote";
import { useAction } from "../setup/useAction";
import { InviteLink } from "./InviteLink";

const SELECT_CLASS =
  "rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-50";


export function TeamManager({ me, users, invites }: { me: Me; users: TeamUser[]; invites: Invite[] }) {
  const userAction = useAction();
  const inviteAction = useAction();
  const [newInvite, setNewInvite] = useState<{ token: string; role: Role; note: string | null } | null>(null);
  // Admins can't hand out (or change) the owner role; owners can.
  const assignable = me.role === "owner" ? ROLES : ROLES.filter((r) => r !== "owner");

  function handleInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const role = String(data.get("role")) as Role;
    const note = String(data.get("note") ?? "").trim() || null;
    inviteAction.run(async () => {
      const created = await apiClient.createInvite(role, note);
      setNewInvite({ token: created.token, role, note });
      form.reset();
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <h2 className="text-base font-semibold text-foreground">Invite someone</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Creates a one-time link. They choose their own username and password when they open it.
        </p>
        <form onSubmit={handleInvite} noValidate className="flex flex-wrap items-end gap-3">
          <Field label="Role" htmlFor="invite-role">
            <select id="invite-role" name="role" defaultValue="member" className={SELECT_CLASS}>
              {assignable.map((r) => (
                <option key={r} value={r}>
                  {ROLE_INFO[r].label} — {ROLE_INFO[r].description}
                </option>
              ))}
            </select>
          </Field>
          <div className="min-w-56 flex-1">
            <Field label="Who it's for (optional)" htmlFor="invite-note">
              <Input id="invite-note" name="note" placeholder="ravi@yourcompany.com" />
            </Field>
          </div>
          <Button type="submit" disabled={inviteAction.isPending}>
            {inviteAction.isPending ? "Creating…" : "Create invite link"}
          </Button>
        </form>
        <div className="mt-4 flex flex-col gap-2">
          {newInvite ? (
            <InviteLink
              token={newInvite.token}
              label={`Invite link for a new ${ROLE_INFO[newInvite.role].label.toLowerCase()}${newInvite.note ? ` (${newInvite.note})` : ""}`}
            />
          ) : null}
          <ActionNote message={inviteAction.message} />
        </div>
      </Card>

      <section aria-labelledby="people-heading" className="flex flex-col gap-3">
        <h2 id="people-heading" className="text-base font-semibold text-foreground">
          People
        </h2>
        <Table>
          <THead>
            <TR>
              <TH>User</TH>
              <TH>Role</TH>
              <TH>Access</TH>
              <TH>Joined</TH>
              <TH>
                <span className="sr-only">Actions</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {users.map((u) => {
              const isMe = u.username === me.username;
              const locked = isMe || (u.role === "owner" && me.role !== "owner");
              return (
                <TR key={u.id}>
                  <TD>
                    <span className="font-medium text-foreground">{u.username}</span>
                    {isMe ? <span className="text-muted-foreground"> (you)</span> : null}
                    {u.is_platform_admin ? (
                      <span className="ml-2">
                        <Badge tone="info">Platform admin</Badge>
                      </span>
                    ) : null}
                  </TD>
                  <TD>
                    <label className="sr-only" htmlFor={`role-${u.id}`}>
                      Role for {u.username}
                    </label>
                    <select
                      id={`role-${u.id}`}
                      value={u.role}
                      disabled={locked || userAction.isPending}
                      onChange={(e) =>
                        userAction.run(async () => {
                          await apiClient.updateUser(u.id, { role: e.target.value as Role });
                        })
                      }
                      className={SELECT_CLASS}
                    >
                      {(locked ? ROLES : assignable).map((r) => (
                        <option key={r} value={r}>
                          {ROLE_INFO[r].label}
                        </option>
                      ))}
                    </select>
                  </TD>
                  <TD>
                    {u.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="warning">Disabled</Badge>}
                  </TD>
                  <TD>{formatDateTime(u.created_at)}</TD>
                  <TD>
                    {locked ? null : (
                      <div className="flex flex-wrap gap-3">
                        <button
                          type="button"
                          className="text-sm font-medium text-primary underline-offset-2 hover:underline disabled:opacity-50"
                          disabled={userAction.isPending}
                          onClick={() =>
                            userAction.run(async () => {
                              await apiClient.updateUser(u.id, { is_active: !u.is_active });
                            })
                          }
                        >
                          {u.is_active ? "Disable" : "Enable"}
                        </button>
                        <button
                          type="button"
                          className="text-sm font-medium text-danger underline-offset-2 hover:underline disabled:opacity-50"
                          disabled={userAction.isPending}
                          onClick={() => {
                            if (window.confirm(`Remove ${u.username} from the team?`)) {
                              userAction.run(async () => {
                                await apiClient.deleteUser(u.id);
                              });
                            }
                          }}
                        >
                          Remove
                        </button>
                      </div>
                    )}
                  </TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
        <ActionNote message={userAction.message} />
      </section>

      {invites.length ? (
        <section aria-labelledby="invites-heading" className="flex flex-col gap-3">
          <h2 id="invites-heading" className="text-base font-semibold text-foreground">
            Open invites
          </h2>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {invites.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 text-sm">
                <span>
                  <span className="font-medium text-foreground">{ROLE_INFO[i.role].label}</span>
                  {i.note ? <span className="text-muted-foreground"> · {i.note}</span> : null}
                  <span className="text-muted-foreground"> · expires {formatDateTime(i.expires_at)}</span>
                </span>
                <button
                  type="button"
                  className="text-sm font-medium text-danger underline-offset-2 hover:underline disabled:opacity-50"
                  disabled={inviteAction.isPending}
                  onClick={() =>
                    inviteAction.run(async () => {
                      await apiClient.revokeInvite(i.id);
                    })
                  }
                >
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
