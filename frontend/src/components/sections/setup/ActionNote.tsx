import type { ActionMessage } from "./useAction";

export function ActionNote({ message }: { message: ActionMessage | null }) {
  if (!message) return null;
  return (
    <p
      role={message.ok ? "status" : "alert"}
      className={`text-sm ${message.ok ? "text-success" : "text-danger"}`}
    >
      {message.ok ? "✓ " : ""}
      {message.text}
    </p>
  );
}
