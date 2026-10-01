import type { Metadata } from "next";
import { Card } from "@/components/ui/Card";
import { LoginForm } from "@/components/sections/LoginForm";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to the AI Calling Agent admin dashboard.",
};

export default function LoginPage() {
  return (
    <div id="main-content" className="flex flex-1 items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-lg font-semibold text-foreground">AI Calling Agent</h1>
        <p className="mb-5 text-sm text-muted-foreground">Sign in to continue.</p>
        <LoginForm />
      </Card>
    </div>
  );
}
