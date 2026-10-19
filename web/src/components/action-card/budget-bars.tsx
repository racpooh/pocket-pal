import { baht, signedBaht } from "@/lib/money";
import { cn } from "@/lib/utils";
import { PocketTile, pocketBarColor } from "@/components/pocket-tile";
import type { PocketChange } from "./types";

function SplitBar({ changes, total, which }: { changes: PocketChange[]; total: number; which: "before" | "after" }) {
  return (
    <div className="flex h-3 w-full gap-[3px] overflow-hidden rounded-full" aria-hidden>
      {changes.map((c) => (
        <span
          key={c.pocketId}
          className={cn("h-full first:rounded-l-full last:rounded-r-full", pocketBarColor(c.kind), which === "before" && "opacity-35")}
          style={{ width: `${(c[which] / total) * 100}%` }}
        />
      ))}
    </div>
  );
}

/**
 * Before/after detail for a budget change: a split bar showing the flexible budget keeps
 * the same total, then paired bars per pocket (grey is now, colour is new).
 */
export function BudgetBars({ changes, total }: { changes: PocketChange[]; total: number }) {
  const max = Math.max(...changes.flatMap((c) => [c.before, c.after]));
  return (
    <>
      <section className="num rounded-2xl bg-background p-3" aria-label="Flexible budget split">
        <div className="mb-2 flex items-baseline justify-between text-[13px]">
          <span className="font-semibold text-muted-foreground">Flexible budget</span>
          <span className="font-bold">{baht(total)} · same total</span>
        </div>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <span className="w-11 text-xs text-muted-foreground">Now</span>
            <SplitBar changes={changes} total={total} which="before" />
          </div>
          <div className="flex items-center gap-2">
            <span className="w-11 text-xs font-semibold">New</span>
            <SplitBar changes={changes} total={total} which="after" />
          </div>
        </div>
      </section>

      <ul className="num mt-3 flex flex-col gap-3">
        {changes.map((c) => {
          const delta = c.after - c.before;
          return (
            <li key={c.pocketId} className="flex items-center gap-3">
              <PocketTile kind={c.kind} size={38} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2 text-[15px]">
                  <span className="font-semibold">{c.name}</span>
                  <span>
                    <span className="sr-only">from {baht(c.before)} to </span>
                    <b className="font-extrabold">{baht(c.after)}</b>{" "}
                    <span className={cn("text-[13px] font-bold", delta > 0 ? "text-mint-text" : "text-muted-foreground")}>
                      {signedBaht(delta)}
                    </span>
                  </span>
                </div>
                <div className="mt-1.5 flex flex-col gap-1" aria-hidden>
                  <span className="block h-1.5 rounded-full bg-[#dfe2e6]" style={{ width: `${(c.before / max) * 100}%` }} />
                  <span className={cn("block h-1.5 rounded-full", pocketBarColor(c.kind))} style={{ width: `${(c.after / max) * 100}%` }} />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}
