"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, apiClient } from "@/lib/apiClient";

export function DeleteProfileButton({
  profileId,
  profileName,
}: {
  profileId: string;
  profileName: string;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  async function handleDelete() {
    if (!window.confirm(`Delete the "${profileName}" profile?`)) return;
    setError(null);
    setIsDeleting(true);
    try {
      await apiClient.deleteProfile(profileId);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete profile.");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <span className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={handleDelete}
        disabled={isDeleting}
        className="text-sm font-medium text-danger underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger disabled:opacity-50"
      >
        {isDeleting ? "Deleting…" : "Delete"}
      </button>
      {error ? (
        <span role="alert" className="text-sm text-danger">
          {error}
        </span>
      ) : null}
    </span>
  );
}
