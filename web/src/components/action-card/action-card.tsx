"use client";

// Action card (CONTEXT.md): previews a proposed change and applies it only after Approve.
// Layout chosen on the prototype/action-card branch (variant D): a compact summary that
// expands into before/after bars.

import { AlertCircle, Check, ChevronDown, Loader2, Lock, RefreshCw, Undo2, X } from "lucide-react";
import { useId, useState } from "react";
import { baht, percentOf } from "@/lib/money";
import { cn } from "@/lib/utils";
import { BudgetBars } from "./budget-bars";
import { PocketTile } from "@/components/pocket-tile";
import type { ActionCardHandlers, ActionCardState, BudgetChangeProposal, NotPossibleDetail, PocketChange } from "./types";

type ActionCardProps = ActionCardHandlers & {
  proposal: BudgetChangeProposal;
  state: ActionCardState;
  /** Required when `state` is "not-possible". */
  notPossible?: NotPossibleDetail;
};

const cardClass = "rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]";

export function ActionCard({ proposal, state, notPossible, ...on }: ActionCardProps) {
  if (state === "applied" || state === "cancelled" || state === "replaced" || state === "failed") {
    return <Receipt state={state} proposal={proposal} onUndo={on.onUndo} onRetry={on.onRetry} />;
  }
  if (state === "not-possible") {
    if (!notPossible) throw new Error("ActionCard: state 'not-possible' needs a notPossible detail");
    return <NotPossibleCard detail={notPossible} onPick={on.onPickAlternative} onKeep={on.onCancel} />;
  }
  return <ProposalCard proposal={proposal} state={state} {...on} />;
}

/** The pocket that grows (the headline) and the pockets that pay for it. */
function splitChanges(changes: PocketChange[]) {
  const main = changes.reduce((a, b) => (b.after - b.before > a.after - a.before ? b : a));
  const payers = changes.filter((c) => c.after < c.before);
  return { main, payers };
}

function payersLine(payers: PocketChange[]): string {
  const names = payers.map((p) => p.name);
  const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : names[0];
  const cuts = payers.map((p) => p.before - p.after);
  const amount = cuts.every((c) => c === cuts[0]) && cuts.length > 1 ? `−${baht(cuts[0])} each` : `−${baht(cuts.reduce((a, b) => a + b, 0))}`;
  return `${list} · ${amount}`;
}

function ProposalCard({
  proposal,
  state,
  onApprove,
  onEdit,
  onCancel,
  onRecalculate,
}: { proposal: BudgetChangeProposal; state: "pending" | "applying" | "out-of-date" } & ActionCardHandlers) {
  const [open, setOpen] = useState(false);
  const detailId = useId();
  const { main, payers } = splitChanges(proposal.changes);
  const total = proposal.flexibleBudget;
  const stale = state === "out-of-date";
  const busy = state === "applying";

  return (
    <article aria-label={`Proposed change: ${main.name} budget`} className={cardClass}>
      <div className="flex items-center gap-2 rounded-full bg-mint-soft px-3 py-2 text-[13px] leading-[18px]">
        <Lock className="size-3.5 shrink-0 text-mint-text" aria-hidden />
        <span>
          <b className="text-mint-text">Balance unchanged</b> · {proposal.lockedPockets} locked
        </span>
      </div>

      <div className={cn("num mt-4 flex items-center gap-3", stale && "opacity-45")}>
        <PocketTile kind={main.kind} size={52} />
        <div className="min-w-0">
          <div className="text-sm text-muted-foreground">
            {main.name} budget · {percentOf(main.before, total)} → {percentOf(main.after, total)}
          </div>
          <div className="text-[26px] leading-8 font-extrabold">
            {baht(main.before)} <span className="text-muted-foreground">→</span>{" "}
            <span className="text-mint-text">{baht(main.after)}</span>
          </div>
        </div>
      </div>

      {open ? (
        <div id={detailId} className={cn("mt-3", stale && "opacity-45")}>
          <BudgetBars changes={proposal.changes} total={total} />
          <p className="mt-3 text-[13px] leading-[18px] text-muted-foreground">
            Grey is now, colour is new. Percentages are of your {baht(total)} flexible budget. {proposal.assumptions.join(". ")}.
          </p>
        </div>
      ) : (
        payers.length > 0 && (
          <div className={cn("num mt-3 flex items-center gap-3 rounded-2xl bg-background px-3 py-2.5", stale && "opacity-45")}>
            <div className="flex -space-x-2">
              {payers.map((c) => (
                <span key={c.pocketId} className="rounded-xl ring-2 ring-background">
                  <PocketTile kind={c.kind} size={30} />
                </span>
              ))}
            </div>
            <div className="min-w-0 text-[13px] leading-[18px]">
              <b className="block text-[15px] leading-5">
                Paid for by {payers.length} {payers.length === 1 ? "pocket" : "pockets"}
              </b>
              <span className="text-muted-foreground">{payersLine(payers)}</span>
            </div>
          </div>
        )
      )}

      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? detailId : undefined}
        onClick={() => setOpen((o) => !o)}
        className="mt-1 flex min-h-11 w-full items-center justify-center gap-1 text-sm font-semibold text-muted-foreground"
      >
        {open ? "Hide details" : `See all ${proposal.changes.length} changes`}
        <ChevronDown className={cn("size-4 transition-transform motion-reduce:transition-none", open && "rotate-180")} aria-hidden />
      </button>

      {stale ? (
        <div className="flex items-center gap-3 rounded-2xl bg-background px-3.5 py-3" role="status">
          <RefreshCw className="size-5 shrink-0 text-muted-foreground" aria-hidden />
          <div className="min-w-0 text-[13px] leading-[18px] text-muted-foreground">
            <b className="block text-[15px] leading-5 text-foreground">Your numbers changed</b>
            Something changed after this plan was made.
          </div>
          <button type="button" onClick={onRecalculate} className="ml-auto min-h-11 shrink-0 rounded-full bg-ink px-4 text-sm font-bold text-white">
            Recalculate
          </button>
        </div>
      ) : (
        <>
          <button
            type="button"
            onClick={onApprove}
            disabled={busy}
            aria-busy={busy}
            className="flex min-h-[52px] w-full items-center justify-center gap-2 rounded-[var(--radius-ctl)] bg-ink text-[15px] font-bold text-white transition-transform active:scale-[0.97] disabled:opacity-70 motion-reduce:transition-none"
          >
            {busy && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />}
            {busy ? "Applying…" : "Approve change"}
          </button>
          <div className="mt-1 flex justify-center gap-2">
            <button type="button" disabled={busy} onClick={onEdit} className="min-h-11 px-4 text-[15px] font-semibold disabled:opacity-50">
              Edit amounts
            </button>
            <span className="self-center text-line" aria-hidden>
              |
            </span>
            <button type="button" disabled={busy} onClick={onCancel} className="min-h-11 px-4 text-[15px] font-semibold text-muted-foreground disabled:opacity-50">
              Not now
            </button>
          </div>
        </>
      )}
    </article>
  );
}

