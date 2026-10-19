"use client";

// Review sheet (CONTEXT.md): check and correct what was read from a photo before saving.
// Layout chosen on the prototype/review-sheet branch (variant A): photo on top, every field
// editable at once, unsure fields marked "Check this".

import { AlertCircle, Copy, X, ZoomIn } from "lucide-react";
import { useEffect, useId, useState } from "react";
import type { PocketKind } from "@/components/action-card/types";
import { PocketTile } from "@/components/pocket-tile";
import { baht } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { DocType, ExtractedDocument, ExtractedField, PaidStatus, ReviewedDocument } from "./types";

const DOC_LABEL: Record<DocType, string> = { receipt: "Receipt", bill: "Bill", slip: "Payment slip" };
const PAID_LABEL: Record<PaidStatus, string> = { paid: "Paid", unpaid: "Not paid yet", unsure: "Not sure" };

export const POCKET_CHOICES: { kind: PocketKind; name: string }[] = [
  { kind: "food", name: "Food" },
  { kind: "transport", name: "Transport" },
  { kind: "shopping", name: "Shopping" },
  { kind: "leisure", name: "Leisure" },
  { kind: "bills", name: "Bills" },
  { kind: "other", name: "Other" },
];

type ReviewSheetProps = {
  doc: ExtractedDocument;
  /** Object URL of the uploaded photo, shown so the user can compare. */
  imageUrl?: string;
  onClose: () => void;
  onSave: (reviewed: ReviewedDocument) => void;
};

/** Parses what the user typed as an amount; null unless it is a positive number. */
function parseAmount(text: string): number | null {
  const n = Number(text.replace(/[,\s฿]/g, ""));
  return text.trim() !== "" && Number.isFinite(n) && n > 0 ? n : null;
}

const inputClass = "h-11 w-full rounded-xl bg-background px-3 text-base font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ink";

