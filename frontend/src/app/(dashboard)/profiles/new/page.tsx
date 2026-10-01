import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { ProfileForm } from "@/components/sections/ProfileForm";
import { Card } from "@/components/ui/Card";

export const metadata: Metadata = {
  title: "New business profile",
};

export default function NewProfilePage() {
  return (
    <PageShell
      title="New business profile"
      description="Set up the calling agent for another business."
    >
      <Card className="max-w-4xl">
        <ProfileForm />
      </Card>
    </PageShell>
  );
}
