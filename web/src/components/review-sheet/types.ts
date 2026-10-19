import type { PocketKind } from "@/components/action-card/types";

export type DocType = "receipt" | "bill" | "slip";
export type PaidStatus = "paid" | "unpaid" | "unsure";

export type ExtractedField = "docType" | "merchant" | "date" | "amount" | "pocket" | "paid";

/** What was read from an uploaded photo. Unknown values are null or empty, never guessed. */
export type ExtractedDocument = {
  docType: DocType;
  merchant: string;
  date: string;
  /** Bills only. */
  dueDate?: string;
  amount: number | null;
  pocket: PocketKind | null;
  paid: PaidStatus | null;
  reference?: string;
  /** Fields the reader was unsure about; shown with "Check this". */
  unsure: ExtractedField[];
  /** Payment slips that don't say what the money was for. */
  askPurpose?: boolean;
  /** An existing record this one looks like (Possible duplicate). */
  duplicateOf?: { merchant: string; date: string; amount: number; source: string };
  /** The photo could not be read; every field starts empty. */
  unreadable?: boolean;
};

/** What the user confirmed in the review sheet. */
export type ReviewedDocument = {
  docType: DocType;
  merchant: string;
  date: string;
  dueDate?: string;
  amount: number;
  pocket: PocketKind;
  paid: PaidStatus;
  purpose?: string;
};
