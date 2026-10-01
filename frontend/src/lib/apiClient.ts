import type {
  BrowserCallStartResponse,
  BusinessProfile,
  BusinessProfileInput,
  CallDetail,
  CallListItem,
  CallStartResponse,
  Customer,
  CustomerCreateInput,
  CustomerUpdateInput,
  LoginResponse,
  Paginated,
  StatsOverview,
} from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
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
  const url = new URL(path, API_BASE_URL);
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

    getStatsOverview: () =>
      request<StatsOverview>("/api/stats/overview", {}, cookieHeader),
  };
}

/** Browser-facing singleton — used from Client Components. */
export const apiClient = makeApiClient();
