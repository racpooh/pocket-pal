import type { PocketKind } from "@/components/action-card/types";

export type Transaction = {
  id: string;
  /** Day label used for grouping, e.g. "Today", "Oct 14". */
  day: string;
  merchant: string;
  /** Null until the user picks one (e.g. a personal transfer). */
  pocket: PocketKind | null;
  pocketName: string | null;
  /** Negative for money out, positive for money in. */
  amount: number;
  source: string;
  /** Needs review: kept out of totals until confirmed. */
  needsReview?: boolean;
  /** Personal transfers don't say what they were for. */
  askPurpose?: boolean;
  possibleDuplicateOf?: { merchant: string; date: string; amount: number; source: string };
  version: number;
  occurredDate: string;
  occurredAt: string | null;
  categoryCode: string | null;
  paymentStatus: string;
  kind: string;
};

export type UpcomingBill = {
  id: string;
  provider: string;
  amount: number;
  due: string;
  daysUntilDue: number;
  status: "unpaid" | "paid";
  /** Change vs the last comparable bill, when there is one. */
  changeVsLast?: number;
};
