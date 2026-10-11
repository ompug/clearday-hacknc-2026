/**
 * The FastAPI backend is contract-tested against these types (api/tests/test_api_contract.py
 * mirrors their keys and value types by hand); change both together.
 *
 * Wire types for the Clearday backend (FastAPI), mirroring docs/02-technical-spec.md.
 *
 * Conventions shared with the backend and analytics modules:
 * - Field names are snake_case, exactly as the JSON arrives.
 * - Money is integer cents (`Cents`). Never divide or format it outside `formatCents`.
 * - Dates are `YYYY-MM-DD` strings (`IsoDate`); due dates display in America/New_York.
 * - IDs are opaque app IDs. Nessie IDs and account numbers never reach the client.
 * - `label` / `merchant` strings are untrusted text: render as text only, never as HTML
 *   and never branch behaviour on their content.
 */

/** Integer number of cents. */
export type Cents = number;
/** `YYYY-MM-DD`. */
export type IsoDate = string;
/** ISO 8601 UTC timestamp. */
export type IsoDateTime = string;

// ---------------------------------------------------------------------------
// Session (demo persona login). NOT in the spec's endpoint table yet; see
// `DEMO_LOGIN_PATH` / `ME_PATH` in http.ts.
// ---------------------------------------------------------------------------

export interface DemoPersona {
  user_id: string;
  display_name: string;
  /** Short, non-financial description shown on the picker. */
  tagline: string;
}

export interface Me {
  user: { user_id: string; display_name: string };
  household: { household_id: string; name: string };
}

// ---------------------------------------------------------------------------
// GET /api/accounts
// ---------------------------------------------------------------------------

export type AccountType = "checking" | "savings" | "credit_card";

export interface Account {
  account_id: string;
  type: AccountType;
  nickname: string;
  /** Last 4 digits only. */
  last4: string;
  /** For credit cards this is the amount owed. */
  balance_cents: Cents;
}

export interface AccountsResponse {
  accounts: Account[];
}

// ---------------------------------------------------------------------------
// GET /api/sky
// ---------------------------------------------------------------------------

/** Share/bill status, per the `shares.status` column. */
export type ShareStatus = "open" | "partial" | "paid" | "disputed";

/**
 * Forecast colour bucket for a bubble, derived server-side from `p_short`
 * (probability of dropping below the safety threshold before the due date).
 */
export type Weather = "clear" | "watch" | "tight";

export type Necessity = "need" | "want";

export interface SkyBubble {
  bubble_id: string;
  /** `bill`: the user's own bill. `shared`: their share of a household expense. */
  kind: "bill" | "shared";
  label: string;
  due_date: IsoDate;
  /** The current user's part still to pay (a partial share's remainder; the whole share once paid).
   * The amount `POST /api/payments` accepts. Equals `total_cents` for a personal bill. */
  your_share_cents: Cents;
  total_cents: Cents;
  /** Status of the current user's share (or the bill itself). */
  status: ShareStatus;
  /** 0..1, how much of the whole bubble is paid across all participants. */
  fill_fraction: number;
  paid_count: number;
  participant_count: number;
  p_short: number;
  weather: Weather;
  necessity: Necessity;
  /** Set for shared bubbles; used by `share.updated` / `bubble.popped`. */
  expense_id: string | null;
  /** The current user's share, when `kind === "shared"`. */
  share_id: string | null;
  /** Suggested paying account. */
  default_account_id: string | null;
  /** Bubbles in a cluster render as one bubble until expanded. */
  cluster_id: string | null;
  /**
   * Whether POST /api/payments accepts this bubble now. False for a paid or disputed share and for a
   * predicted subscription renewal (`sub_`), which charges on its own.
   */
  payable: boolean;
}

export interface SkyCluster {
  cluster_id: string;
  label: string;
  bubble_ids: string[];
}

export interface SkyResponse {
  as_of: IsoDateTime;
  bubbles: SkyBubble[];
  clusters: SkyCluster[];
  safe_to_spend_cents: Cents;
  next_payday: IsoDate;
}

// ---------------------------------------------------------------------------
// POST /api/payments
// ---------------------------------------------------------------------------

export interface PaymentRequest {
  /** Client-generated (crypto.randomUUID); the DB enforces uniqueness. */
  idempotency_key: string;
  bubble_id: string;
  account_id: string;
  /** What the user confirmed. The server recomputes it from the ledger and rejects a mismatch. */
  amount_cents: Cents;
}

export interface PaymentResult {
  payment_id: string;
  bubble_id: string;
  status: ShareStatus;
  fill_fraction: number;
  paid_count: number;
  /** True when the whole bubble is now covered and pops for everyone. */
  popped: boolean;
}

