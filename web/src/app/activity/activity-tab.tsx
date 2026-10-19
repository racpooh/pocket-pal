"use client";

import { useCallback, useEffect, useState } from "react";
import type { PocketKind } from "@/components/action-card/types";
import { TransactionList } from "@/components/activity/transaction-list";
import type { Transaction, UpcomingBill } from "@/components/activity/types";
import { UpcomingBills } from "@/components/activity/upcoming-bills";
import { ConnectedReviewSheet, type ReviewItem } from "@/components/review-sheet/connected-review-sheet";
import { TabBar } from "@/components/tab-bar";
import { api } from "@/lib/api";
import { categoryKind, displayBaht, formatDate, type BillRecord, type TxnRecord } from "@/lib/dashboard";
import { cn } from "@/lib/utils";

type Filter = "all" | "review" | PocketKind;
type ActivityData = { transactions: TxnRecord[]; bills: BillRecord[]; reviews: ReviewItem[] };
const categories = [
  { code: "food", label: "Food" }, { code: "transport", label: "Transport" }, { code: "shopping", label: "Shopping" },
  { code: "entertainment", label: "Leisure" }, { code: "bills", label: "Bills" }, { code: "health", label: "Health" },
  { code: "education", label: "Education" }, { code: "travel", label: "Travel" }, { code: "transfer_people", label: "Transfers" },
  { code: "other", label: "Other" },
];
const kindName: Record<PocketKind, string> = { food: "Food", transport: "Transport", shopping: "Shopping", leisure: "Leisure", bills: "Bills", savings: "Savings", other: "Other" };
const sourceLabel = (source: string) => source === "manual" ? "manual" : source;
function parseSatang(value: string): number | null {
  const clean = value.trim().replace(/,/g, "");
  if (!/^\d+(?:\.\d{1,2})?$/.test(clean)) return null;
  const [whole, cents = ""] = clean.split(".");
  const satang = Number(whole) * 100 + Number(cents.padEnd(2, "0"));
  return Number.isSafeInteger(satang) && satang > 0 ? satang : null;
}
function showAmount(satang: number): string { return (satang / 100).toFixed(2); }
function toTransaction(t: TxnRecord): Transaction {
  const pocket = categoryKind(t.category_code);
  return { id: t.id, day: formatDate(t.occurred_date), merchant: t.payee_display || t.description || "Unnamed transaction",
    pocket, pocketName: t.category_code ? (categories.find((c) => c.code === t.category_code)?.label ?? t.category_code) : null,
    amount: displayBaht(t.kind === "income" || t.kind === "refund" || t.kind === "transfer_in" ? t.amount_satang : -t.amount_satang),
    source: sourceLabel(t.source), needsReview: t.category_state === "unclassified" || t.payment_status === "unknown",
    version: t.version, occurredDate: t.occurred_date, occurredAt: t.occurred_at, categoryCode: t.category_code,
    paymentStatus: t.payment_status, kind: t.kind };
}
function toBill(b: BillRecord): UpcomingBill {
  const today = new Date(); const due = new Date(`${b.due_date}T00:00:00+07:00`);
  const days = Math.ceil((due.getTime() - today.getTime()) / 86400000);
  return { id: b.id, provider: b.biller, amount: displayBaht(b.amount_due_satang), due: formatDate(b.due_date), daysUntilDue: days, status: b.status === "paid" ? "paid" : "unpaid" };
}

