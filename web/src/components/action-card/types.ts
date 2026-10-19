// Action card vocabulary follows CONTEXT.md.

export type PocketKind = "food" | "shopping" | "transport" | "leisure" | "bills" | "savings" | "other";

export type ActionCardState =
  | "pending"
  | "applying"
  | "applied"
  | "cancelled"
  | "replaced"
  | "out-of-date"
  | "failed"
  | "not-possible";

export type PocketChange = {
  pocketId: string;
  name: string;
  kind: PocketKind;
  /** Budget before and after, in whole baht. */
  before: number;
  after: number;
};

/** A proposed reallocation between pockets. Totals across `changes` must net to zero. */
export type BudgetChangeProposal = {
  id: string;
  kind: "budget-change";
  /** The flexible budget the percentages refer to, in whole baht. */
  flexibleBudget: number;
  changes: PocketChange[];
  /** Pockets the change does not touch, e.g. "Bills and Savings". */
  lockedPockets: string;
  assumptions: string[];
  /** One-line result shown once Applied, e.g. "Shopping is now ฿1,800". */
  appliedSummary: string;
};

/** Why a requested change cannot fit, and what would. */
export type NotPossibleDetail = {
  request: string;
  requested: number;
  canFree: number;
  reason: string;
  alternatives: { id: string; label: string; detail: string }[];
};

export type ActionCardHandlers = {
  onApprove: () => void;
  onEdit: () => void;
  onCancel: () => void;
  onRetry: () => void;
  onRecalculate: () => void;
  onUndo: () => void;
  onPickAlternative: (alternativeId: string) => void;
};
