/**
 * Apartment 4B demo fixtures for the mock API. Dates are offsets from today so
 * the sky always looks current. All money is integer cents.
 */
import type { Account, Cents, DemoPersona, Necessity, ShareStatus } from "../types";

export const HOUSEHOLD = { household_id: "hh_4b", name: "Apartment 4B" } as const;

export const PERSONAS: DemoPersona[] = [
  { user_id: "u_maya", display_name: "Maya", tagline: "Night-shift nurse, plans everything" },
  { user_id: "u_jake", display_name: "Jake", tagline: "Grad student, pays rent first" },
  { user_id: "u_priya", display_name: "Priya", tagline: "Designer, does the grocery runs" },
];

export interface MockShare {
  share_id: string;
  user_id: string;
  amount_cents: Cents;
  status: ShareStatus;
}

export interface MockExpense {
  expense_id: string;
  label: string;
  total_cents: Cents;
  due_offset_days: number;
  necessity: Necessity;
  shares: MockShare[];
}

export interface MockBill {
  bubble_id: string;
  user_id: string;
  label: string;
  amount_cents: Cents;
  due_offset_days: number;
  necessity: Necessity;
  status: ShareStatus;
  cluster: "subscriptions" | null;
}

/**
 * Even split with the largest-remainder method, ties broken by user ID. Mirrors
 * analytics/splits.py so the fixtures reconcile to the cent.
 */
export function splitEven(totalCents: Cents, userIds: string[]): Map<string, Cents> {
  const sorted = [...userIds].sort();
  const base = Math.floor(totalCents / sorted.length);
  let leftover = totalCents - base * sorted.length;
  const result = new Map<string, Cents>();
  for (const id of sorted) {
    const extra = leftover > 0 ? 1 : 0;
    leftover -= extra;
    result.set(id, base + extra);
  }
  return result;
}

const ROOMMATES = PERSONAS.map((p) => p.user_id);

function sharedExpense(
  expense_id: string,
  label: string,
  total_cents: Cents,
  due_offset_days: number,
  paidBy: string[],
): MockExpense {
  const amounts = splitEven(total_cents, ROOMMATES);
  return {
    expense_id,
    label,
    total_cents,
    due_offset_days,
    necessity: "need",
    shares: ROOMMATES.map((user_id) => ({
      share_id: `sh_${expense_id.slice(4)}_${user_id.slice(2)}`,
      user_id,
      amount_cents: amounts.get(user_id) ?? 0,
      status: paidBy.includes(user_id) ? "paid" : "open",
    })),
  };
}

export function initialExpenses(): MockExpense[] {
  return [
    sharedExpense("exp_rent", "Rent", 180_000, 6, ["u_jake"]),
    sharedExpense("exp_electric", "Duke Energy electric", 12_850, 3, []),
    sharedExpense("exp_internet", "Home internet", 7_999, 9, ["u_priya"]),
    sharedExpense("exp_groceries", "Harris Teeter groceries", 8_642, 2, ["u_priya", "u_jake"]),
  ];
}

function bill(
  user_id: string,
  key: string,
  label: string,
  amount_cents: Cents,
  due_offset_days: number,
  necessity: Necessity,
  cluster: MockBill["cluster"] = null,
): MockBill {
  return {
    bubble_id: `bill_${user_id.slice(2)}_${key}`,
    user_id,
    label,
    amount_cents,
    due_offset_days,
    necessity,
    status: "open",
    cluster,
  };
}

export function initialBills(): MockBill[] {
  return [
    bill("u_maya", "car", "Car insurance", 11_200, 1, "need"),
    bill("u_maya", "card", "Cashback card payment", 3_500, 12, "need"),
    bill("u_maya", "spotify", "Spotify", 1_199, 4, "want", "subscriptions"),
    bill("u_maya", "netflix", "Netflix", 1_549, 11, "want", "subscriptions"),
    bill("u_maya", "icloud", "iCloud+", 299, 16, "want", "subscriptions"),
    bill("u_jake", "phone", "Phone plan", 4_500, 5, "need"),
    bill("u_jake", "gym", "Gym membership", 3_999, 8, "want"),
    bill("u_jake", "spotify", "Spotify", 1_199, 4, "want", "subscriptions"),
    bill("u_jake", "hulu", "Hulu", 999, 14, "want", "subscriptions"),
    bill("u_priya", "loan", "Student loan", 21_000, 10, "need"),
    bill("u_priya", "netflix", "Netflix", 1_549, 7, "want", "subscriptions"),
    bill("u_priya", "disney", "Disney+", 1_399, 13, "want", "subscriptions"),
  ];
}

/** Forecast probability of a shortfall before each bubble's due date. Default 0.05. */
export const P_SHORT: Record<string, Record<string, number>> = {
  u_maya: {
    bill_maya_car: 0.62,
    exp_electric: 0.31,
    exp_rent: 0.41,
    bill_maya_card: 0.24,
    bill_maya_netflix: 0.22,
  },
  u_jake: { bill_jake_gym: 0.27 },
  u_priya: { bill_priya_loan: 0.36 },
};

export const SAFE_TO_SPEND: Record<string, { cents: Cents; payday_offset_days: number }> = {
  u_maya: { cents: 4_120, payday_offset_days: 5 },
  u_jake: { cents: 38_550, payday_offset_days: 8 },
  u_priya: { cents: 21_075, payday_offset_days: 3 },
};

export function initialAccounts(): Record<string, Account[]> {
  const make = (
    user: string,
    last4s: [string, string, string],
    balances: [Cents, Cents, Cents],
  ) => [
    {
      account_id: `acct_${user}_chk`,
      type: "checking" as const,
      nickname: "Everyday Checking",
      last4: last4s[0],
      balance_cents: balances[0],
    },
    {
      account_id: `acct_${user}_sav`,
      type: "savings" as const,
      nickname: "Rainy Day Savings",
      last4: last4s[1],
      balance_cents: balances[1],
    },
    {
      account_id: `acct_${user}_cc`,
      type: "credit_card" as const,
      nickname: "Cashback Card",
      last4: last4s[2],
      balance_cents: balances[2],
    },
  ];
  return {
    u_maya: make("maya", ["4821", "0937", "5530"], [84_215, 32_000, 41_890]),
    u_jake: make("jake", ["1174", "6620", "3049"], [196_340, 120_500, 8_812]),
    u_priya: make("priya", ["7702", "2288", "9915"], [143_980, 61_250, 22_406]),
  };
}
