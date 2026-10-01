export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  if (minutes === 0) return `${remaining}s`;
  return `${minutes}m ${remaining}s`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// E.164 phone numbers vary widely in length/grouping by country — guessing a
// format would misrender numbers we don't recognize, so this is intentionally
// a pass-through kept as its own function so a real format can slot in later.
export function formatPhone(phone: string): string {
  return phone;
}

export function formatStatusLabel(status: string): string {
  return status
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

const EVENT_LABELS: Record<string, string> = {
  call_initiated: "Call initiated",
  call_status: "Provider status",
  provider_error: "Calling provider error",
  invalid_number: "Invalid phone number",
  stream_started: "Conversation started",
  stream_ended: "Conversation ended",
  customer_silence: "Customer silent — agent checked in",
  silence_timeout: "No response — call ended",
  interruption: "Customer interrupted",
  speech_not_recognized: "Speech not recognised",
  customer_hung_up: "Customer hung up",
  ai_error: "AI failure",
  field_collected: "Information collected",
  agent_end_call: "Agent ended call",
  max_duration: "Time limit reached",
  analysis_failed: "AI summary failed",
};

export function formatEventType(eventType: string): string {
  return EVENT_LABELS[eventType] ?? formatStatusLabel(eventType);
}

const ERROR_EVENTS = new Set([
  "provider_error",
  "invalid_number",
  "ai_error",
  "analysis_failed",
  "silence_timeout",
  "speech_not_recognized",
]);

export function isErrorEvent(eventType: string): boolean {
  return ERROR_EVENTS.has(eventType);
}
