import type {
  AccountsResponse,
  DemoPersona,
  Me,
  PaymentRequest,
  PaymentResult,
  RealtimeEventName,
  RealtimeEvents,
  SkyResponse,
} from "./types";

/**
 * Everything the web app may ask the backend. Both the mock and the HTTP
 * implementation satisfy this; components only ever see this interface.
 * Identity is implicit (session cookie), so no method takes a user ID except
 * the demo persona login.
 */
export interface ApiClient {
  listDemoPersonas(): Promise<DemoPersona[]>;
  loginAsPersona(userId: string): Promise<Me>;
  logout(): Promise<void>;
  /** Null when there is no session. */
  me(): Promise<Me | null>;
  getSky(): Promise<SkyResponse>;
  getAccounts(): Promise<AccountsResponse>;
  pay(request: PaymentRequest): Promise<PaymentResult>;
}

export type Unsubscribe = () => void;

/** Socket.IO subscription, scoped to the session's household and user rooms. */
export interface RealtimeClient {
  on<E extends RealtimeEventName>(
    event: E,
    handler: (payload: RealtimeEvents[E]) => void,
  ): Unsubscribe;
}