// ---------------------------------------------------------------------------
// Socket.IO events (room per household, plus a private room per user)
// ---------------------------------------------------------------------------

export interface ShareUpdatedEvent {
  expense_id: string;
  share_id: string;
  status: ShareStatus;
  fill_fraction: number;
}

export interface BubblePoppedEvent {
  expense_id: string;
  label: string;
}

export interface FeedCreatedEvent {
  type: string;
  actor_display_name: string;
  subject_label: string;
}

export interface ForecastUpdatedEvent {
  bubbles: { bubble_id: string; weather: Weather; p_short: number }[];
  safe_to_spend_cents: Cents;
}

export interface RealtimeEvents {
  "share.updated": ShareUpdatedEvent;
  "bubble.popped": BubblePoppedEvent;
  "feed.created": FeedCreatedEvent;
  "forecast.updated": ForecastUpdatedEvent;
}

export type RealtimeEventName = keyof RealtimeEvents;

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// POST /api/expenses (create a shared expense with a split)
// GET /api/household/members (who can be in a split)
// ---------------------------------------------------------------------------

export interface HouseholdMember {
  user_id: string;
  display_name: string;
}

export interface HouseholdMembersResponse {
  members: HouseholdMember[];
}

/**
 * The expenses contract offers even and custom splits only. An itemized split is built in the
 * dialog (analytics.splits rules) and submitted as `custom` with each person's total.
 */
export type SplitMethod = "even" | "custom";

export interface ExpenseParticipant {
  user_id: string;
  /** Required for `custom` (all amounts must sum to `total_cents`); omit for `even`. */
  amount_cents?: Cents;
}

/**
 * The payer is always the signed-in user (session cookie), never a body field.
 * The payer may be a participant: their own share is created already `paid`.
 * At least one participant other than the payer is required. Ledger-only: no
 * money moves until someone pops their share.
 */
export interface CreateExpenseRequest {
  /** Client-generated (crypto.randomUUID); a replay returns the original result. */
  idempotency_key: string;
  /** 1..80 chars, untrusted text. */
  label: string;
  /** Positive integer cents. */
  total_cents: Cents;
  split_method: SplitMethod;
  /** Unique household members. */
  participants: ExpenseParticipant[];
  /** Defaults to today when omitted or null. */
  due_date?: IsoDate | null;
}

export interface ExpenseShare {
  share_id: string;
  user_id: string;
  amount_cents: Cents;
  status: ShareStatus;
}

export interface CreateExpenseResult {
  /** Also the shared bubble's `bubble_id` in `/api/sky`. */
  expense_id: string;
  label: string;
  total_cents: Cents;
  split_method: SplitMethod;
  due_date: IsoDate;
  payer_id: string;
  /** Sorted by user_id; amounts always sum to `total_cents`. */
  shares: ExpenseShare[];
}

// ---------------------------------------------------------------------------
// GET /api/forecast: the spec's Analytics contract (`forecast.py`) output for the
// signed-in user, plus `as_of`, `threshold_cents` and each bill's bubble link and weather.
// ---------------------------------------------------------------------------

export interface ForecastDay {
  date: IsoDate;
  /** Pessimistic, typical and hopeful balance paths. UI copy never says "P10". */
  p10_cents: Cents;
  p50_cents: Cents;
  p90_cents: Cents;
}

export interface ForecastBill {
  label: string;
  date: IsoDate;
  amount_cents: Cents;
  /** Chance the balance is below the safety threshold before this bill. */
  p_short: number;
  /** The sky bubble this bill belongs to (null if it has none). */
  bubble_id: string | null;
  /** Colour bucket for `p_short`, same rule as `SkyBubble.weather`. */
  weather: Weather;
}

export interface ForecastScenarioBill {
  label: string;
  date: IsoDate;
  p_short: number;
  bubble_id: string | null;
  weather: Weather;
}

export interface ForecastDriver {
  category: string;
  share_of_variance: number;
}

export interface ForecastResponse {
  as_of: IsoDateTime;
  /** Safety threshold the chances are measured against (default $50). */
  threshold_cents: Cents;
  days: ForecastDay[];
  bills: ForecastBill[];
  safe_to_spend_cents: Cents;
  /** Null when no paycheck lands inside the horizon. */
  next_payday: IsoDate | null;
  drivers: ForecastDriver[];
  /** The same month with "want" spending trimmed by 25%. */
  wants_trimmed: {
    safe_to_spend_cents: Cents;
    bills: ForecastScenarioBill[];
  };
}

