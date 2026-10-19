import { AlertCircle, Check, Lock, TrendingUp } from "lucide-react";
import { baht } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { Goal, GoalStatus } from "./types";

const STATUS_TEXT: Record<GoalStatus, string> = {
  "on-track": "On track",
  "with-changes": "On track with changes",
  "not-possible": "Not possible yet",
};

export function GoalStatusPill({ status }: { status: GoalStatus }) {
  const style = {
    "on-track": "bg-mint-soft text-mint-text",
    "with-changes": "bg-card text-foreground ring-2 ring-ink",
    "not-possible": "bg-ink text-white",
  }[status];
  const Icon = status === "on-track" ? Check : AlertCircle;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-bold whitespace-nowrap", style)}>
      <Icon className="size-4" aria-hidden />
      {STATUS_TEXT[status]}
    </span>
  );
}

export function GoalProgressCard({ goal, status }: { goal: Goal; status: GoalStatus }) {
  const pct = Math.min(100, Math.round((goal.saved / goal.target) * 100));
  const toGo = Math.max(0, goal.target - goal.saved);

  return (
    <section aria-label={`${goal.name} progress`} className="num rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-extrabold">{goal.name}</h2>
        {goal.protected && (
          <span className="flex items-center gap-1 text-xs font-semibold text-muted-foreground">
            <Lock className="size-3.5" aria-hidden />
            Protected
          </span>
        )}
      </div>

      <div className="mt-3 flex items-end justify-between gap-3">
        <div>
          <div className="text-sm text-muted-foreground">Saved</div>
          <div className="text-[26px] leading-8 font-extrabold">
            {baht(goal.saved)} <span className="text-lg text-muted-foreground">/</span> <span className="text-mint-text">{baht(goal.target)}</span>
          </div>
        </div>
        <div className="flex items-center gap-1 text-2xl font-extrabold">
          {pct}%<TrendingUp className="size-5 text-mint-text" aria-hidden />
        </div>
      </div>

      <div
        role="progressbar"
        aria-label="Saved toward goal"
        aria-valuemin={0}
        aria-valuemax={goal.target}
        aria-valuenow={goal.saved}
        aria-valuetext={`${baht(goal.saved)} of ${baht(goal.target)}`}
        className="mt-3 h-3 overflow-hidden rounded-full bg-mint-soft"
      >
        <div className="h-full rounded-full bg-mint" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-2 flex justify-between gap-2 text-[13px] text-muted-foreground">
        <span>{goal.lastChange}</span>
        <span>
          By {goal.deadline} · {goal.daysLeft} days
        </span>
      </div>

      <div className="mt-3.5 flex items-center justify-between gap-2 border-t border-line pt-3.5">
        <GoalStatusPill status={status} />
        <span className="text-[13px] text-muted-foreground">{baht(toGo)} to go</span>
      </div>
    </section>
  );
}
