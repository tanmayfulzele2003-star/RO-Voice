import type {
  BrowserCallStartResponse,
  BusinessProfile,
  BusinessProfileInput,
  CallDetail,
  CampaignAction,
  Campaign,
  CampaignCreateInput,
  CampaignDetail,
  CallListItem,
  CallStartResponse,
  Customer,
  CustomerCreateInput,
  CustomerUpdateInput,
  Invite,
  InviteCreated,
  JoinInfo,
  LoginResponse,
  Me,
  OrgSettingsView,
  Organization,
  PlatformOrganization,
  PlatformOrganizationCreated,
  Role,
  TeamUser,
  Paginated,
  PhoneNumber,
  PhoneNumberInput,
  ProfileTemplate,
  SettingsUpdate,
  SettingsView,
  SetupChecklist,
  SetupStatus,
  StatsOverview,
  TestResult,
} from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
/**
 * Where Server Components reach the backend. Defaults to the public URL; in
 * Docker the frontend container sets API_INTERNAL_URL=http://backend:8000,
 * since "localhost" there is the frontend container itself. Read at request
 * time on the server only (it's not a NEXT_PUBLIC_ variable, so it never
 * reaches the browser bundle).
 */
function baseUrl(): string {
  if (typeof window === "undefined" && process.env.API_INTERNAL_URL) {
    return process.env.API_INTERNAL_URL;
  }
  return API_BASE_URL;
}
/** WebSocket origin of the same backend (http→ws, https→wss), no trailing slash. */
export const API_WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws").replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  searchParams?: Record<string, string | number | undefined>;
}

