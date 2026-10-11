/**
 * In-memory mock of the Clearday backend. State lives for the lifetime of the
 * tab (a reload resets the demo); the chosen persona is kept in localStorage to
 * stand in for the session cookie.
 */
import { addDays, daysBetween, todayIso } from "../../dates";
import type { ApiClient, RealtimeClient } from "../client";
import {
  ApiError,
  type Account,
  type CreateExpenseRequest,
  type CreateExpenseResult,
  type Me,
  type PaymentRequest,
  type PaymentResult,
  type RealtimeEventName,
  type RealtimeEvents,
  type SkyBubble,
  type SkyCluster,
  type SkyResponse,
  type Weather,
} from "../types";
import {
  HOUSEHOLD,
  P_SHORT,
  PERSONAS,
  SAFE_TO_SPEND,
  initialAccounts,
  initialBills,
  initialExpenses,
  splitEven,
  type MockExpense,
} from "./data";

const SESSION_KEY = "clearday.mock.session";
const LATENCY_MS = 220;

const state = {
  expenses: initialExpenses(),
  bills: initialBills(),
  accounts: initialAccounts(),
  payments: new Map<string, PaymentResult>(),
  nextPaymentId: 1,
  createdExpenses: new Map<string, CreateExpenseResult>(),
  nextExpenseId: 1,
};

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS));
}

