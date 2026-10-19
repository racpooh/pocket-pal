"use client";

import { Coins, Eye, EyeOff, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { InsightCard, type Insight } from "@/components/insight-card";
import { PocketCard, type Pocket } from "@/components/pocket-card";
import { TabBar } from "@/components/tab-bar";
import { ServerActionCard, type ServerProposal } from "@/components/action-card/server-action-card";
import { parseSatang } from "@/lib/goals";
import { api } from "@/lib/api";
import { displayBaht, formatDate, nextDay, pocketKind, type PlanResponse, type PocketDefinition, type Profile, type SpendingReport } from "@/lib/dashboard";
import { baht } from "@/lib/money";

type Recommendation = { category: string; last_month_satang: number; average_satang: number; estimated_savings_per_month_satang: number; basis: string };
type Insights = { recommendations: Recommendation[] };
type Dashboard = { plan: PlanResponse; profile: Profile; pockets: Pocket[]; spending: SpendingReport; insight: Insight | null };

function Gauge({ percent }: { percent: number }) {
  const shown = Math.min(100, Math.max(0, percent));
  return <div className="relative h-[66px] w-[116px] shrink-0" aria-hidden>
    <svg viewBox="0 0 116 66" width="116" height="66">
      <path d="M10 58a48 48 0 0 1 96 0" fill="none" className="stroke-mint-soft" strokeWidth="14" strokeLinecap="round" />
      <path d="M10 58a48 48 0 0 1 96 0" fill="none" className={percent > 100 ? "stroke-danger" : "stroke-mint"} strokeWidth="14" strokeLinecap="round" pathLength={100} strokeDasharray={`${shown} 100`} />
    </svg>
    <span className="absolute inset-x-0 bottom-0 text-center text-lg font-extrabold">{Math.round(percent)}%</span>
  </div>;
}

async function loadDashboard(): Promise<Dashboard> {
  const [plan, definitions, profile, insights] = await Promise.all([
    api<PlanResponse>("/plan"), api<PocketDefinition[]>("/pockets"), api<Profile>("/me/profile"), api<Insights>("/insights"),
  ]);
  const spending = await api<SpendingReport>(`/spending?from=${encodeURIComponent(plan.today)}&to=${encodeURIComponent(nextDay(plan.today))}`);
  const status = new Map(plan.pockets.filter((p) => p.pocket_id).map((p) => [p.pocket_id, p]));
  const pockets = definitions.map((p): Pocket => {
    const s = status.get(p.pocket_id);
    const confirmed = s?.spent_confirmed_satang ?? null;
    const predicted = s?.spent_predicted_satang ?? null;
    return { id: p.pocket_id, name: p.name, kind: pocketKind(p.categories, p.name),
      budget: s?.allocation_satang == null ? null : displayBaht(s.allocation_satang),
      spent: confirmed === null || predicted === null ? null : displayBaht(confirmed + predicted),
      predicted: predicted === null ? undefined : displayBaht(predicted) };
  });
  const r = insights.recommendations?.[0];
  const insight: Insight | null = r ? { id: `${r.category}:${r.basis}`, subject: r.category,
    period: { current: "Last month", previous: "Earlier average" },
    amounts: { current: displayBaht(r.last_month_satang), previous: displayBaht(r.average_satang) },
    action: `Consider spending ${baht(displayBaht(r.estimated_savings_per_month_satang))} less on ${r.category} per month.`,
    saving: { amount: displayBaht(r.estimated_savings_per_month_satang), by: "the end of a month" },
    tradeoff: `Based on ${r.basis}; this is an estimate from recorded transactions.` } : null;
  return { plan, profile, pockets, spending, insight };
}

export function PocketsTab() {
  const [hidden, setHidden] = useState(false);
  const [insightShown, setInsightShown] = useState(true);
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editPocket, setEditPocket] = useState("");
  const [increase, setIncrease] = useState("");
  const [proposal, setProposal] = useState<ServerProposal | null>(null);
  const [proposing, setProposing] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const proposeIncrease = async () => {
    const amount = parseSatang(increase);
    if (!editPocket || amount === null || amount <= 0) { setEditError("Choose a pocket and enter a positive amount in baht."); return; }
    setProposing(true); setEditError(null);
    try {
      setProposal(await api<ServerProposal>("/plan/tradeoff", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({pocket_id:editPocket, increase_satang:amount})}));
    } catch (e) { setEditError(e instanceof Error ? e.message : "Could not prepare this change."); }
    finally { setProposing(false); }
  };
  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await loadDashboard()); } catch (e) { setError(e instanceof Error ? e.message : "Could not load your pockets."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    void refresh();
    const focus = () => { void refresh(); };
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, [refresh]);
  const cash = data?.plan.cashflow;
  const spent = data?.spending.total_satang ?? 0;
  const daily = cash?.daily_allowance_satang ?? 0;
  const left = daily;
  const nextIncome = data?.profile.income?.next_income_date;
  const unassigned = data?.plan.pockets.find((p) => p.pocket_id === null);

  return <div className="mx-auto flex min-h-dvh w-full max-w-[430px] flex-col bg-background">
    <main className="num flex flex-1 flex-col gap-3.5 px-[18px] pt-[max(16px,env(safe-area-inset-top))] pb-6">
      <header className="flex items-center justify-between pt-1.5">
        <div><h1 className="text-2xl leading-[30px] font-extrabold tracking-tight">Your pockets</h1>
          <p className="text-sm text-muted-foreground">{nextIncome ? `Next income ${formatDate(nextIncome)}` : "Your money plan"}</p></div>
        <Link href="/settings" aria-label="Settings" className="grid place-items-center size-11 rounded-full bg-mint-soft text-[15px] font-bold text-mint-text">You</Link>
      </header>
      <div className="grid grid-cols-2 gap-2.5">
        <Link href="/" className="flex min-h-[52px] items-center justify-center gap-2.5 rounded-[var(--radius-ctl)] bg-ink text-[15px] font-semibold text-white active:scale-[0.97]"><Upload className="size-5" aria-hidden />Upload slip</Link>
        <Link href="/" className="flex min-h-[52px] items-center justify-center gap-2.5 rounded-[var(--radius-ctl)] bg-mint text-[15px] font-semibold text-ink active:scale-[0.97]"><Sparkles className="size-5" aria-hidden />Ask Pal</Link>
      </div>
      {loading && <p role="status" className="rounded-2xl bg-card p-4 text-sm">Loading your pockets…</p>}
      {error && <div role="alert" className="rounded-2xl bg-card p-4 text-sm">{error} <button type="button" onClick={() => void refresh()} className="ml-2 font-bold underline">Retry</button></div>}
      {data && cash && <>
        <section aria-label="Balance" className="flex items-center gap-3.5 rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
          <span className="grid size-[52px] shrink-0 place-items-center rounded-[14px] bg-mint-soft text-mint-text"><Coins className="size-[26px]" aria-hidden /></span>
          <div><div className="text-sm text-muted-foreground">Tracked balance</div><div className="text-[26px] leading-8 font-extrabold tracking-tight">{hidden ? "฿•••••" : `${cash.available_balance_satang < 0 ? "−" : ""}${baht(displayBaht(cash.available_balance_satang))}`}</div></div>
          <button type="button" onClick={() => setHidden((h) => !h)} aria-pressed={hidden} className="ml-auto flex min-h-11 items-center gap-1.5 rounded-full bg-background px-3.5 text-sm font-semibold">{hidden ? <Eye className="size-4" aria-hidden /> : <EyeOff className="size-4" aria-hidden />}{hidden ? "Show" : "Hide"}</button>
        </section>
        <section aria-label="Safe to spend" className="rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
          <div className="flex items-center gap-2 rounded-full bg-mint-soft px-3 py-2 text-sm leading-5"><span><b className="text-mint-text">{baht(displayBaht(Math.max(0, left)))}</b> current daily guide</span><span className="ml-auto flex items-center gap-1.5 font-semibold whitespace-nowrap"><span className="size-2 rounded-full bg-mint" aria-hidden />{cash.shortage_satang > 0 ? "Shortfall" : "Updated"}</span></div>
          <div className="mt-3.5 flex items-center gap-4"><Gauge percent={daily > 0 ? (spent / daily) * 100 : 0} /><div><div className="text-sm text-muted-foreground">Recorded spending today</div><div className="text-2xl leading-[30px] font-extrabold">{baht(displayBaht(spent))} / <span className="text-mint-text">{baht(displayBaht(daily))}</span></div></div></div>
          <p className="mt-3 border-t border-line pt-3 text-[13px] leading-[18px] text-muted-foreground"><b className="text-foreground">{cash.discretionary_satang < 0 ? "Shortfall" : "Money left"} {baht(displayBaht(cash.discretionary_satang))}</b> until {nextIncome ? formatDate(nextIncome) : "next income"}, after recorded bills, essentials, savings commitments and buffer. The guide already reflects recorded spending. Gauge: today’s spending as a percentage of the current daily guide.</p>
          {(data.spending.excluded_unresolved_count > 0 || data.spending.unlinked_refunds_satang > 0) && <p className="mt-2 text-xs text-muted-foreground">Unresolved spending or unlinked refunds are not included in this total.</p>}
        </section>
        {insightShown && data.insight && <InsightCard insight={data.insight} onDismiss={() => setInsightShown(false)} />}
        <h2 className="flex items-center gap-3 text-[15px] font-semibold text-muted-foreground before:h-px before:flex-1 before:bg-[#d9dde2] after:h-px after:flex-1 after:bg-[#d9dde2]">Your pockets</h2>
        {data.plan.plan && <p className="text-sm text-muted-foreground" data-testid="pocket-period">Budget period: {formatDate(data.plan.plan.period_start)} – before {formatDate(data.plan.plan.period_end)}. Spending follows the transaction date. Older slips stay in Activity and do not use this period’s budget.</p>}
        <button type="button" disabled={loading} onClick={() => void refresh()} className="self-end min-h-11 text-sm font-semibold underline">Refresh pockets</button>
        <div className="grid grid-cols-2 gap-3">{data.pockets.map((p) => <PocketCard key={p.id} pocket={p} />)}</div>
        {data.pockets.length === 0 && <p className="rounded-2xl bg-card p-4 text-center text-sm text-muted-foreground">No pockets yet. <Link href="/welcome" className="underline">Open setup</Link> to create your plan.</p>}
        <p className="text-center text-[13px] text-muted-foreground">{data.plan.plan ? (unassigned?.unassigned_satang ? `${baht(displayBaht(unassigned.unassigned_satang))} of recorded spending is unassigned` : "All counted spending in this budget period has a pocket") : "Create a plan to see pocket allocations"}</p>
        {data.plan.plan && <section className="rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]" aria-label="Adjust pocket budgets">
          <h2 className="font-bold">Adjust pocket budgets</h2>
          <p className="mt-2 text-sm text-muted-foreground">Give one pocket more budget. Pal will take it from other pockets in proportion to their unspent amounts. Review every change before approving; your total budget stays the same.</p>
          <label className="mt-3 block text-sm">Pocket to increase<select className="mt-1 min-h-11 w-full rounded-xl bg-background p-2" value={editPocket} onChange={e => {setEditPocket(e.target.value); setProposal(null);}} disabled={proposing}>
            <option value="">Choose a pocket</option>{data.pockets.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select></label>
          <label className="mt-3 block text-sm">Increase by (THB)<input className="mt-1 min-h-11 w-full rounded-xl bg-background p-2" inputMode="decimal" value={increase} onChange={e => {setIncrease(e.target.value); setProposal(null);}} placeholder="100.00" disabled={proposing} /></label>
          <button type="button" onClick={() => void proposeIncrease()} disabled={proposing || !editPocket || !increase.trim()} className="mt-3 min-h-11 w-full rounded-xl bg-ink p-2 font-bold text-white disabled:opacity-40">{proposing ? "Preparing…" : "Preview changes"}</button>
          {editError && <p role="alert" className="mt-2 text-sm text-danger">{editError}</p>}
        </section>}
        {proposal && <ServerActionCard key={proposal.proposal_id} initial={proposal} onEdit={() => setProposal(null)} onChanged={() => {setProposal(null); setIncrease(""); void refresh();}} />}
      </>}
    </main><div className="sticky bottom-0"><TabBar /></div>
  </div>;
}
