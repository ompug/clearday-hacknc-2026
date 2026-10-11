import type {
  AccountsResponse,
  AnalystSegmentsResponse,
  AssistantRequest,
  AnnouncementResponse,
  AssistantResponse,
  CreateExpenseRequest,
  AnomaliesResponse,
  BacktestSummary,
  PriceItemsRequest,
  RecapResponse,
  PriceTipsResponse,
  CreateExpenseResult,
  DuplicateSubscriptionsResponse,
  DemoPersona,
  ForecastResponse,
  FutureRequest,
  FutureResponse,
  HouseholdMembersResponse,
  Me,
  PaymentRequest,
  ReceiptReadResult,
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
  getForecast(): Promise<ForecastResponse>;
  listHouseholdMembers(): Promise<HouseholdMembersResponse>;
  createExpense(request: CreateExpenseRequest): Promise<CreateExpenseResult>;
  /** Natural-language split: a proposal to confirm; nothing is saved. */
  askAssistant(request: AssistantRequest): Promise<AssistantResponse>;
  /** Spoken household announcement for a cleared shared bill: transcript plus optional audio. */
  getAnnouncement(): Promise<AnnouncementResponse>;
  /** Reads a receipt image into line items to confirm; the server deletes the image after. */
  readReceipt(file: File): Promise<ReceiptReadResult>;
  getDuplicateSubscriptions(): Promise<DuplicateSubscriptionsResponse>;
  getBacktest(): Promise<BacktestSummary>;
  getAnomalies(): Promise<AnomaliesResponse>;
  getPriceTips(req: PriceItemsRequest): Promise<PriceTipsResponse>;
  rememberPrices(req: PriceItemsRequest): Promise<void>;
  /** Segment hardship rates over synthetic households (never real users). */
  getAnalystSegments(): Promise<AnalystSegmentsResponse>;
  /** This week's two-host recap: lines, transcript and optional audio. */
  getRecap(): Promise<RecapResponse>;
  /** Hypothetical 10-year range for a steady monthly amount, with adjustable return assumptions. */
  getFuture(req?: FutureRequest): Promise<FutureResponse>;
}

export type Unsubscribe = () => void;

/** Socket.IO subscription, scoped to the session's household and user rooms. */
export interface RealtimeClient {
  on<E extends RealtimeEventName>(
    event: E,
    handler: (payload: RealtimeEvents[E]) => void,
  ): Unsubscribe;
}
