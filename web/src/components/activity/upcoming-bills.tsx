import { Check, Receipt } from "lucide-react";
import { baht } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { UpcomingBill } from "./types";

export function UpcomingBills({ bills, onOpen }: { bills: UpcomingBill[]; onOpen: (bill: UpcomingBill) => void }) {
  const reserved = bills.filter((b) => b.status === "unpaid").reduce((s, b) => s + b.amount, 0);
  return (
    <section aria-labelledby="bills-heading" className="num rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="bills-heading" className="text-[15px] font-bold">
          Upcoming bills
        </h2>
        <span className="text-[13px] text-muted-foreground">{baht(reserved)} unpaid</span>
      </div>
      <ul className="mt-2">
        {bills.map((b) => {
          const paid = b.status === "paid";
          return (
            <li key={b.id} className="border-t border-line first:border-t-0">
              <button type="button" onClick={() => onOpen(b)} className="flex min-h-16 w-full items-center gap-3 py-2.5 text-left">
                <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl", paid ? "bg-mint-soft text-mint-text" : "bg-background text-foreground")}>
                  {paid ? <Check className="size-5" aria-hidden /> : <Receipt className="size-5" aria-hidden />}
                </span>
                <span className="min-w-0 flex-1">
                  <b className="block truncate text-[15px]">{b.provider}</b>
                  <span className="text-[13px] text-muted-foreground">
                    {paid ? "Paid" : `Due ${b.due} · in ${b.daysUntilDue} ${b.daysUntilDue === 1 ? "day" : "days"}`}
                    {b.changeVsLast ? ` · ${b.changeVsLast > 0 ? "up" : "down"} ${baht(b.changeVsLast)} vs last` : ""}
                  </span>
                </span>
                <span className="text-right">
                  <b className={cn("block", paid && "text-muted-foreground")}>{baht(b.amount)}</b>
                  {!paid && <span className="rounded-full bg-ink px-2 py-0.5 text-[11px] font-bold text-white">Link payment</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
