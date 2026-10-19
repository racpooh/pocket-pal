import type { PocketKind } from "@/components/action-card/types";

export type PlanResponse = {
  today: string;
  cashflow: {
    available_balance_satang: number;
    discretionary_satang: number;
    daily_allowance_satang: number;
    shortage_satang: number;
  };
  plan: null | { id: string; period_start: string; period_end: string };
  pockets: PocketStatus[];
};

export type PocketStatus = {
  pocket_id: string | null;
  name: string;
  allocation_satang: number | null;
  spent_confirmed_satang: number | null;
  spent_predicted_satang: number | null;
  unassigned_satang?: number;
  excluded_unresolved_count?: number;
};

export type PocketDefinition = { pocket_id: string; name: string; categories: string[] };
export type SpendingReport = { total_satang: number; excluded_unresolved_count: number; unlinked_refunds_satang: number };
export type Profile = { timezone: string; income: null | { next_income_date: string } };
export type TxnRecord = {
  id: string; version: number; kind: "expense" | "income" | "refund" | "transfer_out" | "transfer_in";
  amount_satang: number; occurred_date: string; occurred_at: string | null;
  payee_display: string | null; category_code: string | null; category_state: string;
  payment_status: string; source: string; description: string | null;
};
export type BillRecord = { id: string; biller: string; amount_due_satang: number; due_date: string; status: "paid" | "unpaid" | "cancelled"; paid_by_txn_id: string | null };

/** The legacy UI accepts baht; all calculations remain integer satang until this display boundary. */
export function displayBaht(satang: number): number { return satang / 100; }

export function pocketKind(categories: string[], name: string): PocketKind {
  const keys = [...categories, name.toLowerCase()];
  if (keys.includes("food")) return "food";
  if (keys.includes("transport")) return "transport";
  if (keys.includes("shopping")) return "shopping";
  if (keys.includes("entertainment") || keys.includes("leisure")) return "leisure";
  if (keys.includes("bills")) return "bills";
  if (keys.includes("savings")) return "savings";
  return "other";
}

export function categoryKind(category: string | null): PocketKind | null {
  if (!category) return null;
  return pocketKind([category], category);
}

export function nextDay(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10);
}

export function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(year, month - 1, day)));
}
