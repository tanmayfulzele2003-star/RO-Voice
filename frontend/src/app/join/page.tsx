import Link from "next/link";
import type { Metadata } from "next";
import { JoinForm } from "@/components/sections/team/JoinForm";
import { Card } from "@/components/ui/Card";
import { makeApiClient } from "@/lib/apiClient";
import type { JoinInfo } from "@/types/api";

export const metadata: Metadata = {
  title: "Join",
  description: "Accept an invitation to the AI Calling Agent.",
};

const ROLE_TEXT = {
  viewer: "a viewer (see calls and results)",
  member: "a member (add customers and place calls)",
  admin: "an admin (manage the agent, numbers and team)",
  owner: "an owner",
} as const;

export default async function JoinPage({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token = "" } = await searchParams;
  let info: JoinInfo | null = null;
  if (token) {
    info = await makeApiClient()
      .describeInvite(token)
      .catch(() => null);
  }

  return (
    <div id="main-content" className="flex flex-1 items-center justify-center p-4">
      <Card className="w-full max-w-md">
        {info ? (
          <>
            <h1 className="mb-1 text-lg font-semibold text-foreground">Join {info.organization}</h1>
            <p className="mb-5 text-sm text-muted-foreground">
              You&apos;re invited as {ROLE_TEXT[info.role]}. Choose your sign-in details.
            </p>
            <JoinForm token={token} firstOwner={info.role === "owner"} />
          </>
        ) : (
          <>
            <h1 className="mb-1 text-lg font-semibold text-foreground">This invite can&apos;t be used</h1>
            <p className="text-sm text-muted-foreground">
              The link is invalid, was already used, or has expired. Ask whoever invited you for a new
              one. Already have an account?{" "}
              <Link href="/login" className="font-medium text-primary underline-offset-2 hover:underline">
                Sign in
              </Link>
              .
            </p>
          </>
        )}
      </Card>
    </div>
  );
}
