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
