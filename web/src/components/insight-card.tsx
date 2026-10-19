"use client";

// Insight card (CONTEXT.md): an observation, its period, a suggested action, a saving with
// amount and time span, and the tradeoff. Wording never blames: "Delivery is up ฿300".

import { Lightbulb, X } from "lucide-react";
import { baht } from "@/lib/money";
import { cn } from "@/lib/utils";

export type Insight = {
  id: string;
  /** What is being compared, e.g. "Delivery". */
  subject: string;
  /** Equal elapsed periods, e.g. "Oct 1–14" vs "Sep 1–14". */
  period: { current: string; previous: string };
  amounts: { current: number; previous: number };
  /** Suggested action, e.g. "Spend ฿150 less a week on delivery". */
  action: string;
  /** Saving over an explicit horizon. */
  saving: { amount: number; by: string; toward?: string };
  tradeoff: string;
  /** Button that turns the suggestion into a proposal; omit for read-only insights. */
  actionLabel?: string;
};

/** "Delivery is up ฿300" / "down" / "is new this month"; a THB change, never a % of zero. */
function headline({ subject, amounts }: Insight): string {
  const diff = amounts.current - amounts.previous;
  if (amounts.previous === 0) return `${subject} is new: ${baht(amounts.current)}`;
  if (diff === 0) return `${subject} is the same as last time`;
  return `${subject} is ${diff > 0 ? "up" : "down"} ${baht(diff)}`;
}

export function InsightCard({
  insight,
  onAction,
  onDismiss,
  className,
}: {
  insight: Insight;
  onAction?: () => void;
  onDismiss?: () => void;
  className?: string;
}) {
  const { amounts, period } = insight;
  const max = Math.max(amounts.current, amounts.previous, 1);
  const rows = [
    { label: period.previous, value: amounts.previous, now: false },
    { label: period.current, value: amounts.current, now: true },
  ];

  return (
    <article aria-label={`Insight: ${headline(insight)}`} className={cn("num rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]", className)}>
      <div className="flex items-center gap-2.5">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-mint-soft text-mint-text">
          <Lightbulb className="size-[18px]" aria-hidden />
        </span>
        <div className="min-w-0">
          <div className="text-xs font-bold tracking-[0.06em] text-mint-text uppercase">Insight</div>
          <div className="text-[13px] leading-[18px] text-muted-foreground">
            {period.current} vs {period.previous}
          </div>
        </div>
        {onDismiss && (
          <button type="button" aria-label="Hide this insight" onClick={onDismiss} className="-mr-1 ml-auto grid size-11 place-items-center rounded-full text-muted-foreground">
            <X className="size-5" aria-hidden />
          </button>
        )}
      </div>

      <h3 className="mt-3 text-xl leading-7 font-extrabold">{headline(insight)}</h3>

      <dl className="mt-2.5 flex flex-col gap-2">
        {rows.map((r) => (
          <div key={r.label} className="grid grid-cols-[72px_minmax(0,1fr)_auto] items-center gap-2.5 text-[13px]">
            <dt className={cn(r.now ? "font-semibold" : "text-muted-foreground")}>{r.label}</dt>
            <span className="h-2.5 overflow-hidden rounded-full bg-background" aria-hidden>
              <span className={cn("block h-full rounded-full", r.now ? "bg-ink" : "bg-[#c9cdd3]")} style={{ width: `${(r.value / max) * 100}%` }} />
            </span>
            <dd className={cn("text-right", r.now ? "font-extrabold" : "text-muted-foreground")}>{baht(r.value)}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-3.5 rounded-2xl bg-mint-soft p-3">
        <p className="text-[15px] leading-[22px] font-bold">{insight.action}</p>
        <p className="mt-0.5 text-sm leading-5">
          <b className="text-mint-text">
            {baht(insight.saving.amount)} more{insight.saving.toward ? ` for ${insight.saving.toward}` : ""}
          </b>{" "}
          by {insight.saving.by}
        </p>
      </div>
      <p className="mt-2.5 text-[13px] leading-[18px] text-muted-foreground">
        <span className="font-semibold text-foreground">Tradeoff:</span> {insight.tradeoff}
      </p>

      {(onAction || onDismiss) && (
        <div className="mt-3.5 flex items-center gap-2">
          {onAction && insight.actionLabel && (
            <button type="button" onClick={onAction} className="min-h-12 flex-1 rounded-[var(--radius-ctl)] bg-ink px-4 text-[15px] font-bold text-white active:scale-[0.97] motion-reduce:transform-none">
              {insight.actionLabel}
            </button>
          )}
          {onDismiss && (
            <button type="button" onClick={onDismiss} className="min-h-12 rounded-[var(--radius-ctl)] px-4 text-[15px] font-semibold text-muted-foreground">
              Not now
            </button>
          )}
        </div>
      )}
    </article>
  );
}
