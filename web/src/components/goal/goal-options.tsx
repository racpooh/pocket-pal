import { CalendarClock, Plus, Target, Wallet } from "lucide-react";
import { baht } from "@/lib/money";
import type { Goal, GoalOption } from "./types";

const ICONS = { deadline: CalendarClock, target: Target, pocket: Wallet, income: Plus };

/** Swipeable option cards, each comparing the numbers it changes (old struck through, new bold). */
export function GoalOptions({
  goal,
  perPayday,
  options,
  onChoose,
}: {
  goal: Goal;
  /** The current Planned amount per income date. */
  perPayday: number;
  options: GoalOption[];
  onChoose: (option: GoalOption) => void;
}) {
  if (options.length === 0) return null;
  return (
    <section aria-labelledby="options-heading">
      <h3 id="options-heading" className="mb-2 px-1 text-[15px] font-bold">
        Your options
      </h3>
      <div className="num -mx-[18px] flex snap-x snap-mandatory gap-3 overflow-x-auto px-[18px] pb-2 [scrollbar-width:none]">
        {options.map((o) => {
          const Icon = ICONS[o.kind];
          const changes = [
            { label: "Deadline", from: goal.deadline, to: o.newDeadline },
            { label: "Target", from: baht(goal.target), to: o.newTarget ? baht(o.newTarget) : undefined },
            { label: "Per payday", from: baht(perPayday), to: o.newPerPayday ? baht(o.newPerPayday) : undefined },
          ].filter((c) => c.to);
          return (
            <article key={o.id} aria-label={o.title} className="flex w-[78%] shrink-0 snap-start flex-col rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]">
              <span className="grid size-10 place-items-center rounded-xl bg-mint-soft text-mint-text">
                <Icon className="size-5" aria-hidden />
              </span>
              <h4 className="mt-2.5 text-[15px] leading-5 font-extrabold">{o.title}</h4>
              <p className="mt-1 text-[13px] leading-[18px] text-muted-foreground">{o.detail}</p>
              {changes.length > 0 && (
                <dl className="mt-3 flex flex-col gap-1.5 rounded-xl bg-background p-2.5 text-[13px]">
                  {changes.map((c) => (
                    <div key={c.label} className="flex justify-between gap-2">
                      <dt className="text-muted-foreground">{c.label}</dt>
                      <dd>
                        <s className="mr-1 text-muted-foreground">
                          <span className="sr-only">was </span>
                          {c.from}
                        </s>
                        <b>
                          <span className="sr-only">becomes </span>
                          {c.to}
                        </b>
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
              <div className="min-h-3.5 flex-1" aria-hidden />
              <button type="button" onClick={() => onChoose(o)} className="min-h-11 rounded-xl bg-ink text-sm font-bold text-white active:scale-[0.97] motion-reduce:transform-none">
                Choose this
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
