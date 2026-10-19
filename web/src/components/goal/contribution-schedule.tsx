import { Check } from "lucide-react";
import { baht } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { PlannedContribution } from "./types";

/** Planned contributions per income date, each checked against what's free that day. */
export function ContributionSchedule({ schedule }: { schedule: PlannedContribution[] }) {
  return (
    <section aria-labelledby="planned-heading" className="num rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
      <h3 id="planned-heading" className="text-[15px] font-bold">
        Planned contributions
      </h3>
      <ul className="mt-2">
        {schedule.map((r) => {
          const fits = r.free >= r.planned;
          return (
            <li key={r.date} className="flex items-center gap-3 border-t border-line py-3 first:border-t-0">
              <span className={cn("grid size-9 shrink-0 place-items-center rounded-xl", fits ? "bg-mint-soft text-mint-text" : "bg-ink text-white")} aria-hidden>
                {fits ? <Check className="size-4" /> : <span className="text-sm font-extrabold">!</span>}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-bold">{r.date} payday</div>
                <div className="text-[13px] text-muted-foreground">
                  {fits ? `Fits · ${baht(r.free)} free` : `Only ${baht(r.free)} free · ${baht(r.planned - r.free)} short`}
                </div>
              </div>
              <span className="font-extrabold">{baht(r.planned)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
