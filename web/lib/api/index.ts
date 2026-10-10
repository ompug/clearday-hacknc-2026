import type { ApiClient, RealtimeClient } from "./client";
import { httpApi } from "./http";
import { mockApi, mockRealtime } from "./mock/client";
import { socketRealtime } from "./realtime";

export type { ApiClient, RealtimeClient, Unsubscribe } from "./client";
export * from "./types";

/** The one switch between the in-memory mock and the FastAPI backend. */
export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

export const api: ApiClient = USE_MOCKS ? mockApi : httpApi;
export const realtime: RealtimeClient = USE_MOCKS ? mockRealtime : socketRealtime;