async function request<T>(
  path: string,
  options: RequestOptions,
  cookieHeader?: string,
): Promise<T> {
  const url = new URL(path, baseUrl());
  if (options.searchParams) {
    for (const [key, value] of Object.entries(options.searchParams)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = {};
  if (options.body) headers["Content-Type"] = "application/json";
  // Server Components run in Node — cookies aren't attached automatically
  // the way a browser would, so the incoming request's cookie header is
  // forwarded explicitly (see getServerApiClient). In the browser, plain
  // `credentials: "include"` lets the browser attach the cookie itself.
  if (cookieHeader) headers["Cookie"] = cookieHeader;

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      method: options.method ?? "GET",
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
      credentials: cookieHeader ? undefined : "include",
    });
  } catch {
    throw new ApiError(0, "Could not reach the backend API. Is it running?");
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.json()) as {
        detail?: string | { msg?: string; loc?: (string | number)[] }[];
      };
      if (Array.isArray(data.detail)) {
        // FastAPI validation errors: [{loc: ["body", "phone"], msg: "..."}]
        detail = data.detail
          .map((item) => {
            const field = item.loc?.filter((part) => part !== "body").join(".");
            const msg = (item.msg ?? "Invalid value").replace(/^Value error, /, "");
            return field ? `${field}: ${msg}` : msg;
          })
          .join("; ");
      } else {
        detail = data.detail ?? detail;
      }
    } catch {
      // Response wasn't JSON — fall back to statusText.
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export interface CallListFilters {
  limit?: number;
  offset?: number;
  status?: string;
  lead_status?: string;
  date_from?: string;
  date_to?: string;
  customer_name?: string;
  follow_up?: string;
  outcome?: string;
  channel?: string;
  profile_id?: string;
  direction?: string;
  campaign_id?: string;
  [key: string]: string | number | undefined;
}

/**
 * Builds the API client. `cookieHeader`, when provided, is forwarded as-is
 * on every request — used for server-side calls (see getServerApiClient).
 * Browser-side calls omit it and rely on `credentials: "include"` instead.
 */
export function makeApiClient(cookieHeader?: string) {
  return {
    login: (username: string, password: string) =>
      request<LoginResponse>(
        "/api/auth/login",
        { method: "POST", body: { username, password } },
        cookieHeader,
      ),
    logout: () => request<void>("/api/auth/logout", { method: "POST" }, cookieHeader),
    getMe: () => request<Me>("/api/auth/me", {}, cookieHeader),
    changePassword: (currentPassword: string, newPassword: string) =>
      request<void>(
        "/api/auth/password",
        { method: "POST", body: { current_password: currentPassword, new_password: newPassword } },
        cookieHeader,
      ),

    getOrganization: () => request<Organization>("/api/organization", {}, cookieHeader),
    renameOrganization: (name: string) =>
      request<Organization>("/api/organization", { method: "PATCH", body: { name } }, cookieHeader),
    listUsers: () => request<TeamUser[]>("/api/users", {}, cookieHeader),
    updateUser: (id: string, input: { role?: Role; is_active?: boolean }) =>
      request<TeamUser>(`/api/users/${id}`, { method: "PATCH", body: input }, cookieHeader),
    deleteUser: (id: string) => request<void>(`/api/users/${id}`, { method: "DELETE" }, cookieHeader),
    listInvites: () => request<Invite[]>("/api/invites", {}, cookieHeader),
    createInvite: (role: Role, note: string | null) =>
      request<InviteCreated>("/api/invites", { method: "POST", body: { role, note } }, cookieHeader),
    revokeInvite: (id: string) =>
      request<void>(`/api/invites/${id}`, { method: "DELETE" }, cookieHeader),
    describeInvite: (token: string) =>
      request<JoinInfo>(`/api/join/${encodeURIComponent(token)}`, {}, cookieHeader),
    acceptInvite: (token: string, username: string, password: string) =>
      request<Me>(
        `/api/join/${encodeURIComponent(token)}`,
        { method: "POST", body: { username, password } },
        cookieHeader,
      ),

    listPlatformOrganizations: () =>
      request<PlatformOrganization[]>("/api/platform/organizations", {}, cookieHeader),
    createPlatformOrganization: (name: string, maxConcurrentCalls: number | null) =>
      request<PlatformOrganizationCreated>(
        "/api/platform/organizations",
        { method: "POST", body: { name, max_concurrent_calls: maxConcurrentCalls } },
        cookieHeader,
      ),
    updatePlatformOrganization: (
      id: string,
      input: { name?: string; is_active?: boolean; max_concurrent_calls?: number | null },
    ) =>
      request<PlatformOrganization>(
        `/api/platform/organizations/${id}`,
        { method: "PATCH", body: input },
        cookieHeader,
      ),
    createOwnerInvite: (orgId: string) =>
      request<InviteCreated>(
        `/api/platform/organizations/${orgId}/invites`,
        { method: "POST" },
        cookieHeader,
      ),

    listCustomers: (params: { limit?: number; offset?: number } = {}) =>
      request<Paginated<Customer>>("/api/customers", { searchParams: params }, cookieHeader),
    getCustomer: (id: string) => request<Customer>(`/api/customers/${id}`, {}, cookieHeader),
    createCustomer: (input: CustomerCreateInput) =>
      request<Customer>("/api/customers", { method: "POST", body: input }, cookieHeader),
    updateCustomer: (id: string, input: CustomerUpdateInput) =>
      request<Customer>(`/api/customers/${id}`, { method: "PATCH", body: input }, cookieHeader),

    listProfiles: () => request<BusinessProfile[]>("/api/profiles", {}, cookieHeader),
    getProfile: (id: string) =>
      request<BusinessProfile>(`/api/profiles/${id}`, {}, cookieHeader),
    createProfile: (input: BusinessProfileInput) =>
      request<BusinessProfile>("/api/profiles", { method: "POST", body: input }, cookieHeader),
    updateProfile: (id: string, input: Partial<BusinessProfileInput>) =>
      request<BusinessProfile>(
        `/api/profiles/${id}`,
        { method: "PATCH", body: input },
        cookieHeader,
      ),
    deleteProfile: (id: string) =>
      request<void>(`/api/profiles/${id}`, { method: "DELETE" }, cookieHeader),

    startBrowserCall: (customerId: string) =>
      request<BrowserCallStartResponse>(
        "/api/calls/browser",
        { method: "POST", body: { customer_id: customerId } },
        cookieHeader,
      ),
    startCall: (customerId: string) =>
      request<CallStartResponse>(
        "/api/calls",
        { method: "POST", body: { customer_id: customerId } },
        cookieHeader,
      ),
    listCalls: (params: CallListFilters = {}) =>
      request<Paginated<CallListItem>>("/api/calls", { searchParams: params }, cookieHeader),
    getCall: (id: string) => request<CallDetail>(`/api/calls/${id}`, {}, cookieHeader),

    listNumbers: () => request<PhoneNumber[]>("/api/numbers", {}, cookieHeader),
    createNumber: (input: PhoneNumberInput) =>
      request<PhoneNumber>("/api/numbers", { method: "POST", body: input }, cookieHeader),
    updateNumber: (id: string, input: Partial<PhoneNumberInput>) =>
      request<PhoneNumber>(`/api/numbers/${id}`, { method: "PATCH", body: input }, cookieHeader),
    deleteNumber: (id: string) =>
      request<void>(`/api/numbers/${id}`, { method: "DELETE" }, cookieHeader),
    syncNumberToTwilio: (id: string) =>
      request<PhoneNumber>(`/api/numbers/${id}/sync-twilio`, { method: "POST" }, cookieHeader),

    listCampaigns: () => request<Campaign[]>("/api/campaigns", {}, cookieHeader),
    getCampaign: (id: string) =>
      request<CampaignDetail>(`/api/campaigns/${id}`, {}, cookieHeader),
    createCampaign: (input: CampaignCreateInput) =>
      request<CampaignDetail>("/api/campaigns", { method: "POST", body: input }, cookieHeader),
    changeCampaignStatus: (id: string, action: CampaignAction) =>
      request<CampaignDetail>(`/api/campaigns/${id}/${action}`, { method: "POST" }, cookieHeader),
    deleteCampaign: (id: string) =>
      request<void>(`/api/campaigns/${id}`, { method: "DELETE" }, cookieHeader),

    getSetupStatus: () => request<SetupStatus>("/api/setup/status", {}, cookieHeader),
    createFirstAdmin: (input: {
      token: string;
      company_name: string;
      username: string;
      password: string;
    }) =>
      request<SetupStatus>("/api/setup/admin", { method: "POST", body: input }, cookieHeader),
    getSetupChecklist: () => request<SetupChecklist>("/api/setup/checklist", {}, cookieHeader),
    setSetupFlag: (key: "setup_profile" | "setup_completed", value: boolean) =>
      request<void>("/api/setup/flags", { method: "POST", body: { key, value } }, cookieHeader),

    /** The company's own Twilio account (admins and owners). */
    getOrgSettings: () => request<OrgSettingsView>("/api/settings", {}, cookieHeader),
    updateOrgSettings: (input: SettingsUpdate) =>
      request<OrgSettingsView>("/api/settings", { method: "PATCH", body: input }, cookieHeader),
    testOrgTwilio: () =>
      request<TestResult>("/api/settings/test-twilio", { method: "POST" }, cookieHeader),

    /** Platform-wide settings (platform admin only). */
    getPlatformSettings: () => request<SettingsView>("/api/platform/settings", {}, cookieHeader),
    updatePlatformSettings: (input: SettingsUpdate) =>
      request<SettingsView>("/api/platform/settings", { method: "PATCH", body: input }, cookieHeader),
    testPlatformTwilio: () =>
      request<TestResult>("/api/platform/settings/test-twilio", { method: "POST" }, cookieHeader),
    testGemini: () =>
      request<TestResult>("/api/platform/settings/test-gemini", { method: "POST" }, cookieHeader),
    testPublicUrl: () =>
      request<TestResult>("/api/platform/settings/test-public-url", { method: "POST" }, cookieHeader),

    listProfileTemplates: () =>
      request<ProfileTemplate[]>("/api/profiles/templates", {}, cookieHeader),

    getStatsOverview: () =>
      request<StatsOverview>("/api/stats/overview", {}, cookieHeader),
  };
}

/** Browser-facing singleton — used from Client Components. */
export const apiClient = makeApiClient();
