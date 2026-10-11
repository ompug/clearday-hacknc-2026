import type { ApiClient } from "./client";
import {
  ApiError,
  type AccountsResponse,
  type AnnouncementResponse,
  type AssistantRequest,
  type AssistantResponse,
  type BacktestSummary,
  type CreateExpenseRequest,
  type DuplicateSubscriptionsResponse,
  type CreateExpenseResult,
  type DemoPersona,
  type ForecastResponse,
  type HouseholdMembersResponse,
  type Me,
  type PaymentRequest,
  type PaymentResult,
  type ReceiptReadResult,
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
