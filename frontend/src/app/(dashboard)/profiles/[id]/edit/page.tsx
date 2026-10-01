import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/layout/PageShell";
import { ProfileForm } from "@/components/sections/ProfileForm";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { BusinessProfile } from "@/types/api";

export const metadata: Metadata = {
  title: "Edit business profile",
};

export default async function EditProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let profile: BusinessProfile | null = null;
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    profile = await apiClient.getProfile(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load profile.";
  }

  return (
    <PageShell title="Edit business profile" description={profile?.name}>
      {loadError || !profile ? (
        <ErrorState message={loadError ?? "Failed to load profile."} />
      ) : (
        <Card className="max-w-4xl">
          <ProfileForm profile={profile} />
        </Card>
      )}
    </PageShell>
  );
}
