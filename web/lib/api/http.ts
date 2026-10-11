import type { ApiClient } from "./client";
import {
  ApiError,
  type AccountsResponse,
  type AnalystSegmentsResponse,
  type AnnouncementResponse,
  type AssistantRequest,
  type AssistantResponse,
  type AnomaliesResponse,
  type BacktestSummary,
  type PriceItemsRequest,
  type PriceTipsResponse,
  type CreateExpenseRequest,
  type DuplicateSubscriptionsResponse,
  type CreateExpenseResult,
  type DemoPersona,
  type ForecastResponse,
  type FutureResponse,
  type HelpPanelResponse,
  type HouseholdMembersResponse,
  type Me,
  type PaymentRequest,
  type PaymentResult,
  type ReceiptReadResult,
  type RecapResponse,
  type SkyResponse,
} from "./types";

/**
 * Routes not yet in the spec's endpoint table. The backend should add them (or
 * tell us the real paths) before mocks are switched off.
 */
export const DEMO_PERSONAS_PATH = "/api/dev/personas";
export const DEMO_LOGIN_PATH = "/api/dev/login";
export const LOGOUT_PATH = "/api/session/logout";
export const ME_PATH = "/api/me";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    // Session cookie carries identity; the body never does.
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new ApiError(response.status, `${init?.method ?? "GET"} ${path} failed`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const httpApi: ApiClient = {
  listDemoPersonas: () => request<DemoPersona[]>(DEMO_PERSONAS_PATH),
  loginAsPersona: (userId) =>
    request<Me>(DEMO_LOGIN_PATH, { method: "POST", body: JSON.stringify({ user_id: userId }) }),
  logout: () => request<void>(LOGOUT_PATH, { method: "POST" }),
  me: async () => {
    try {
      return await request<Me>(ME_PATH);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },
  readReceipt: async (file) => {
    const response = await fetch(`${BASE_URL}/api/receipts`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": file.type },
      body: file,
    });
    if (!response.ok) throw new ApiError(response.status, "POST /api/receipts failed");
    return (await response.json()) as ReceiptReadResult;
  },
  getAnnouncement: () => request<AnnouncementResponse>("/api/voice/announcement"),
  getDuplicateSubscriptions: () =>
    request<DuplicateSubscriptionsResponse>("/api/insights/subscriptions"),
  getBacktest: () => request<BacktestSummary>("/api/insights/backtest"),
  getPriceTips: (req: PriceItemsRequest) =>
    request<PriceTipsResponse>("/api/prices/tips", { method: "POST", body: JSON.stringify(req) }),
  rememberPrices: async (req: PriceItemsRequest) => {
    await request("/api/prices/remember", { method: "POST", body: JSON.stringify(req) });
  },
  getAnalystSegments: () => request<AnalystSegmentsResponse>("/api/analyst/segments"),
  getFuture: (req) => {
    const q = new URLSearchParams();
    if (req?.rates) {
      q.set("low", String(req.rates.low));
      q.set("mid", String(req.rates.mid));
      q.set("high", String(req.rates.high));
    }
    if (req?.monthly_cents !== undefined) q.set("monthly_cents", String(req.monthly_cents));
    return request<FutureResponse>(`/api/future${q.size ? `?${q}` : ""}`);
  },
  getHelpPanel: () => request<HelpPanelResponse>("/api/help"),
  getRecap: () => request<RecapResponse>("/api/recap/latest"),
  getAnomalies: () => request<AnomaliesResponse>("/api/insights/anomalies"),
  getSky: () => request<SkyResponse>("/api/sky"),
  getAccounts: () => request<AccountsResponse>("/api/accounts"),
  pay: (body: PaymentRequest) =>
    request<PaymentResult>("/api/payments", { method: "POST", body: JSON.stringify(body) }),
  listHouseholdMembers: () => request<HouseholdMembersResponse>("/api/household/members"),
  createExpense: (body: CreateExpenseRequest) =>
    request<CreateExpenseResult>("/api/expenses", { method: "POST", body: JSON.stringify(body) }),
  getForecast: () => request<ForecastResponse>("/api/forecast"),
  askAssistant: (body: AssistantRequest) =>
    request<AssistantResponse>("/api/assistant", { method: "POST", body: JSON.stringify(body) }),
};
