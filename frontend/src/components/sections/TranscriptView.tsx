import { formatDateTime } from "@/lib/formatters";
import type { ConversationMessage } from "@/types/api";

export function TranscriptView({ messages }: { messages: ConversationMessage[] }) {
  if (messages.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No transcript was captured for this call.</p>
    );
  }

  return (
    <ol className="flex flex-col gap-3">
      {messages.map((message, index) => {
        const isCustomer = message.speaker === "customer";
        return (
          <li key={index} className={`flex ${isCustomer ? "justify-start" : "justify-end"}`}>
            <div
              className={`max-w-[85%] rounded-lg px-4 py-2 text-sm ${
                isCustomer ? "bg-muted text-foreground" : "bg-primary text-primary-foreground"
              }`}
            >
              <p className="mb-1 text-xs font-medium opacity-70">
                {isCustomer ? "Customer" : "AI"} · {formatDateTime(message.timestamp)}
              </p>
              <p className="whitespace-pre-wrap">{message.message}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
