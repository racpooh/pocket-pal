import { HelpCircle } from "lucide-react";
import { PocketTile } from "@/components/pocket-tile";
import { baht } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { Transaction } from "./types";

const SOURCE_LABEL: Record<string, string> = {
  slip: "From a slip",
  receipt: "From a receipt",
  manual: "Added by you",
  csv: "Imported",
};

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full bg-ink px-2 py-0.5 text-[11px] font-bold whitespace-nowrap text-white">{children}</span>;
}

/** Transactions grouped by day; each row opens for correction. */
export function TransactionList({ transactions, onOpen }: { transactions: Transaction[]; onOpen: (t: Transaction) => void }) {
  const days = [...new Set(transactions.map((t) => t.day))];
  if (transactions.length === 0) {
    return <p className="rounded-[var(--radius-card)] bg-card p-6 text-center text-sm text-muted-foreground shadow-[var(--shadow-card)]">Nothing here for this filter.</p>;
  }
  return (
    <div className="num flex flex-col gap-3">
      {days.map((day) => (
        <section key={day} aria-label={day}>
          <h3 className="mb-1.5 px-1 text-[13px] font-semibold text-muted-foreground">{day}</h3>
          <ul className="rounded-[var(--radius-card)] bg-card px-3.5 shadow-[var(--shadow-card)]">
            {transactions
              .filter((t) => t.day === day)
              .map((t) => {
                const income = t.amount > 0;
                return (
                  <li key={t.id} className="border-t border-line first:border-t-0">
                    <button type="button" onClick={() => onOpen(t)} className="flex min-h-16 w-full items-center gap-3 py-2.5 text-left">
                      {t.pocket ? (
                        <PocketTile kind={t.pocket} size={40} className="rounded-xl" />
                      ) : (
                        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-background text-muted-foreground">
                          <HelpCircle className="size-5" aria-hidden />
                        </span>
                      )}
                      <span className="min-w-0 flex-1">
                        <b className="block truncate text-[15px]">{t.merchant}</b>
                        <span className="flex flex-wrap items-center gap-1.5 text-[13px] text-muted-foreground">
                          {t.pocketName ?? "No pocket yet"} · {SOURCE_LABEL[t.source] ?? t.source}
                        </span>
                        {(t.needsReview || t.possibleDuplicateOf) && (
                          <span className="mt-1 flex flex-wrap gap-1">
                            {t.needsReview && <Tag>Needs review</Tag>}
                            {t.possibleDuplicateOf && <Tag>Possible duplicate</Tag>}
                          </span>
                        )}
                      </span>
                      <span className={cn("shrink-0 font-extrabold", income && "text-mint-text", t.needsReview && "text-muted-foreground")}>
                        {income ? "+" : "−"}
                        {baht(t.amount)}
                      </span>
                    </button>
                  </li>
                );
              })}
          </ul>
        </section>
      ))}
    </div>
  );
}
