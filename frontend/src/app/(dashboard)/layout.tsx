import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-1 flex-col md:flex-row">
      <Sidebar />
      <main id="main-content" className="flex flex-1 flex-col">
        {children}
      </main>
    </div>
  );
}
