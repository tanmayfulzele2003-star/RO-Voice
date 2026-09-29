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
  created_at: string;
}

export interface CustomerCreateInput {
  name: string;
  phone: string;
  company?: string | null;
}

export interface CustomerUpdateInput {
  name?: string;
  phone?: string;
  company?: string | null;
}

export interface CallStartResponse {
  call_id: string;
  call_sid: string | null;
  status: CallStatus;
}

export interface CallListItem {
  id: string;
  customer_id: string;
  customer_name: string;
  direction: CallDirection;
  status: CallStatus;
  lead_status: LeadStatus | null;
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
}

export interface CallSummary {
  summary: string | null;
  customer_intent: string | null;
  key_requirements: string[] | null;
  important_points: string[] | null;
  follow_up: boolean | null;
  lead_status: LeadStatus | null;
}

export interface CallDetail {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  twilio_call_sid: string | null;
  direction: CallDirection;
  status: CallStatus;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  error_reason: string | null;
  created_at: string;
  messages: ConversationMessage[];
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
