import Link from "next/link";
import type { Metadata } from "next";
import { FirstAdminForm } from "@/components/sections/setup/FirstAdminForm";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { ApiError, makeApiClient } from "@/lib/apiClient";

export const metadata: Metadata = {
  title: "Set up",
  description: "Create the first admin account for the AI Calling Agent.",
};

export default async function SetupPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token = "" } = await searchParams;
  let needsAdmin: boolean | null = null;
  let loadError: string | null = null;
  try {
    needsAdmin = (await makeApiClient().getSetupStatus()).needs_admin;
  } catch (err) {
    loadError = err instanceof ApiError ? err.message : "Could not reach the backend.";
  }

  return (
    <div id="main-content" className="flex flex-1 items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <h1 className="mb-1 text-lg font-semibold text-foreground">Welcome to the AI Calling Agent</h1>
        {loadError ? (
          <ErrorState message={loadError} />
        ) : needsAdmin ? (
          <>
            <p className="mb-5 text-sm text-muted-foreground">
              Create the admin account. Next you&apos;ll connect Twilio and Gemini and make a
              test call — about five minutes.
            </p>
            <FirstAdminForm token={token} />
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Setup is already done.{" "}
            <Link href="/login" className="font-medium text-primary underline-offset-2 hover:underline">
              Sign in
            </Link>
            .
          </p>
        )}
      </Card>
    </div>
  );
}
