/**
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
  /** The current user's part. Equals `total_cents` for a personal bill. */
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
