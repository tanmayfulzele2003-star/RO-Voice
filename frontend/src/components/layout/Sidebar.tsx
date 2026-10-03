"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { apiClient } from "@/lib/apiClient";
import { endSession } from "@/lib/session";
import { ROLE_INFO, ROLE_RANK } from "@/lib/roles";
import type { Me, Role } from "@/types/api";

type NavItem = { href: string; label: string; minRole?: Role; platformOnly?: boolean };

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview" },
  { href: "/customers", label: "Customers" },
  { href: "/calls", label: "Calls" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/numbers", label: "Phone numbers" },
  { href: "/profiles", label: "Business profiles" },
  { href: "/team", label: "Team", minRole: "admin" },
  { href: "/settings", label: "Settings", minRole: "admin" },
  { href: "/platform", label: "Companies", platformOnly: true },
  { href: "/account", label: "Account" },
];

export function Sidebar({ me }: { me: Me | null }) {
  const pathname = usePathname();
  const router = useRouter();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  async function handleLogout() {
    setIsLoggingOut(true);
    try {
      await apiClient.logout();
    } finally {
      endSession();
      router.refresh();
    }
  }

  return (
    <nav
      aria-label="Main navigation"
      className="flex shrink-0 flex-col gap-1 border-border p-4 md:w-56 md:border-r"
    >
      <div className="mb-3 px-2">
        <p className="text-sm font-semibold tracking-tight text-foreground">
          {me?.organization.name ?? "AI Calling Agent"}
        </p>
        {me ? (
          <p className="text-xs text-muted-foreground">
            {me.username} · {ROLE_INFO[me.role].label}
            {me.is_platform_admin ? " · Platform admin" : ""}
          </p>
        ) : null}
      </div>
      {NAV_ITEMS.filter(
        (item) =>
          (!item.minRole || (me && ROLE_RANK[me.role] >= ROLE_RANK[item.minRole])) &&
          (!item.platformOnly || me?.is_platform_admin),
      ).map((item) => {
        const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
              isActive
                ? "bg-primary text-primary-foreground"
                : "text-foreground hover:bg-muted"
            }`}
          >
            {item.label}
          </Link>
        );
      })}

      <button
        type="button"
        onClick={handleLogout}
        disabled={isLoggingOut}
        className="mt-auto rounded-lg px-3 py-2 text-left text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-50 md:mt-6"
      >
        {isLoggingOut ? "Signing out…" : "Sign out"}
      </button>
    </nav>
  );
}