export function ReviewSheet({ doc, imageUrl, onClose, onSave }: ReviewSheetProps) {
  const id = useId();
  const [docType, setDocType] = useState(doc.docType);
  const [merchant, setMerchant] = useState(doc.merchant);
  const [date, setDate] = useState(doc.date);
  const [amountText, setAmountText] = useState(doc.amount === null ? "" : String(doc.amount));
  const [pocket, setPocket] = useState(doc.pocket);
  const [paid, setPaid] = useState(doc.paid);
  const [purpose, setPurpose] = useState("");
  const [zoom, setZoom] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const isBill = docType === "bill";
  const amount = parseAmount(amountText);
  const current: Record<ExtractedField, unknown> = { docType, merchant, date, amount, pocket, paid };
  // "Check this" stays until the user changes the value the reader was unsure about.
  const unsure = (f: ExtractedField) => doc.unsure.includes(f) && current[f] === doc[f];
  const missing = {
    merchant: merchant.trim() === "",
    amount: amount === null,
    pocket: pocket === null,
    paid: isBill && paid === null,
    purpose: !!doc.askPurpose && purpose.trim() === "",
  };
  const ready = !Object.values(missing).some(Boolean);

  const save = () => {
    if (!ready || amount === null || pocket === null) return;
    onSave({
      docType,
      merchant: merchant.trim(),
      date: date.trim(),
      dueDate: isBill ? doc.dueDate : undefined,
      amount,
      pocket,
      paid: isBill ? (paid ?? "unsure") : "paid",
      purpose: purpose.trim() || undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-center">
      <button type="button" aria-label="Close" tabIndex={-1} onClick={onClose} className="absolute inset-0 bg-ink/40" />
      <div role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} className="relative mt-auto flex max-h-[92dvh] w-full max-w-[430px] flex-col rounded-t-[28px] bg-background">
        <span className="mx-auto mt-2.5 h-1.5 w-10 rounded-full bg-[#d0d4da]" aria-hidden />
        <div className="flex items-center gap-3 px-[18px] pt-2 pb-2">
          <h2 id={`${id}-title`} className="text-lg font-extrabold">
            Check your {DOC_LABEL[docType].toLowerCase()}
          </h2>
          <button type="button" aria-label="Close" onClick={onClose} className="ml-auto grid size-11 place-items-center rounded-full bg-card shadow-[var(--shadow-card)]">
            <X className="size-5" aria-hidden />
          </button>
        </div>

        <div className="num min-h-0 flex-1 overflow-y-auto px-[18px] pb-4">
          <div className="flex flex-col gap-3">
            {imageUrl ? (
              <button type="button" onClick={() => setZoom((z) => !z)} aria-label={zoom ? "Shrink photo" : "Zoom photo"} className="relative block w-full overflow-hidden rounded-2xl bg-[#cfd6dc]">
                {/* eslint-disable-next-line @next/next/no-img-element -- local object URL, not optimisable */}
                <img src={imageUrl} alt="Your uploaded photo" className={cn("w-full object-contain transition-[height] motion-reduce:transition-none", zoom ? "h-[360px]" : "h-36")} />
                <span className="absolute right-2 bottom-2 flex items-center gap-1 rounded-full bg-card/90 px-2.5 py-1 text-xs font-semibold">
                  <ZoomIn className="size-3.5" aria-hidden />
                  {zoom ? "Shrink" : "Zoom"}
                </span>
              </button>
            ) : null}

            {doc.unreadable && (
              <div className="flex gap-3 rounded-2xl bg-card p-3 text-sm shadow-[var(--shadow-card)]" role="status">
                <AlertCircle className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
                <p>
                  <b>I couldn&apos;t read this photo.</b> Type the details below, or close and try a sharper photo.
                </p>
              </div>
            )}

            {doc.duplicateOf && (
              <div className="flex gap-3 rounded-2xl bg-card p-3 text-sm ring-2 ring-ink" role="status">
                <Copy className="mt-0.5 size-5 shrink-0" aria-hidden />
                <p>
                  <b>Possible duplicate.</b> {doc.duplicateOf.source}: {doc.duplicateOf.merchant}, {baht(doc.duplicateOf.amount)}. Save only if this is a different payment.
                </p>
              </div>
            )}

            <Field label="Type" unsure={unsure("docType")}>
              <Choices
                label="Document type"
                value={docType}
                onChange={setDocType}
                options={(Object.keys(DOC_LABEL) as DocType[]).map((k) => ({ value: k, label: DOC_LABEL[k] }))}
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Amount" htmlFor={`${id}-amount`} unsure={unsure("amount")} needed={missing.amount}>
                <div className="relative">
                  <span className="absolute top-1/2 left-3 -translate-y-1/2 font-semibold text-muted-foreground" aria-hidden>
                    ฿
                  </span>
                  <input id={`${id}-amount`} inputMode="decimal" value={amountText} onChange={(e) => setAmountText(e.target.value)} className={cn(inputClass, "pl-7")} />
                </div>
              </Field>
              <Field label={isBill ? "Issued" : "Date"} htmlFor={`${id}-date`} unsure={unsure("date")}>
                <input id={`${id}-date`} value={date} placeholder="Today" onChange={(e) => setDate(e.target.value)} className={inputClass} />
              </Field>
            </div>

            <Field label={docType === "slip" ? "Paid to" : "Shop or company"} htmlFor={`${id}-merchant`} unsure={unsure("merchant")} needed={missing.merchant}>
              <input id={`${id}-merchant`} value={merchant} onChange={(e) => setMerchant(e.target.value)} className={inputClass} />
            </Field>

            {doc.askPurpose && (
              <Field label="What was this payment for?" htmlFor={`${id}-purpose`} unsure={missing.purpose}>
                <input id={`${id}-purpose`} value={purpose} placeholder="e.g. my share of dinner" onChange={(e) => setPurpose(e.target.value)} className={inputClass} />
              </Field>
            )}

            <Field label="Pocket" unsure={unsure("pocket")} needed={missing.pocket}>
              <Choices
                label="Pocket"
                value={pocket}
                onChange={setPocket}
                options={POCKET_CHOICES.map((p) => ({ value: p.kind, label: p.name, icon: <PocketTile kind={p.kind} size={24} /> }))}
              />
            </Field>

            {isBill && (
              <Field label={doc.dueDate ? `Paid? Due ${doc.dueDate}` : "Paid?"} unsure={unsure("paid")} needed={missing.paid}>
                <Choices
                  label="Payment status"
                  value={paid}
                  onChange={setPaid}
                  options={(Object.keys(PAID_LABEL) as PaidStatus[]).map((k) => ({ value: k, label: PAID_LABEL[k] }))}
                />
                {paid !== null && paid !== "paid" && amount !== null && (
                  <p className="mt-2 text-[13px] text-muted-foreground">I&apos;ll keep {baht(amount)} out of Safe to spend until you mark it paid.</p>
                )}
              </Field>
            )}
          </div>
        </div>

        <div className="border-t border-line bg-card px-[18px] pt-3 pb-[max(14px,env(safe-area-inset-bottom))]">
          {!ready && <p className="mb-2 text-center text-[13px] text-muted-foreground">Fill in the marked fields to save.</p>}
          <div className="grid grid-cols-[1fr_auto] gap-2.5">
            <button type="button" disabled={!ready} onClick={save} className="min-h-[52px] rounded-[var(--radius-ctl)] bg-ink text-[15px] font-bold text-white disabled:opacity-40">
              Save
            </button>
            <button type="button" onClick={onClose} className="min-h-[52px] rounded-[var(--radius-ctl)] bg-background px-5 text-[15px] font-bold">
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  unsure,
  needed,
  htmlFor,
  children,
}: {
  label: string;
  unsure?: boolean;
  /** Required and still empty. */
  needed?: boolean;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  const flag = unsure || needed;
  return (
    <div className={cn("rounded-2xl bg-card p-3", flag ? "ring-2 ring-ink" : "shadow-[var(--shadow-card)]")}>
      <div className="mb-2 flex items-center justify-between gap-2">
        {htmlFor ? (
          <label htmlFor={htmlFor} className="text-[13px] font-semibold text-muted-foreground">
            {label}
          </label>
        ) : (
          <span className="text-[13px] font-semibold text-muted-foreground">{label}</span>
        )}
        {unsure ? <Tag>Check this</Tag> : needed ? <Tag>Needed</Tag> : null}
      </div>
      {children}
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full bg-ink px-2 py-0.5 text-[11px] font-bold text-white">{children}</span>;
}

function Choices<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string; icon?: React.ReactNode }[];
  value: T | null;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={cn(
              "flex min-h-11 items-center gap-2 rounded-full border-2 px-3.5 text-sm font-semibold transition-colors motion-reduce:transition-none",
              on ? "border-ink bg-ink text-white" : "border-transparent bg-background",
            )}
          >
            {o.icon}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
