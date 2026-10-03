"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { ApiError, apiClient } from "@/lib/apiClient";

export function JoinForm({ token, firstOwner }: { token: string; firstOwner: boolean }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const data = new FormData(event.currentTarget);
    const username = String(data.get("username") ?? "").trim();
    const password = String(data.get("password") ?? "");
    if (username.length < 3) return setError("Choose a username of at least 3 characters.");
    if (password.length < 8) return setError("Use a password of at least 8 characters.");
    if (password !== String(data.get("confirm") ?? "")) return setError("The passwords don't match.");
    startTransition(async () => {
      try {
        await apiClient.acceptInvite(token, username, password);
        router.push(firstOwner ? "/get-started" : "/");
        router.refresh();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Unexpected error. Please try again.");
      }
    });
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <Field label="Username" htmlFor="username">
        <Input id="username" name="username" autoComplete="username" />
      </Field>
      <Field label="Password" htmlFor="password">
        <Input id="password" name="password" type="password" autoComplete="new-password" />
      </Field>
      <Field label="Confirm password" htmlFor="confirm">
        <Input id="confirm" name="confirm" type="password" autoComplete="new-password" />
      </Field>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
      <Button type="submit" disabled={isPending}>
        {isPending ? "Creating account…" : "Create my account"}
      </Button>
    </form>
  );
}
