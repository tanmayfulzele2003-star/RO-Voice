// Mirrors backend/audiocall/api/schemas.py — keep these in sync with the
// FastAPI response models.

export type CallStatus =
  | "queued"
  | "ringing"
  | "in_progress"
  | "completed"
  | "failed"
  | "no_answer"
  | "disconnected";

export type CallDirection = "outbound" | "inbound";

export type CallChannel = "phone" | "browser";

export type CallOutcome =
  | "qualified"
  | "not_interested"
  | "callback"
  | "incomplete"
  | "no_answer"
  | "no_conversation"
  | "failed";

export interface ProfileField {
  key: string;
  label: string;
  description: string;
  required: boolean;
}

export interface BusinessProfile {
  id: string;
  name: string;
  agent_name: string;
  industry: string | null;
  description: string | null;
  products: string | null;
  call_objective: string;
  greeting: string | null;
  language: string | null;
  fields: ProfileField[];
  is_default: boolean;
  created_at: string;
}

/** Create/update payload. A field's `key` may be left empty — the backend
 * derives it from the label. */
export type BusinessProfileInput = Omit<BusinessProfile, "id" | "created_at">;

export type LeadStatus = "interested" | "not_interested" | "uncertain";

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Customer {
  id: string;
  name: string;
  phone: string;
  company: string | null;
  purpose: string | null;
  product: string | null;
  profile_id: string | null;
  created_at: string;
}

export interface CustomerCreateInput {
  name: string;
  phone: string;
  company?: string | null;
  purpose?: string | null;
  product?: string | null;
  profile_id?: string | null;
}

export type CustomerUpdateInput = Partial<CustomerCreateInput>;

export interface CallStartResponse {
  call_id: string;
  call_sid: string | null;
  status: CallStatus;
}

export interface BrowserCallStartResponse {
  call_id: string;
  token: string;
  stream_url: string;
}

export interface CallListItem {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  profile_name: string | null;
  direction: CallDirection;
  channel: CallChannel;
  status: CallStatus;
  outcome: CallOutcome | null;
  lead_status: LeadStatus | null;
  follow_up: boolean | null;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  error_reason: string | null;
  created_at: string;
}

export interface ConversationMessage {
  speaker: "customer" | "ai";
  message: string;
  timestamp: string | null;
}

export interface Requirements {
  customer_name: string | null;
  company_name: string | null;
  requirement: string | null;
  ro_capacity: string | null;
  location: string | null;
  budget: string | null;
  timeline: string | null;
  additional_requirements: string | null;
  fields: Record<string, string> | null;
}

export interface CallEvent {
  event_type: string;
  detail: string | null;
  created_at: string;
}

export interface CallSummary {
  summary: string | null;
  customer_intent: string | null;
  key_requirements: string[] | null;
  important_points: string[] | null;
  follow_up: boolean | null;
  follow_up_notes: string | null;
  call_outcome: string | null;
  lead_status: LeadStatus | null;
}

export interface CallDetail {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  customer_company: string | null;
  customer_purpose: string | null;
  customer_product: string | null;
  profile_id: string | null;
  profile_name: string | null;
  profile_fields: ProfileField[];
  twilio_call_sid: string | null;
  direction: CallDirection;
  channel: CallChannel;
  status: CallStatus;
  outcome: CallOutcome | null;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  error_reason: string | null;
  created_at: string;
  messages: ConversationMessage[];
  events: CallEvent[];
  requirements: Requirements | null;
  summary: CallSummary | null;
}

export interface LoginResponse {
  username: string;
}

export interface StatsOverview {
  total_calls: number;
  completed_calls: number;
  failed_calls: number;
  interested_leads: number;
  follow_ups_required: number;
  avg_duration_seconds: number | null;
}
