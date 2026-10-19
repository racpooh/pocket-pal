import { Lock } from "lucide-react";
import type { PocketKind } from "@/components/action-card/types";
import { PocketTile } from "@/components/pocket-tile";
import { baht } from "@/lib/money";
import { cn } from "@/lib/utils";

// Pocket (CONTEXT.md): holds a Budget and tracks Spent; Left = Budget − Spent and may go
// negative. Savings shows Saved instead, since its money is set aside, not spent.

export type Pocket = {
  id: string;
  name: string;
  kind: PocketKind;
  /** Planned allocation this period, in whole baht. */
  budget: number | null;
  /** Confirmed spending this period, net of refunds. */
  spent: number | null;
  /** Protected pockets are never reduced without the user's approval. */
  protected?: boolean;
  /** Savings only: money actually set aside. */
  saved?: number;
  /** Server classified amount that is still only a prediction. */
  predicted?: number;
  /** Short extra line, e.g. "2 upcoming bills". */
  note?: string;
};

export function PocketCard({ pocket }: { pocket: Pocket }) {
  const isSavings = pocket.kind === "savings";
  const left = pocket.budget === null || pocket.spent === null ? null : pocket.budget - pocket.spent;
  const over = !isSavings && left !== null && left < 0;
  const fill = pocket.budget && pocket.spent !== null ? Math.min(100, (pocket.spent / pocket.budget) * 100) : 0;

  return (
    <article
      aria-label={`${pocket.name} pocket`}
      className="num flex flex-col gap-2.5 rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]"
    >
      <div className="flex items-start justify-between">
        <PocketTile kind={pocket.kind} size={42} className="rounded-xl" />
        {pocket.protected && (
          <span className="flex items-center gap-1 rounded-full bg-background px-2 py-1 text-[11px] font-semibold text-muted-foreground">
            <Lock className="size-3" aria-hidden />
            Protected
          </span>
        )}
      </div>

      <div>
        <h3 className="text-[15px] font-bold">{pocket.name}</h3>
        {isSavings ? (
          <p className="text-lg leading-6 font-extrabold">
            {pocket.budget === null ? "No plan yet" : baht(pocket.budget)} {pocket.budget !== null && <span className="text-sm font-semibold text-muted-foreground">allocated</span>}
          </p>
        ) : (
          <p className={cn("text-lg leading-6 font-extrabold", over && "text-danger")}>
            {left === null ? "No plan yet" : over ? `${baht(left)} over` : `${baht(left)} left`}
          </p>
        )}
      </div>

      {!isSavings && pocket.budget !== null && pocket.spent !== null && (
        <div
          role="progressbar"
          aria-label={`${pocket.name} spent`}
          aria-valuemin={0}
          aria-valuemax={pocket.budget}
          aria-valuenow={pocket.spent}
          aria-valuetext={`${baht(pocket.spent)} of ${baht(pocket.budget)}`}
          className={cn("h-2 overflow-hidden rounded-full", over ? "bg-danger-soft" : "bg-mint-soft")}
        >
          <div className={cn("h-full rounded-full", over ? "bg-danger" : "bg-mint")} style={{ width: `${fill}%` }} />
        </div>
      )}

      <p className="text-[13px] leading-[18px] text-muted-foreground">
        {isSavings ? "Allocation only · saved balance unavailable" : pocket.budget === null || pocket.spent === null ? "Create a plan to track spending" : `${baht(pocket.spent)} of ${baht(pocket.budget)} · confirmed + predicted`}
        {!!pocket.predicted && <><br />{baht(pocket.predicted)} still predicted</>}
        {pocket.note && (
          <>
            <br />
            {pocket.note}
          </>
        )}
      </p>
    </article>
  );
}