// ---------------------------------------------------------------------------
// POST /api/assistant: natural-language split. The model (Gemma) only ever sees
// placeholders; the server maps them back and computes every amount from the
// ledger. Nothing is saved: the user confirms, then the app calls POST /api/expenses.
// ---------------------------------------------------------------------------

export interface AssistantRequest {
  /** What the user typed, e.g. "split last night's pizza with Jake". Max 500 characters. */
  message: string;
}

export interface AssistantShare {
  user_id: string;
  display_name: string;
  amount_cents: Cents;
}

export interface AssistantSplitProposal {
  kind: "split";
  /** The purchase's merchant name (untrusted text; render as text only). */
  label: string;
  purchase_date: IsoDate;
  total_cents: Cents;
  split_method: "even";
  /** Includes the signed-in user; sorted by user_id; amounts sum to `total_cents`. */
  participants: AssistantShare[];
}

export interface AssistantResponse {
  reply: string;
  /** "template" when the model was slow, rate-limited or unavailable. */
  source: "model" | "template";
  proposal: AssistantSplitProposal | null;
}

// ---------------------------------------------------------------------------
// POST /api/receipts: raw image body (image/png, image/jpeg or image/webp, at most 5 MB).
// Returns line items for the user to confirm; nothing is saved and the image is deleted
// right after extraction. 503 = the reader is unavailable, 422 = couldn't read it or the
// items didn't add up, 413/415 = too big or wrong type: in every case enter items by hand.
// ---------------------------------------------------------------------------

export interface ReceiptLineItem {
  /** Untrusted text from the receipt; render as text only. */
  label: string;
  amount_cents: Cents;
}

export interface ReceiptReadResult {
  /** Untrusted text; render as text only. */
  merchant: string;
  date: IsoDate | null;
  items: ReceiptLineItem[];
  tax_cents: Cents;
  tip_cents: Cents;
  /** Always equals the items plus tax plus tip. */
  total_cents: Cents;
}

// ---------------------------------------------------------------------------
// Price memory. POST /api/prices/tips (items of a receipt just read -> where each was cheaper
// before; saves nothing) and POST /api/prices/remember (the confirmed items, kept for later).
// History is the signed-in user's own receipts only. Shown only in the app, never in the feed
// or on Clearday Home.
// ---------------------------------------------------------------------------

export interface PriceItemsRequest {
  merchant: string;
  date: IsoDate;
  items: ReceiptLineItem[];
}

export interface PricePoint {
  /** Untrusted text; render as text only. */
  merchant: string;
  date: IsoDate;
  unit_price_cents: Cents;
}

export interface PriceTip {
  /** The item as written on this receipt (untrusted text). */
  label: string;
  /** The normalized item name. */
  item: string;
  /** The cheapest remembered price. */
  best: PricePoint;
  /** The most recent price, which is this receipt's. */
  latest: PricePoint;
  /** latest minus best, always above 0 here. */
  savings_cents_per_unit: Cents;
}

export interface PriceTipsResponse {
  tips: PriceTip[];
}

// ---------------------------------------------------------------------------
// GET /api/voice/announcement: household-level spoken text, no amounts or names.
// ---------------------------------------------------------------------------

export interface AnnouncementResponse {
  /** Always shown as the transcript. */
  text: string;
  /** Null when ElevenLabs is unavailable: text only. Fetch with the session cookie. */
  audio_url: string | null;
  source: "elevenlabs" | "cache" | "text";
}

// ---------------------------------------------------------------------------
// GET /api/insights/subscriptions and /api/insights/backtest
// ---------------------------------------------------------------------------

export interface DuplicateSubscription {
  /** Untrusted text; render as text only. */
  merchant: string;
  /** Roommates in the signed-in user's household who each pay for it. */
  members: { user_id: string; display_name: string }[];
  monthly_cost_cents: Cents;
  possible_savings_cents: Cents;
}

export interface DuplicateSubscriptionsResponse {
  duplicates: DuplicateSubscription[];
}

export interface UnusualCharge {
  /** Opaque ID of the charge ("txn_<n>"). */
  anomaly_id: string;
  /** Untrusted text; render as text only. */
  merchant: string;
  /** YYYY-MM-DD */
  date: string;
  amount_cents: Cents;
  typical_low_cents: Cents;
  typical_high_cents: Cents;
}

/** GET /api/insights/anomalies: the signed-in user's own unusual charges only. */
export interface AnomaliesResponse {
  anomalies: UnusualCharge[];
}

export interface BacktestSummary {
  /** Share of held-out days whose actual balance fell inside the P10 to P90 band, 0 to 1. */
  coverage: number;
  median_abs_error_cents: Cents;
  holdout_days: number;
  /** True while analytics.backtest is the stub: the number is a placeholder, say so. */
  is_preview: boolean;
}
