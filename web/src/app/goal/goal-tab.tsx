"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { GoalProgressCard } from "@/components/goal/goal-progress-card";
import { TabBar } from "@/components/tab-bar";
import { api } from "@/lib/api";
import { approveProposal, createGoalProposal, errorMessage, formatSatang, parseSatang, type GoalRecord, type Proposal } from "@/lib/goals";

type Feasibility = {
  remaining_satang: number; contribution_events: number; required_per_event_satang: number;
  capacity_per_event_satang: number; feasible: boolean; progress_bps: number;
  later_deadline: string | null; smaller_target_satang: number | null;
  extra_saving_needed_per_event_satang: number | null; assumption: string;
};

export function GoalTab() {
  const router = useRouter();
  const [goals, setGoals] = useState<GoalRecord[]>([]);
  const [selected, setSelected] = useState("");
  const [feasibility, setFeasibility] = useState<Feasibility | null>(null);
  const [pending, setPending] = useState<Proposal | null>(null);
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [deadline, setDeadline] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const goal = goals.find((g) => g.id === selected) ?? goals[0];

  const refresh = async () => {
    const rows = await api<GoalRecord[]>("/goals");
    setGoals(rows);
    setSelected((current) => rows.some((g) => g.id === current) ? current : rows[0]?.id ?? "");
  };
  useEffect(() => { void refresh().catch((cause) => setError(errorMessage(cause))); }, []);
  useEffect(() => {
    if (!goal) { setFeasibility(null); return; }
    let live = true;
    void api<Feasibility>("/goals/feasibility", { method: "POST", body: JSON.stringify({
      target_satang: goal.target_satang, saved_satang: goal.saved_satang, deadline: goal.deadline,
    }) }).then((result) => { if (live) setFeasibility(result); }).catch((cause) => { if (live) setError(errorMessage(cause)); });
    return () => { live = false; };
  }, [goal?.id, goal?.target_satang, goal?.saved_satang, goal?.deadline]);

  const proposeNew = async () => {
    const value = parseSatang(amount);
    if (!name.trim() || value === null || value <= 0 || !deadline) { setError("Enter a name, positive amount, and deadline."); return; }
    setBusy(true); setError(null);
    try { setPending(await createGoalProposal({ name: name.trim(), target_satang: value, saved_satang: 0, deadline, contribution_satang_per_period: 0 })); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };
  const proposeUpdate = async (change: { deadline?: string; target_satang?: number }) => {
    if (!goal) return;
    setBusy(true); setError(null);
    try { setPending(await api<Proposal>("/proposals", { method: "POST", body: JSON.stringify({ kind: "goal_update", payload: { goal_id: goal.id, ...change } }) })); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };
  const approve = async () => {
    if (!pending) return;
    setBusy(true); setError(null);
    try { await approveProposal(pending); setPending(null); await refresh(); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!pending) return;
    setBusy(true); setError(null);
    try { await api(`/proposals/${pending.proposal_id}/cancel`, { method: "POST" }); setPending(null); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };

  return <div className="mx-auto flex min-h-dvh w-full max-w-[430px] flex-col bg-background">
    <main className="flex flex-1 flex-col gap-3.5 px-[18px] pt-[max(16px,env(safe-area-inset-top))] pb-6">
      <h1 className="pt-1.5 text-2xl leading-[30px] font-extrabold tracking-tight">Your goal</h1>
      {error && <p role="alert" className="rounded-2xl bg-danger-soft p-3 text-sm text-danger">{error}</p>}
      {goals.length > 1 && <label className="text-sm font-bold">Choose goal<select className="mt-1 h-12 w-full rounded-xl bg-card px-3" value={goal?.id ?? ""} onChange={(event) => setSelected(event.target.value)}>{goals.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label>}
      {goal ? <>
        <GoalProgressCard goal={{ id: goal.id, name: goal.name, target: goal.target_satang / 100, saved: goal.saved_satang / 100, deadline: goal.deadline, daysLeft: Math.max(0, Math.ceil((new Date(`${goal.deadline}T00:00:00+07:00`).getTime() - Date.now()) / 86_400_000)), protected: false }} status={feasibility ? feasibility.feasible ? "on-track" : "not-possible" : "with-changes"} />
        <section className="num rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
          <h2 className="text-[15px] font-bold">Planned contributions</h2>
          {feasibility ? <div className="mt-2 space-y-1 text-sm">
            <p>{feasibility.contribution_events} income dates until {goal.deadline}.</p>
            <p>{formatSatang(feasibility.required_per_event_satang)} needed per income date; {formatSatang(feasibility.capacity_per_event_satang)} estimated capacity per date.</p>
            <p className="text-muted-foreground">Saved commitments: {formatSatang(goal.contribution_satang_per_period)} per income period. {feasibility.assumption}.</p>
            <p className="text-muted-foreground">A dated contribution schedule is unavailable from the current backend.</p>
          </div> : <p className="mt-2 text-sm text-muted-foreground">Checking your current plan…</p>}
        </section>
        {feasibility && !feasibility.feasible && <section aria-label="Your options"><h2 className="mb-2 px-1 text-[15px] font-bold">Your options</h2><div className="num -mx-[18px] flex snap-x snap-mandatory gap-3 overflow-x-auto px-[18px] pb-2 [scrollbar-width:none]">
          {feasibility.later_deadline && <article className="flex w-[78%] shrink-0 snap-start flex-col rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]"><h3 className="text-[15px] font-extrabold">Move the deadline</h3><p className="mt-1 flex-1 text-sm text-muted-foreground">From {goal.deadline} to {feasibility.later_deadline}, based on current estimated capacity.</p><button type="button" disabled={busy || !!pending} onClick={() => proposeUpdate({ deadline: feasibility.later_deadline! })} className="mt-3 min-h-11 rounded-xl bg-ink text-sm font-bold text-white disabled:opacity-40">Choose this</button></article>}
          {feasibility.smaller_target_satang !== null && feasibility.smaller_target_satang > 0 && feasibility.smaller_target_satang !== goal.target_satang && <article className="flex w-[78%] shrink-0 snap-start flex-col rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]"><h3 className="text-[15px] font-extrabold">Lower the target</h3><p className="mt-1 flex-1 text-sm text-muted-foreground">From {formatSatang(goal.target_satang)} to {formatSatang(feasibility.smaller_target_satang)} by {goal.deadline}.</p><button type="button" disabled={busy || !!pending} onClick={() => proposeUpdate({ target_satang: feasibility.smaller_target_satang! })} className="mt-3 min-h-11 rounded-xl bg-ink text-sm font-bold text-white disabled:opacity-40">Choose this</button></article>}
          {feasibility.extra_saving_needed_per_event_satang !== null && <article className="flex w-[78%] shrink-0 snap-start flex-col rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]"><h3 className="text-[15px] font-extrabold">Find more room</h3><p className="mt-1 text-sm text-muted-foreground">You would need {formatSatang(feasibility.extra_saving_needed_per_event_satang)} more per income date. Review spending before changing a commitment.</p></article>}
        </div></section>}
      </> : <section className="rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]"><h2 className="text-lg font-extrabold">Start a goal</h2><div className="mt-3 space-y-3 text-sm"><label className="block">Goal name<input className="mt-1 h-11 w-full rounded-xl bg-background px-3" value={name} onChange={(e) => setName(e.target.value)} /></label><label className="block">Target (฿)<input className="mt-1 h-11 w-full rounded-xl bg-background px-3" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></label><label className="block">By<input className="mt-1 h-11 w-full rounded-xl bg-background px-3" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label><button type="button" disabled={busy || !!pending} onClick={proposeNew} className="min-h-11 w-full rounded-xl bg-ink font-bold text-white disabled:opacity-40">Review goal</button></div></section>}
      {pending && <section aria-label="Goal approval" className="rounded-[var(--radius-card)] bg-mint-soft p-[18px]"><h2 className="font-extrabold">Review before applying</h2><p className="mt-1 text-sm">{pending.card.summary?.text}</p>{pending.card.warnings?.map((warning, i) => <p key={i} className="mt-2 text-sm">{warning.text}</p>)}{pending.card.uncertainty?.map((item, i) => <p key={i} className="mt-2 text-sm text-muted-foreground">{item.text}</p>)}<p className="mt-2 text-xs text-muted-foreground">Nothing changes until you approve this card.</p><div className="mt-3 grid grid-cols-2 gap-2"><button type="button" disabled={busy} onClick={approve} className="min-h-11 rounded-xl bg-ink text-sm font-bold text-white disabled:opacity-40">Approve</button><button type="button" disabled={busy} onClick={cancel} className="min-h-11 rounded-xl bg-card text-sm font-bold disabled:opacity-40">Cancel</button></div></section>}
      {!goal && <button type="button" onClick={() => router.push("/")} className="text-sm font-semibold text-muted-foreground">Back to chat</button>}
    </main><div className="sticky bottom-0"><TabBar /></div>
  </div>;
}
