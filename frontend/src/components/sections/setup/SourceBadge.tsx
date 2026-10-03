import { Badge } from "@/components/ui/Badge";
import type { SettingValue } from "@/types/api";

export function SourceBadge({ setting }: { setting: SettingValue }) {
  if (setting.source === "dashboard") return <Badge tone="success">Saved here</Badge>;
  if (setting.source === "organization") return <Badge tone="success">Your company&apos;s account</Badge>;
  if (setting.source === "environment") return <Badge tone="info">From server environment</Badge>;
  return <Badge tone="warning">Not set</Badge>;
}