function Receipt({
  state,
  proposal,
  onUndo,
  onRetry,
}: {
  state: "applied" | "cancelled" | "replaced" | "failed";
  proposal: BudgetChangeProposal;
  onUndo: () => void;
  onRetry: () => void;
}) {
  const { main } = splitChanges(proposal.changes);
  const changeName = `${main.name} ${percentOf(main.before, proposal.flexibleBudget)} → ${percentOf(main.after, proposal.flexibleBudget)}`;
  const conf = {
    applied: { Icon: Check, tile: "bg-mint-soft text-mint-text", title: proposal.appliedSummary, sub: "Applied · Balance unchanged", action: { label: "Undo", Icon: Undo2, onClick: onUndo } },
    cancelled: { Icon: X, tile: "bg-background text-muted-foreground", title: changeName, sub: "Cancelled · nothing changed", action: null },
    replaced: { Icon: RefreshCw, tile: "bg-background text-muted-foreground", title: changeName, sub: "Replaced by your edited plan", action: null },
    failed: { Icon: AlertCircle, tile: "bg-white text-danger", title: "Couldn't save this change", sub: "Failed · nothing was changed", action: { label: "Retry", Icon: RefreshCw, onClick: onRetry } },
  }[state];
  const failed = state === "failed";
  const inactive = state === "cancelled" || state === "replaced";

  return (
    <div
      role={failed ? "alert" : "status"}
      className={cn(
        "flex items-center gap-3 rounded-[var(--radius-card)] px-3.5 py-3",
        failed ? "bg-danger-soft" : "bg-card shadow-[var(--shadow-card)]",
      )}
    >
      <span className={cn("grid size-[42px] shrink-0 place-items-center rounded-xl", conf.tile)}>
        <conf.Icon className="size-5" aria-hidden />
      </span>
      <div className="num min-w-0">
        <div className={cn("text-[15px] leading-5 font-bold", inactive && "text-muted-foreground line-through decoration-line")}>{conf.title}</div>
        <div className="text-[13px] leading-[18px] text-muted-foreground">{conf.sub}</div>
      </div>
      {conf.action && (
        <button
          type="button"
          onClick={conf.action.onClick}
          className="ml-auto flex min-h-11 shrink-0 items-center gap-1.5 rounded-full bg-background px-4 text-sm font-bold"
        >
          <conf.action.Icon className="size-4" aria-hidden />
          {conf.action.label}
        </button>
      )}
    </div>
  );
}

function NotPossibleCard({
  detail,
  onPick,
  onKeep,
}: {
  detail: NotPossibleDetail;
  onPick: (id: string) => void;
  onKeep: () => void;
}) {
  const shortfall = detail.requested - detail.canFree;
  return (
    <article aria-label={`Not possible: ${detail.request}`} className={cardClass}>
      <div className="mb-1 text-[13px] font-semibold text-muted-foreground">{detail.request}</div>
      <div className="mb-3 text-[26px] leading-8 font-extrabold">Doesn&apos;t fit yet</div>
      <div className="num flex flex-col gap-3">
        <div className="rounded-2xl bg-danger-soft px-3.5 py-3 text-[13px] leading-[18px] text-danger">
          <b className="block text-[15px] leading-5">{baht(shortfall)} short</b>
          You asked for +{baht(detail.requested)}, but only {baht(detail.canFree)} can be freed. {detail.reason}
        </div>
        <div className="text-[13px] font-semibold text-muted-foreground">Try one of these instead</div>
        {detail.alternatives.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => onPick(a.id)}
            className="flex min-h-14 items-center justify-between gap-3 rounded-2xl bg-background px-4 py-2 text-left"
          >
            <span>
              <b className="block text-[15px] leading-5">{a.label}</b>
              <span className="text-[13px] leading-[18px] text-muted-foreground">{a.detail}</span>
            </span>
            <span className="shrink-0 text-sm font-bold text-mint-text">Use this</span>
          </button>
        ))}
      </div>
      <button type="button" onClick={onKeep} className="mx-auto mt-2 flex min-h-11 items-center px-4 text-[15px] font-semibold text-muted-foreground">
        Keep my budget
      </button>
    </article>
  );
}
