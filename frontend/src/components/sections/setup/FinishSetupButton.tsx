"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { apiClient } from "@/lib/apiClient";
import { ActionNote } from "./ActionNote";
import { useAction } from "./useAction";

export function FinishSetupButton({ complete }: { complete: boolean }) {
  const router = useRouter();
  const { run, isPending, message } = useAction();
  return (
    <div className="flex flex-col items-start gap-2">
      <Button
        variant={complete ? "primary" : "secondary"}
        disabled={isPending}
        onClick={() =>
          run(
            async () => {
              await apiClient.setSetupFlag("setup_completed", true);
              router.push("/");
            },
            { refresh: false },
          )
        }
      >
        {complete ? "Finish setup" : "I'll finish later — hide the setup reminder"}
      </Button>
      <ActionNote message={message} />
    </div>
  );
}