function readSession(): string | null {
  try {
    return window.localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function writeSession(userId: string | null): void {
  try {
    if (userId) window.localStorage.setItem(SESSION_KEY, userId);
    else window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // Storage blocked: the session just won't survive a reload.
  }
}

function requireUser(): string {
  const userId = readSession();
  if (!userId || !PERSONAS.some((p) => p.user_id === userId)) {
    throw new ApiError(401, "Not signed in");
  }
  return userId;
}

function meFor(userId: string): Me {
  const persona = PERSONAS.find((p) => p.user_id === userId);
  return {
    user: { user_id: userId, display_name: persona?.display_name ?? "Roommate" },
    household: { ...HOUSEHOLD },
  };
}

// Server-side rule, duplicated here only because the mock plays the server.
function weatherFor(pShort: number): Weather {
  if (pShort >= 0.5) return "tight";
  if (pShort >= 0.2) return "watch";
  return "clear";
}

function fillOf(expense: MockExpense): { fill: number; paid: number } {
  const paidCents = expense.shares
    .filter((s) => s.status === "paid")
    .reduce((sum, s) => sum + s.amount_cents, 0);
  return {
    fill: paidCents / expense.total_cents,
    paid: expense.shares.filter((s) => s.status === "paid").length,
  };
}

function isCovered(expense: MockExpense): boolean {
  return expense.shares.every((s) => s.status === "paid");
}

function buildSky(userId: string): SkyResponse {
  const today = todayIso();
  const pShort = (id: string) => P_SHORT[userId]?.[id] ?? 0.05;
  const defaultAccount = state.accounts[userId]?.[0]?.account_id ?? null;

  const shared: SkyBubble[] = state.expenses
    .filter((e) => !isCovered(e))
    .flatMap((e) => {
      const mine = e.shares.find((s) => s.user_id === userId);
      if (!mine) return [];
      const { fill, paid } = fillOf(e);
      const p = mine.status === "paid" ? 0 : pShort(e.expense_id);
      return [
        {
          bubble_id: e.expense_id,
          kind: "shared",
          label: e.label,
          due_date: addDays(today, e.due_offset_days),
          your_share_cents: mine.amount_cents,
          total_cents: e.total_cents,
          status: mine.status,
          fill_fraction: fill,
          paid_count: paid,
          participant_count: e.shares.length,
          p_short: p,
          weather: weatherFor(p),
          necessity: e.necessity,
          expense_id: e.expense_id,
          share_id: mine.share_id,
          default_account_id: defaultAccount,
          cluster_id: null,
        } satisfies SkyBubble,
      ];
    });

  const personal: SkyBubble[] = state.bills
    .filter((b) => b.user_id === userId && b.status !== "paid")
    .map((b) => {
      const p = pShort(b.bubble_id);
      return {
        bubble_id: b.bubble_id,
        kind: "bill",
        label: b.label,
        due_date: addDays(today, b.due_offset_days),
        your_share_cents: b.amount_cents,
        total_cents: b.amount_cents,
        status: b.status,
        fill_fraction: 0,
        paid_count: 0,
        participant_count: 1,
        p_short: p,
        weather: weatherFor(p),
        necessity: b.necessity,
        expense_id: null,
        share_id: null,
        default_account_id: defaultAccount,
        cluster_id: b.cluster ? `cl_${userId}_${b.cluster}` : null,
      };
    });

  const bubbles = [...shared, ...personal].sort((a, b) => a.due_date.localeCompare(b.due_date));

  const clusterMap = new Map<string, string[]>();
  for (const b of bubbles) {
    if (b.cluster_id)
      clusterMap.set(b.cluster_id, [...(clusterMap.get(b.cluster_id) ?? []), b.bubble_id]);
  }
  const clusters: SkyCluster[] = [];
  for (const [cluster_id, bubble_ids] of clusterMap) {
    if (bubble_ids.length < 2) {
      // A cluster of one is just a bubble.
      for (const b of bubbles) if (b.cluster_id === cluster_id) b.cluster_id = null;
      continue;
    }
    clusters.push({ cluster_id, label: "Subscriptions", bubble_ids });
  }

  const safe = SAFE_TO_SPEND[userId] ?? { cents: 0, payday_offset_days: 7 };
  return {
    as_of: new Date().toISOString(),
    bubbles,
    clusters,
    safe_to_spend_cents: safe.cents,
    next_payday: addDays(today, safe.payday_offset_days),
  };
}

// --- Realtime bus -----------------------------------------------------------

type AnyHandler = (payload: unknown) => void;
const handlers = new Map<RealtimeEventName, Set<AnyHandler>>();

function emit<E extends RealtimeEventName>(event: E, payload: RealtimeEvents[E]): void {
  // Deliver after the HTTP-style response, like a socket push would.
  setTimeout(() => handlers.get(event)?.forEach((h) => h(payload)), 0);
}

export const mockRealtime: RealtimeClient = {
  on(event, handler) {
    const set = handlers.get(event) ?? new Set<AnyHandler>();
    set.add(handler as AnyHandler);
    handlers.set(event, set);
    return () => set.delete(handler as AnyHandler);
  },
};

// --- API --------------------------------------------------------------------

function findAccount(userId: string, accountId: string): Account {
  const account = state.accounts[userId]?.find((a) => a.account_id === accountId);
  if (!account) throw new ApiError(404, "Account not found");
  return account;
}

function pay(userId: string, req: PaymentRequest): PaymentResult {
  const replay = state.payments.get(req.idempotency_key);
  if (replay) return replay;

  const account = findAccount(userId, req.account_id);
  const payment_id = `pay_${state.nextPaymentId++}`;
  let result: PaymentResult;

  const expense = state.expenses.find((e) => e.expense_id === req.bubble_id);
  if (expense) {
    const share = expense.shares.find((s) => s.user_id === userId);
    if (!share || share.status === "paid") throw new ApiError(409, "Nothing left to pay");
    if (share.amount_cents !== req.amount_cents) throw new ApiError(409, "Amount changed");
    share.status = "paid";
    const { fill, paid } = fillOf(expense);
    result = {
      payment_id,
      bubble_id: expense.expense_id,
      status: "paid",
      fill_fraction: fill,
      paid_count: paid,
      popped: isCovered(expense),
    };
    emit("share.updated", {
      expense_id: expense.expense_id,
      share_id: share.share_id,
      status: "paid",
      fill_fraction: fill,
    });
    if (result.popped)
      emit("bubble.popped", { expense_id: expense.expense_id, label: expense.label });
  } else {
    const bill = state.bills.find((b) => b.bubble_id === req.bubble_id && b.user_id === userId);
    if (!bill || bill.status === "paid") throw new ApiError(409, "Nothing left to pay");
    if (bill.amount_cents !== req.amount_cents) throw new ApiError(409, "Amount changed");
    bill.status = "paid";
    result = {
      payment_id,
      bubble_id: bill.bubble_id,
      status: "paid",
      fill_fraction: 1,
      paid_count: 1,
      popped: true,
    };
  }

  account.balance_cents += account.type === "credit_card" ? req.amount_cents : -req.amount_cents;
  state.payments.set(req.idempotency_key, result);
  return result;
}

export const mockApi: ApiClient = {
  listDemoPersonas: () => delay(PERSONAS.map((p) => ({ ...p }))),
  loginAsPersona: async (userId) => {
    if (!PERSONAS.some((p) => p.user_id === userId)) throw new ApiError(404, "Unknown persona");
    writeSession(userId);
    return delay(meFor(userId));
  },
  logout: async () => {
    writeSession(null);
    return delay(undefined);
  },
  me: async () => {
    const userId = readSession();
    return delay(userId && PERSONAS.some((p) => p.user_id === userId) ? meFor(userId) : null);
  },
  getSky: async () => delay(buildSky(requireUser())),
  getAccounts: async () =>
    delay({ accounts: (state.accounts[requireUser()] ?? []).map((a) => ({ ...a })) }),
  pay: async (req) => {
    const userId = requireUser();
    return delay(pay(userId, req));
  },
  listHouseholdMembers: async () => {
    requireUser();
    return delay({
      members: PERSONAS.map((p) => ({ user_id: p.user_id, display_name: p.display_name })),
    });
  },
  createExpense: async (req) => {
    const userId = requireUser();
    return delay(createExpense(userId, req));
  },
};

// --- Shared expenses (mirrors POST /api/expenses) ---------------------------

function createExpense(userId: string, req: CreateExpenseRequest): CreateExpenseResult {
  const replay = state.createdExpenses.get(req.idempotency_key);
  if (replay) return replay;

  const label = req.label.trim();
  if (label.length < 1 || label.length > 80)
    throw new ApiError(422, "Label must be 1-80 characters");
  if (!Number.isInteger(req.total_cents) || req.total_cents <= 0)
    throw new ApiError(422, "total_cents must be positive integer cents");
  const ids = req.participants.map((p) => p.user_id);
  if (new Set(ids).size !== ids.length) throw new ApiError(422, "Participants must be unique");
  if (ids.some((id) => !PERSONAS.some((p) => p.user_id === id)))
    throw new ApiError(422, "Participants must be household members");
  if (!ids.some((id) => id !== userId))
    throw new ApiError(422, "Add at least one roommate besides you");

  let amounts: Map<string, number>;
  if (req.split_method === "even") {
    amounts = splitEven(req.total_cents, ids);
  } else if (req.split_method === "custom") {
    amounts = new Map();
    for (const p of req.participants) {
      if (!Number.isInteger(p.amount_cents) || (p.amount_cents ?? -1) < 0)
        throw new ApiError(422, "Custom amounts must be non-negative integer cents");
      amounts.set(p.user_id, p.amount_cents ?? 0);
    }
    const sum = [...amounts.values()].reduce((a, b) => a + b, 0);
    if (sum !== req.total_cents) throw new ApiError(422, "Custom amounts must add up to the total");
  } else {
    throw new ApiError(422, "Unknown split method");
  }

  const today = todayIso();
  const dueDate = req.due_date ?? today;
  const expense_id = `exp_new${state.nextExpenseId++}`;
  const shares = [...ids].sort().map((user_id) => ({
    share_id: `sh_${expense_id.slice(4)}_${user_id.slice(2)}`,
    user_id,
    amount_cents: amounts.get(user_id) ?? 0,
    status: (user_id === userId ? "paid" : "open") as "paid" | "open",
  }));
  const expense: MockExpense = {
    expense_id,
    label,
    total_cents: req.total_cents,
    due_offset_days: daysBetween(today, dueDate),
    necessity: "need",
    shares,
  };
  state.expenses.push(expense);

  const result: CreateExpenseResult = {
    expense_id,
    label,
    total_cents: req.total_cents,
    split_method: req.split_method,
    due_date: dueDate,
    payer_id: userId,
    shares: shares.map((s) => ({ ...s })),
  };
  state.createdExpenses.set(req.idempotency_key, result);

  const { fill } = fillOf(expense);
  for (const s of shares)
    emit("share.updated", {
      expense_id,
      share_id: s.share_id,
      status: s.status,
      fill_fraction: fill,
    });
  const actor = PERSONAS.find((p) => p.user_id === userId)?.display_name ?? "Roommate";
  emit("feed.created", {
    type: "expense_created",
    actor_display_name: actor,
    subject_label: label,
  });
  return result;
}