function TransactionEditor({ transaction, onClose, onSaved }: { transaction: TxnRecord; onClose: () => void; onSaved: () => void }) {
  const [payee, setPayee] = useState(transaction.payee_display ?? "");
  const [amount, setAmount] = useState(showAmount(transaction.amount_satang));
  const [date, setDate] = useState(transaction.occurred_date);
  const [category, setCategory] = useState(transaction.category_code ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const parsed = parseSatang(amount);
  async function save() {
    if (!parsed || busy) return;
    const changes: Record<string, unknown> = {};
    if (payee.trim() !== (transaction.payee_display ?? "")) changes.payee_display = payee.trim() || null;
    if (parsed !== transaction.amount_satang) changes.amount_satang = parsed;
    if (date !== transaction.occurred_date) { changes.occurred_date = date; changes.occurred_at = null; }
    if (category && category !== transaction.category_code) changes.category = category;
    if (!Object.keys(changes).length) { onClose(); return; }
    setBusy(true); setError(null);
    try {
      await api(`/transactions/${transaction.id}`, { method: "PATCH", body: JSON.stringify({ version: transaction.version, changes }) });
      onSaved();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save this correction."); }
    finally { setBusy(false); }
  }
  return <div className="fixed inset-0 z-40 flex justify-center bg-ink/40">
    <div role="dialog" aria-modal="true" aria-label="Correct transaction" className="relative mt-auto flex max-h-[92dvh] w-full max-w-[430px] flex-col overflow-y-auto rounded-t-[28px] bg-background p-[18px] pb-[max(18px,env(safe-area-inset-bottom))]">
      <div className="flex items-center justify-between"><h2 className="text-lg font-extrabold">Correct transaction</h2><button type="button" onClick={onClose} className="min-h-11 px-3 font-bold">Close</button></div>
      <p className="mb-3 text-sm text-muted-foreground">{transaction.kind.replaceAll("_", " ")} · {transaction.source} · {transaction.payment_status}</p>
      <label className="mb-3 text-sm font-semibold">Payee<input value={payee} onChange={(e) => setPayee(e.target.value)} maxLength={120} className="mt-1 h-11 w-full rounded-xl bg-card px-3" /></label>
      <div className="mb-3 grid grid-cols-2 gap-3">
        <label className="text-sm font-semibold">Amount (฿)<input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" className="mt-1 h-11 w-full rounded-xl bg-card px-3" /></label>
        <label className="text-sm font-semibold">Date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="mt-1 h-11 w-full rounded-xl bg-card px-3" /></label>
      </div>
      <label className="mb-3 text-sm font-semibold">Category<select value={category} onChange={(e) => setCategory(e.target.value)} className="mt-1 h-11 w-full rounded-xl bg-card px-3"><option value="">Uncategorised</option>{categories.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}</select></label>
      {error && <p role="alert" className="mb-3 rounded-xl bg-danger-soft p-3 text-sm">{error}</p>}
      <button type="button" onClick={() => void save()} disabled={!parsed || busy} className="min-h-[52px] rounded-[var(--radius-ctl)] bg-ink font-bold text-white disabled:opacity-50">{busy ? "Saving…" : "Save correction"}</button>
    </div>
  </div>;
}

function BillPayment({ bill, transactions, onClose, onSaved }: { bill: BillRecord; transactions: TxnRecord[]; onClose: () => void; onSaved: () => void }) {
  const matching = transactions.filter((t) => t.kind === "expense" && t.payment_status === "completed" && t.amount_satang === bill.amount_due_satang);
  const [txnId, setTxnId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function link() {
    if (!txnId || busy) return;
    setBusy(true); setError(null);
    try { await api(`/bills/${bill.id}/link-payment`, { method: "POST", body: JSON.stringify({ txn_id: txnId }) }); onSaved(); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not link this payment."); }
    finally { setBusy(false); }
  }
  return <div className="fixed inset-0 z-40 flex justify-center bg-ink/40"><div role="dialog" aria-modal="true" aria-label="Link bill payment" className="relative mt-auto w-full max-w-[430px] rounded-t-[28px] bg-background p-[18px] pb-[max(18px,env(safe-area-inset-bottom))]">
    <div className="flex items-center justify-between"><h2 className="text-lg font-extrabold">Link payment</h2><button type="button" onClick={onClose} className="min-h-11 px-3 font-bold">Close</button></div>
    <p className="mb-3 text-sm">Select the recorded payment for {bill.biller}. Its amount must match the bill exactly.</p>
    {matching.length ? <select aria-label="Matching expense" value={txnId} onChange={(e) => setTxnId(e.target.value)} className="mb-3 h-11 w-full rounded-xl bg-card px-3"><option value="">Choose a payment</option>{matching.map((t) => <option key={t.id} value={t.id}>{formatDate(t.occurred_date)} · {t.payee_display || "Expense"} · ฿{showAmount(t.amount_satang)}</option>)}</select> : <p className="mb-3 rounded-xl bg-card p-3 text-sm text-muted-foreground">No matching completed expense is in the recent activity list. Record or import the payment first, then return here.</p>}
    {error && <p role="alert" className="mb-3 rounded-xl bg-danger-soft p-3 text-sm">{error}</p>}
    <button type="button" disabled={!txnId || busy} onClick={() => void link()} className="min-h-[52px] w-full rounded-[var(--radius-ctl)] bg-ink font-bold text-white disabled:opacity-50">{busy ? "Linking…" : "Mark paid with this payment"}</button>
  </div></div>;
}

export function ActivityTab() {
  const [data, setData] = useState<ActivityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [openTxn, setOpenTxn] = useState<TxnRecord | null>(null);
  const [openBill, setOpenBill] = useState<BillRecord | null>(null);
  const [openReview, setOpenReview] = useState<ReviewItem | null>(null);
  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [transactions, bills, reviews] = await Promise.all([
        api<TxnRecord[]>("/transactions"), api<BillRecord[]>("/bills"), api<{ items: ReviewItem[] }>("/review-items"),
      ]);
      setData({ transactions, bills: bills.filter((b) => b.status !== "cancelled"), reviews: reviews.items });
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load activity."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const txns = data?.transactions.map(toTransaction) ?? [];
  const reviewCount = data?.reviews.length ?? 0;
  const filters: { key: Filter; label: string }[] = [
    { key: "all", label: "All" }, { key: "review", label: `Needs review (${reviewCount})` },
    ...(["food", "transport", "shopping", "leisure", "bills", "other"] as PocketKind[]).map((k) => ({ key: k, label: kindName[k] })),
  ];
  const shown = txns.filter((t) => filter === "all" ? true : filter === "review" ? false : t.pocket === filter);
  function saved(message: string) { setOpenTxn(null); setOpenBill(null); setOpenReview(null); setNotice(message); void refresh(); }

  return <div className="mx-auto flex min-h-dvh w-full max-w-[430px] flex-col bg-background">
    <main className="flex flex-1 flex-col gap-3.5 px-[18px] pt-[max(16px,env(safe-area-inset-top))] pb-6">
      <div className="flex items-center justify-between"><h1 className="pt-1.5 text-2xl leading-[30px] font-extrabold tracking-tight">Activity</h1><button type="button" disabled={loading} onClick={() => void refresh()} className="min-h-11 px-3 text-sm font-semibold underline disabled:opacity-40">Refresh</button></div>
      {notice && <p role="status" className="rounded-2xl bg-mint-soft px-3.5 py-3 text-sm font-semibold">{notice}</p>}
      {loading && <p role="status" className="rounded-2xl bg-card p-4 text-sm">Loading activity…</p>}
      {error && <p role="alert" className="rounded-2xl bg-card p-4 text-sm">{error} <button type="button" onClick={() => void refresh()} className="font-bold underline">Retry</button></p>}
      {data && <>
        {filter === "all" && <UpcomingBills bills={data.bills.map(toBill)} onOpen={(b) => setOpenBill(data.bills.find((x) => x.id === b.id) ?? null)} />}
        <div role="radiogroup" aria-label="Show" className="-mx-[18px] flex gap-2 overflow-x-auto px-[18px] py-1 [scrollbar-width:none]">
          {filters.map((f) => <button key={f.key} type="button" role="radio" aria-checked={filter === f.key} onClick={() => setFilter(f.key)} className={cn("min-h-11 shrink-0 rounded-full px-4 text-sm font-semibold", filter === f.key ? "bg-ink text-white" : "bg-card shadow-[var(--shadow-card)]")}>{f.label}</button>)}
        </div>
        {reviewCount > 0 && filter !== "review" && <p className="px-1 text-[13px] text-muted-foreground">{reviewCount} uploaded {reviewCount === 1 ? "item needs" : "items need"} a quick check. They are not counted in totals yet.</p>}
        {filter === "review" ? <div className="flex flex-col gap-2">{data.reviews.length ? data.reviews.map((item) => <button key={item.id} type="button" onClick={() => setOpenReview(item)} className="rounded-[var(--radius-card)] bg-card p-4 text-left shadow-[var(--shadow-card)]"><b className="block">{item.extracted.payee || "Uploaded document"}</b><span className="text-sm text-muted-foreground">{item.reason.replaceAll("_", " ")} · Check this item</span></button>) : <p className="rounded-[var(--radius-card)] bg-card p-6 text-center text-sm text-muted-foreground">Nothing needs review.</p>}</div>
          : <TransactionList transactions={shown} onOpen={(t) => setOpenTxn(data.transactions.find((x) => x.id === t.id) ?? null)} />}
        {data.transactions.length >= 200 && <p className="text-center text-xs text-muted-foreground">Showing the 200 most recent transactions. Older records are not shown here.</p>}
      </>}
    </main><div className="sticky bottom-0"><TabBar /></div>
    {openTxn && <TransactionEditor transaction={openTxn} onClose={() => setOpenTxn(null)} onSaved={() => saved("Correction saved. Totals refreshed.")} />}
    {openBill && <BillPayment bill={openBill} transactions={data?.transactions ?? []} onClose={() => setOpenBill(null)} onSaved={() => saved("Payment linked. Bill marked paid.")} />}
    {openReview && <ConnectedReviewSheet item={openReview} onClose={() => {setOpenReview(null);void refresh();}} onResolved={() => saved("Review saved. Activity refreshed.")} />}
  </div>;
}
