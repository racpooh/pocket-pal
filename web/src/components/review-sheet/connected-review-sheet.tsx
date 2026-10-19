"use client";

import { AlertCircle, Copy, Loader2, X, ZoomIn } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export type ReviewDecision = "accept" | "not_a_transaction" | "duplicate_of" | "link_receipt" | "distinct";
export type ReviewCandidate = {
  txn_id: string;
  kind: string;
  amount_satang: number;
  occurred_date: string;
  payee_display: string | null;
  source: string;
};
export type ReviewItem = {
  id: string;
  upload_id: string;
  reason: string;
  problem_fields: string[];
  extracted: Record<string, string | null>;
  allowed_decisions: ReviewDecision[];
  candidates: ReviewCandidate[];
};
export type ReviewResolution = { decision: ReviewDecision; txn_id?: string; bill_id?: string };

type Props = { item: ReviewItem; imageUrl?: string; onClose: () => void; onResolved: (result: ReviewResolution) => void };
const inputClass = "h-11 w-full rounded-xl bg-background px-3 text-base font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ink";
const labels: Record<ReviewDecision, string> = {
  accept: "Save record",
  distinct: "Save as a separate record",
  duplicate_of: "Attach to existing record",
  link_receipt: "Link receipt to existing payment",
  not_a_transaction: "Not a transaction",
};
const docLabels: Record<string, string> = {
  transfer_out: "Money sent", transfer_in: "Money received", receipt: "Receipt", bill: "Unpaid bill",
};
const statuses = ["success", "pending", "failed", "scheduled", "unknown"];
function formatSatang(value: number) {
  const sign = value < 0 ? "−" : "";
  const digits = String(Math.abs(value));
  const whole = (digits.length > 2 ? digits.slice(0, -2) : "0").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${sign}฿${whole}.${digits.slice(-2).padStart(2, "0")}`;
}

export function ConnectedReviewSheet({ item, imageUrl, onClose, onResolved }: Props) {
  const id = useId();
  imageUrl = imageUrl || `/api/backend/uploads/${item.upload_id}/image`;
  const extracted = item.extracted || {};
  const [docType, setDocType] = useState(extracted.doc_type || "");
  const [amount, setAmount] = useState(extracted.amount_text || "");
  const [time, setTime] = useState(extracted.time_text || "");
  const [date, setDate] = useState(extracted.date_text || "");
  const [payee, setPayee] = useState(extracted.payee || "");
  const [status, setStatus] = useState(extracted.status || "unknown");
  const [dueDate, setDueDate] = useState(extracted.due_date_text || "");
  const [candidateId, setCandidateId] = useState(item.candidates?.length === 1 ? item.candidates[0].txn_id : "");
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(false);
  const [decision, setDecision] = useState<ReviewDecision>(item.allowed_decisions.includes("accept") ? "accept" : item.allowed_decisions[0]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const savesNew = decision === "accept" || decision === "distinct";
  const linksExisting = decision === "duplicate_of" || decision === "link_receipt";
  const amountValid = /^\d+(?:,\d{3})*(?:\.\d{1,2})?$/.test(amount.trim()) && /[1-9]/.test(amount);
  const canSubmit = !busy && !stale && (!linksExisting || !!candidateId) && (!savesNew || (
    !!docType && !!date.trim() && amountValid &&
    (docType === "bill" ? !!dueDate.trim() : docType === "receipt" || status !== "unknown")
  ));

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const fields = savesNew ? {
        doc_type: docType,
        amount_text: amount.trim(),
        amount_text_second: null,
        date_text: date.trim(),
        time_text: time.trim() || null,
        payee: payee.trim() || null,
        status: docType === "receipt" || docType === "bill" ? null : status,
        due_date_text: docType === "bill" ? dueDate.trim() : null,
        readability: "clear",
      } : undefined;
      const result = await api<ReviewResolution>(`/review-items/${item.id}/resolve`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, fields, txn_id: linksExisting ? candidateId : null }),
      });
      onResolved(result);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404) setStale(true);
      setError(cause instanceof Error ? cause.message : "Could not save this review. Please try again.");
    } finally { setBusy(false); }
  };

  return <div className="fixed inset-0 z-40 flex justify-center">
    <button type="button" aria-label="Close" tabIndex={-1} onClick={onClose} className="absolute inset-0 bg-ink/40" />
    <div role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} className="relative mt-auto flex max-h-[92dvh] w-full max-w-[430px] flex-col rounded-t-[28px] bg-background">
      <span className="mx-auto mt-2.5 h-1.5 w-10 rounded-full bg-[#d0d4da]" aria-hidden />
      <div className="flex items-center gap-3 px-[18px] pt-2 pb-2">
        <h2 id={`${id}-title`} className="text-lg font-extrabold">Check this photo</h2>
        <button type="button" aria-label="Close" disabled={busy} onClick={onClose} className="ml-auto grid size-11 place-items-center rounded-full bg-card shadow-[var(--shadow-card)]"><X className="size-5" /></button>
      </div>
      <div className="num min-h-0 flex-1 space-y-3 overflow-y-auto px-[18px] pb-4">
        {imageUrl && <button type="button" onClick={() => setZoom(!zoom)} className="relative block w-full overflow-hidden rounded-2xl bg-[#cfd6dc]" aria-label={zoom ? "Shrink photo" : "Zoom photo"}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imageUrl} alt="Photo under review" className={cn("w-full object-contain", zoom ? "h-[360px]" : "h-36")} />
          <span className="absolute right-2 bottom-2 flex items-center gap-1 rounded-full bg-card/90 px-2.5 py-1 text-xs font-semibold"><ZoomIn className="size-3.5" />{zoom ? "Shrink" : "Zoom"}</span>
        </button>}
        <div className="flex gap-3 rounded-2xl bg-card p-3 text-sm shadow-[var(--shadow-card)]" role="status">
          <AlertCircle className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
          <p><b>Review needed.</b> {item.reason.replaceAll("_", " ")}. {item.problem_fields.length ? `Check: ${item.problem_fields.join(", ")}.` : "Compare the photo before deciding."}</p>
        </div>
        {item.candidates?.length > 0 && <div className="rounded-2xl bg-card p-3 shadow-[var(--shadow-card)]">
          <div className="mb-2 flex items-center gap-2 text-sm font-bold"><Copy className="size-4" />Possible existing records</div>
          {item.candidates.map((candidate) => <label key={candidate.txn_id} className="flex min-h-11 items-center gap-2 text-sm">
            <input type="radio" name={`${id}-candidate`} checked={candidateId === candidate.txn_id} onChange={() => setCandidateId(candidate.txn_id)} />
            <span>{candidate.payee_display || "Unknown payee"} · {formatSatang(candidate.amount_satang)} · {candidate.occurred_date} · {candidate.source}</span>
          </label>)}
        </div>}
        <Field label="Decision"><div role="radiogroup" aria-label="Decision" className="flex flex-wrap gap-2">{item.allowed_decisions.map((option) => <button key={option} type="button" role="radio" aria-checked={decision === option} onClick={() => setDecision(option)} className={cn("min-h-11 rounded-full border-2 px-3 text-sm font-semibold", decision === option ? "border-ink bg-ink text-white" : "border-transparent bg-background")}>{labels[option]}</button>)}</div></Field>
        {savesNew && <>
          <Field label="Type and direction" needed={!docType}><select value={docType} onChange={(event) => setDocType(event.target.value)} className={inputClass}><option value="">Choose type</option>{Object.entries(docLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Amount (THB)" needed={!amountValid}><input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} className={inputClass} placeholder="0.00" /></Field>
            <Field label={docType === "bill" ? "Issued date" : "Date"} needed={!date.trim()}><input value={date} onChange={(event) => setDate(event.target.value)} className={inputClass} placeholder="YYYY-MM-DD" /></Field>
          </div>
          <Field label="Time"><input value={time} onChange={(event) => setTime(event.target.value)} className={inputClass} placeholder="HH:MM" /></Field>
          <Field label={docType === "transfer_in" ? "Sent by" : "Shop, company, or paid to"}><input value={payee} onChange={(event) => setPayee(event.target.value)} className={inputClass} /></Field>
          {docType === "bill" ? <Field label="Due date" needed={!dueDate.trim()}><input value={dueDate} onChange={(event) => setDueDate(event.target.value)} className={inputClass} placeholder="YYYY-MM-DD" /></Field> : docType !== "receipt" && <Field label="Payment status" needed={status === "unknown"}><select value={status} onChange={(event) => setStatus(event.target.value)} className={inputClass}>{statuses.map((value) => <option key={value} value={value}>{value}</option>)}</select></Field>}
          <p className="text-[13px] text-muted-foreground">The amount, date, direction, and payment status affect your totals. Confirm them against the photo.</p>
        </>}
        {error && <p role="alert" className="rounded-2xl bg-danger-soft p-3 text-sm text-danger">{error}</p>}
      </div>
      <div className="border-t border-line bg-card px-[18px] pt-3 pb-[max(14px,env(safe-area-inset-bottom))]">
        <div className="grid grid-cols-[1fr_auto] gap-2.5">
          <button type="button" disabled={!canSubmit} onClick={submit} className="min-h-[52px] rounded-[var(--radius-ctl)] bg-ink px-4 text-[15px] font-bold text-white disabled:opacity-40">{busy ? <Loader2 className="mx-auto size-5 animate-spin" /> : labels[decision]}</button>
          <button type="button" onClick={onClose} disabled={busy} className="min-h-[52px] rounded-[var(--radius-ctl)] bg-background px-5 text-[15px] font-bold">Cancel</button>
        </div>
      </div>
    </div>
  </div>;
}

function Field({ label, needed, children }: { label: string; needed?: boolean; children: React.ReactNode }) {
  return <div className={cn("rounded-2xl bg-card p-3", needed ? "ring-2 ring-ink" : "shadow-[var(--shadow-card)]")}><div className="mb-2 flex justify-between text-[13px] font-semibold text-muted-foreground"><span>{label}</span>{needed && <span className="rounded-full bg-ink px-2 py-0.5 text-[11px] text-white">Needed</span>}</div>{children}</div>;
}
