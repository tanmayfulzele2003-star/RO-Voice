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
  | "transferred"
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
  /** E.164 number of a person the agent can hand phone calls to. */
  transfer_number: string | null;
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
  from_number: string | null;
  to_number: string | null;
  campaign_id: string | null;
  transferred_to: string | null;
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
  from_number: string | null;
  to_number: string | null;
  campaign_id: string | null;
  transferred_to: string | null;
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

export type Role = "viewer" | "member" | "admin" | "owner";

/** The signed-in user (GET /api/auth/me, and the login response). */
export interface Me {
  username: string;
  role: Role;
  is_platform_admin: boolean;
  organization: { id: string; name: string };
}

export type LoginResponse = Me;

export interface StatsOverview {
  total_calls: number;
  completed_calls: number;
  failed_calls: number;
  interested_leads: number;
  follow_ups_required: number;
  avg_duration_seconds: number | null;
}

export interface PhoneNumber {
  id: string;
  number: string;
  label: string | null;
  /** null = shared pool, usable by every business. */
  profile_id: string | null;
  inbound_enabled: boolean;
  outbound_enabled: boolean;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export type PhoneNumberInput = Pick<
  PhoneNumber,
  "number" | "label" | "profile_id" | "inbound_enabled" | "outbound_enabled" | "is_active"
>;

export type CampaignStatus = "draft" | "running" | "paused" | "completed" | "cancelled";

export type CampaignContactStatus = "pending" | "dialing" | "completed" | "failed" | "cancelled";

export interface CampaignCounts {
  pending: number;
  dialing: number;
  completed: number;
  failed: number;
  cancelled: number;
  total: number;
}

export interface Campaign {
  id: string;
  name: string;
  profile_id: string | null;
  status: CampaignStatus;
  /** Why the dialer paused the campaign on its own, e.g. Twilio credentials rejected. */
  status_reason: string | null;
  max_concurrent: number;
  max_attempts: number;
  retry_delay_minutes: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  counts: CampaignCounts;
}

export interface CampaignContact {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  status: CampaignContactStatus;
  attempts: number;
  last_call_id: string | null;
  last_outcome: string | null;
  next_attempt_at: string | null;
}

export interface CampaignDetail extends Campaign {
  contacts: CampaignContact[];
}

export interface CampaignCreateInput {
  name: string;
  profile_id: string | null;
  customer_ids: string[];
  max_concurrent: number;
  max_attempts: number;
  retry_delay_minutes: number;
}

export type CampaignAction = "start" | "pause" | "cancel";

export type SettingKey =
  | "twilio_account_sid"
  | "twilio_auth_token"
  | "twilio_phone_number"
  | "google_api_key"
  | "public_url";

export interface SettingValue {
  label: string;
  secret: boolean;
  /** Masked for secrets ("••••••••1234"). */
  value: string;
  is_set: boolean;
  source: "dashboard" | "organization" | "environment" | "unset";
}

export type SettingsView = Record<SettingKey, SettingValue>;

/** Only keys sent are changed; "" removes the saved value. */
export type SettingsUpdate = Partial<Record<SettingKey, string>>;

export interface TwilioAccountNumber {
  number: string;
  friendly_name: string;
  registered: boolean;
}

export interface TestResult {
  ok: boolean;
  message: string;
  details: { account_type?: string; numbers?: TwilioAccountNumber[] } | null;
}

export interface SetupStatus {
  needs_admin: boolean;
}

export type ChecklistKey = "twilio" | "number" | "gemini" | "public_url" | "profile" | "test_call";

export interface ChecklistItem {
  key: ChecklistKey;
  label: string;
  done: boolean;
  hint: string;
  /** Platform-wide step; only shown to the platform admin. */
  platform: boolean;
}

export interface SetupChecklist {
  items: ChecklistItem[];
  complete: boolean;
  dismissed: boolean;
}

export interface ProfileTemplate {
  id: string;
  title: string;
  summary: string;
  profile: Omit<BusinessProfileInput, "is_default" | "transfer_number">;
}

export type TwilioSettingKey = "twilio_account_sid" | "twilio_auth_token" | "twilio_phone_number";

/** The company's own Twilio settings (GET /api/settings). */
export interface OrgSettingsView {
  settings: Record<TwilioSettingKey, SettingValue>;
  /** No own account saved: calls go through the platform's Twilio account. */
  uses_platform_twilio: boolean;
  platform_twilio_available: boolean;
}

export interface Organization {
  id: string;
  name: string;
  max_concurrent_calls: number | null;
  created_at: string;
}

export interface TeamUser {
  id: string;
  username: string;
  role: Role;
  is_active: boolean;
  is_platform_admin: boolean;
  created_at: string;
}

export interface Invite {
  id: string;
  role: Role;
  note: string | null;
  expires_at: string;
  created_at: string;
}

/** Returned once, when the invite is created. The link is /join?token=… */
export interface InviteCreated extends Invite {
  token: string;
}

export interface JoinInfo {
  organization: string;
  role: Role;
  expires_at: string;
}

export interface PlatformOrganization {
  id: string;
  name: string;
  is_active: boolean;
  max_concurrent_calls: number | null;
  users: number;
  calls: number;
  created_at: string;
}

export interface PlatformOrganizationCreated {
  organization: PlatformOrganization;
  owner_invite: InviteCreated;
}
