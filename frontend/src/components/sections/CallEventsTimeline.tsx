import { formatDateTime, formatEventType, isErrorEvent } from "@/lib/formatters";
import type { CallEvent } from "@/types/api";

export function CallEventsTimeline({ events }: { events: CallEvent[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">No events were recorded for this call.</p>;
  }
  return (
    <ol className="flex flex-col gap-2">
      {events.map((event, index) => {
        const isError = isErrorEvent(event.event_type);
        return (
          <li key={index} className="flex gap-3 text-sm">
            <span
              aria-hidden
              className={`mt-1.5 inline-block size-2 shrink-0 rounded-full ${
                isError ? "bg-danger" : "bg-muted-foreground"
              }`}
            />
            <div className="min-w-0">
              <p className={`font-medium ${isError ? "text-danger" : "text-foreground"}`}>
                {formatEventType(event.event_type)}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {formatDateTime(event.created_at)}
                </span>
              </p>
              {event.detail ? (
                <p className="break-words text-muted-foreground">{event.detail}</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
