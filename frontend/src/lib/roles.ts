import type { Role } from "@/types/api";

/** What each role can do — mirrors backend/audiocall/services/team_service.py. */
export const ROLE_INFO: Record<Role, { label: string; description: string }> = {
  viewer: { label: "Viewer", description: "Sees calls, customers and results" },
  member: { label: "Member", description: "Also adds customers, places calls, runs campaigns" },
  admin: { label: "Admin", description: "Also manages profiles, numbers, settings and the team" },
  owner: { label: "Owner", description: "Everything, including other admins and owners" },
};

export const ROLES: Role[] = ["viewer", "member", "admin", "owner"];

export const ROLE_RANK: Record<Role, number> = { viewer: 0, member: 1, admin: 2, owner: 3 };
