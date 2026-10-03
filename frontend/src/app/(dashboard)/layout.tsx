import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { Me } from "@/types/api";

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  let me: Me | null = null;
  try {
    me = await (await getServerApiClient()).getMe();
  } catch (err) {
    redirectIfUnauthenticated(err);
  }
  return (
    <div className="flex flex-1 flex-col md:flex-row">
      <Sidebar me={me} />
      <main id="main-content" className="flex flex-1 flex-col">
        {children}
      </main>
    </div>
  );
}
