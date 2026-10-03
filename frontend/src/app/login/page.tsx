import type { Metadata } from "next";
import { Card } from "@/components/ui/Card";
import { LoginForm } from "@/components/sections/LoginForm";
import { makeApiClient } from "@/lib/apiClient";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to the AI Calling Agent admin dashboard.",
};

export default async function LoginPage() {
  // A brand-new install has no admin to sign in as yet.
  const needsAdmin = await makeApiClient()
    .getSetupStatus()
    .then((s) => s.needs_admin)
    .catch(() => false);
  return (
    <div id="main-content" className="flex flex-1 items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-lg font-semibold text-foreground">AI Calling Agent</h1>
        {needsAdmin ? (
          <div className="flex flex-col gap-2 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">No admin account yet</p>
            <p>
              Open the setup link printed in the server log when it started. It looks like{" "}
              <code>/setup?token=…</code>. With Docker: <code>docker compose logs backend</code>.
            </p>
          </div>
        ) : (
          <>
            <p className="mb-5 text-sm text-muted-foreground">Sign in to continue.</p>
            <LoginForm />
          </>
        )}
      </Card>
    </div>
  );
}
