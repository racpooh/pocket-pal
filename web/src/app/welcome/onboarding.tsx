"use client";

// First run: save the entered numbers to the signed-in account.

import { ArrowLeft, Database, FileUp, Plus, Sparkles, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";
import { baht } from "@/lib/money";
import { cn } from "@/lib/utils";
import { ServerActionCard, type ServerProposal } from "@/components/action-card/server-action-card";
import { api } from "@/lib/api";
import { approveProposal, createGoalProposal, errorMessage, parseSatang, type Proposal } from "@/lib/goals";

const STEPS = ["Balance", "Income", "Bills", "Goal"] as const;

type Bill = { id: number; name: string; amount: string; due: string };

const input =
  "h-12 w-full rounded-xl bg-background px-3.5 text-base font-semibold outline-none placeholder:font-normal placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ink";

function Field({ label, hint, htmlFor, children }: { label: string; hint?: string; htmlFor: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-bold">
        {label}
      </label>
      {children}
      {hint && <p className="text-[13px] leading-[18px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function BahtInput({ id, value, onChange, placeholder = "0" }: { id: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div className="relative">
      <span className="absolute top-1/2 left-3.5 -translate-y-1/2 font-semibold text-muted-foreground" aria-hidden>
        ฿
      </span>
      <input id={id} inputMode="decimal" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} className={cn(input, "pl-8")} />
    </div>
  );
}

function Segmented<T extends string>({ label, options, value, onChange }: { label: string; options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="grid gap-1 rounded-2xl bg-background p-1" style={{ gridTemplateColumns: `repeat(${options.length}, 1fr)` }}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn("min-h-11 rounded-xl text-sm font-bold", value === o.value ? "bg-ink text-white" : "text-muted-foreground")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const num = (s: string) => parseSatang(s) ?? 0;

const EVENTS_PER_YEAR = { monthly: 12, biweekly: 26, weekly: 52 };

export function Onboarding() {
  const router = useRouter();
  const id = useId();
  const csvInput = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState(-1);
  const [csvNote, setCsvNote] = useState<string | null>(null);

  const [balance, setBalance] = useState("");
  const [asOf, setAsOf] = useState(() => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Bangkok" }));
  const [income, setIncome] = useState("");
  const [frequency, setFrequency] = useState<"monthly" | "biweekly" | "weekly">("monthly");
  const [nextIncome, setNextIncome] = useState("");
  const [incomeSure, setIncomeSure] = useState<"sure" | "unsure">("sure");
  const [bills, setBills] = useState<Bill[]>([{ id: 1, name: "", amount: "", due: "" }]);
  const [essentials, setEssentials] = useState("");
  const [buffer, setBuffer] = useState("");
  const [goalName, setGoalName] = useState("");
  const [goalAmount, setGoalAmount] = useState("");
  const [goalBy, setGoalBy] = useState("");
  const savedBills = useRef(new Set<string>());
  const [pendingPlan, setPendingPlan] = useState<ServerProposal | null>(null);
  const [pendingGoal, setPendingGoal] = useState<Proposal | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const billTotal = bills.reduce((s, b) => s + num(b.amount), 0);
  const monthlyIncome = incomeSure === "sure" ? Math.floor(num(income) * EVENTS_PER_YEAR[frequency] / 12) : 0;
  const flexible = monthlyIncome - billTotal - num(essentials) - num(buffer);
  const canNext = [(parseSatang(balance) ?? -1) >= 0 && !!asOf, (parseSatang(income) ?? 0) > 0 && !!nextIncome && incomeSure === "sure", true, true][step] ?? true;
  const makePlan = async () => {
    const bufferAmount = buffer.trim() ? parseSatang(buffer) : 0;
    if (bufferAmount === null) throw new Error("Check the safety buffer amount.");
    const existing = await api<{name:string;categories:string[]}[]>("/pockets");
    for (const [name, category] of [["Food", "food"], ["Transport", "transport"], ["Shopping", "shopping"], ["Leisure", "entertainment"], ["Other", "other"]]) {
      if (!existing.some(p => p.name === name || p.categories.includes(category))) await api("/pockets", {method:"POST",body:JSON.stringify({name,categories:[category]})});
    }
    setPendingPlan(await api<ServerProposal>(`/plan/suggest?buffer_satang=${bufferAmount}`, {method:"POST"}));
  };
  const finish = async (skipGoal = false) => {
    if (saving) return;
    setSaving(true); setError(null);
    try {
      const amount = parseSatang(balance);
      const pay = parseSatang(income);
      const essentialsAmount = essentials.trim() ? parseSatang(essentials) : 0;
      if (amount === null || pay === null || pay <= 0 || essentialsAmount === null || !nextIncome) throw new Error("Check your balance, income, and essentials amounts.");
      const namedBills = bills.filter((bill) => bill.name.trim() || bill.amount.trim() || bill.due.trim());
      const billPayloads = namedBills.map((bill) => {
        const due = bill.due;
        const value = parseSatang(bill.amount);
        if (!bill.name.trim() || value === null || value <= 0 || !due) throw new Error("Each bill needs a name, positive amount, and due date.");
        return { biller: bill.name.trim(), amount_due_satang: value, due_date: due };
      });
      const target = goalAmount.trim() ? parseSatang(goalAmount) : null;
      if (!skipGoal && (goalName.trim() || goalAmount.trim() || goalBy) && (!goalName.trim() || target === null || target <= 0 || !goalBy)) {
        throw new Error("A goal needs a name, positive amount, and deadline. You can also skip it for now.");
      }
      await api("/me/profile", { method: "PUT", body: JSON.stringify({
        income_satang: pay, income_frequency: frequency, next_income_date: nextIncome,
        timezone: "Asia/Bangkok", essentials: essentialsAmount > 0 ? [{ name: "Everyday essentials", amount_satang: essentialsAmount, due_day: 1 }] : [],
      }) });
      const accounts = await api<{ id: string; kind: string }[]>("/accounts");
      const account = accounts.find((a) => a.kind === "spending");
      if (!account) throw new Error("No spending account is available for this profile.");
      await api(`/accounts/${account.id}/balance-observations`, { method: "POST", body: JSON.stringify({ amount_satang: amount, as_of_date: asOf }) });
      const currentBills = await api<{biller:string;amount_due_satang:number;due_date:string}[]>("/bills");
      for (const bill of billPayloads) {
        const key = JSON.stringify(bill);
        if (!savedBills.current.has(key) && !currentBills.some(b => b.biller === bill.biller && b.amount_due_satang === bill.amount_due_satang && b.due_date === bill.due_date)) {
          await api("/bills", { method: "POST", body: key }); savedBills.current.add(key);
        }
      }
      if (!skipGoal && goalName.trim() && goalAmount.trim() && goalBy) {
        const proposal = await createGoalProposal({ name: goalName.trim(), target_satang: target!, saved_satang: 0, deadline: goalBy, contribution_satang_per_period: 0 });
        setPendingGoal(proposal);
      } else await makePlan();
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setSaving(false); }
  };
  const approveGoal = async () => {
    if (!pendingGoal || saving) return;
    setSaving(true); setError(null);
    try { await approveProposal(pendingGoal); setPendingGoal(null); await makePlan(); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setSaving(false); }
  };

  if (step === -1) {
    return (
      <div className="mx-auto flex min-h-dvh w-full max-w-[430px] flex-col bg-background px-[18px] pt-[max(48px,env(safe-area-inset-top))] pb-[max(24px,env(safe-area-inset-bottom))]">
        <span className="grid size-16 place-items-center rounded-[20px] bg-mint text-ink">
          <Sparkles className="size-8" aria-hidden />
        </span>
        <h1 className="mt-6 text-[32px] leading-10 font-extrabold tracking-tight">
          Hi, I&apos;m <span className="text-mint-text">Pocket Pal</span>
        </h1>
        <p className="mt-3 text-[17px] leading-6 text-muted-foreground">
          Tell me what you want to do with your money. I&apos;ll check your situation, show your options, and help you update your plan.
        </p>

        <div className="mt-auto flex flex-col gap-2.5 pt-10">
          <button type="button" onClick={() => setCsvNote("Demo data is unavailable for this account. Set up with your own numbers to continue.")} className="flex min-h-14 items-center justify-center gap-2.5 rounded-[var(--radius-ctl)] bg-ink text-base font-bold text-white">
            <Database className="size-5" aria-hidden />
            Try it with demo data
          </button>
          <button type="button" onClick={() => setStep(0)} className="min-h-14 rounded-[var(--radius-ctl)] bg-mint text-base font-bold text-ink">
            Set up with my numbers
          </button>
          <input
            ref={csvInput}
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              // CSV import isn't built yet; acknowledge the file without pretending it was read.
              if (f) setCsvNote(`Got ${f.name}. Importing CSV files is coming soon. For now, set up with your numbers or try the demo.`);
            }}
          />
          <button type="button" onClick={() => csvInput.current?.click()} className="flex min-h-12 items-center justify-center gap-2 text-[15px] font-semibold text-muted-foreground">
            <FileUp className="size-5" aria-hidden />
            Import a bank CSV
          </button>
          {csvNote && (
            <p role="status" className="rounded-2xl bg-card px-3.5 py-3 text-sm shadow-[var(--shadow-card)]">
              {csvNote}
            </p>
          )}
          <p className="text-center text-[13px] leading-[18px] text-muted-foreground">
            This is a planning app. It never moves real money and never asks for your bank password.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-[430px] flex-col bg-background">
      <header className="flex items-center gap-3 px-[18px] pt-[max(16px,env(safe-area-inset-top))] pb-2">
        <button type="button" onClick={() => setStep(step - 1)} aria-label="Back" className="grid size-11 place-items-center rounded-full bg-card shadow-[var(--shadow-card)]">
          <ArrowLeft className="size-5" aria-hidden />
        </button>
        <ol className="flex flex-1 gap-1.5" aria-label={`Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}`}>
          {STEPS.map((s, i) => (
            <li key={s} className={cn("h-1.5 flex-1 rounded-full", i <= step ? "bg-ink" : "bg-[#d0d4da]")} aria-hidden />
          ))}
        </ol>
        <span className="w-11 text-right text-[13px] font-semibold text-muted-foreground">
          {step + 1}/{STEPS.length}
        </span>
      </header>

      <main className="num flex flex-1 flex-col gap-5 px-[18px] pt-4 pb-6">
        {step === 0 && (
          <>
            <div>
              <h1 className="text-2xl leading-[30px] font-extrabold">How much is in your account?</h1>
              <p className="mt-1.5 text-[15px] text-muted-foreground">Your balance right now. It&apos;s a starting point; nothing is connected to your bank.</p>
            </div>
            <div className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
              <Field label="Balance" htmlFor={`${id}-bal`}>
                <BahtInput id={`${id}-bal`} value={balance} onChange={setBalance} />
              </Field>
              <Field label="As of" htmlFor={`${id}-asof`} hint="Spending you import from before this date won't be taken off your balance again.">
                <input id={`${id}-asof`} type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className={input} />
              </Field>
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <div>
              <h1 className="text-2xl leading-[30px] font-extrabold">When does money come in?</h1>
              <p className="mt-1.5 text-[15px] text-muted-foreground">Allowance, salary or part-time pay.</p>
            </div>
            <div className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
              <Field label="Amount each time" htmlFor={`${id}-inc`}>
                <BahtInput id={`${id}-inc`} value={income} onChange={setIncome} />
              </Field>
              <Segmented
                label="How often"
                value={frequency}
                onChange={setFrequency}
                options={[
                  { value: "monthly", label: "Monthly" },
                  { value: "biweekly", label: "Every 2 weeks" },
                  { value: "weekly", label: "Weekly" },
                ]}
              />
              <Field label="Next payday" htmlFor={`${id}-next`}>
                <input id={`${id}-next`} type="date" value={nextIncome} onChange={(e) => setNextIncome(e.target.value)} className={input} />
              </Field>
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-bold">How sure are you?</span>
                <Segmented
                  label="How sure are you?"
                  value={incomeSure}
                  onChange={setIncomeSure}
                  options={[
                    { value: "sure", label: "It's confirmed" },
                    { value: "unsure", label: "Not sure yet" },
                  ]}
                />
                <p className="text-[13px] leading-[18px] text-muted-foreground">
                  {incomeSure === "sure" ? "This income will be used in your plan." : "Unconfirmed income cannot be saved in the current plan yet. Please use confirmed income to continue."}
                </p>
              </div>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <div>
              <h1 className="text-2xl leading-[30px] font-extrabold">What do you have to pay?</h1>
              <p className="mt-1.5 text-[15px] text-muted-foreground">Bills with due dates, and the least you need for everyday essentials.</p>
            </div>
            <div className="flex flex-col gap-3">
              {bills.map((b, i) => (
                <div key={b.id} className="flex flex-col gap-2.5 rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold">Bill {i + 1}</span>
                    {bills.length > 1 && (
                      <button type="button" aria-label={`Remove bill ${i + 1}`} onClick={() => setBills(bills.filter((x) => x.id !== b.id))} className="-mr-2 grid size-11 place-items-center rounded-full text-muted-foreground">
                        <Trash2 className="size-4" aria-hidden />
                      </button>
                    )}
                  </div>
                  <label className="sr-only" htmlFor={`${id}-bn-${b.id}`}>Bill name</label>
                  <input id={`${id}-bn-${b.id}`} value={b.name} placeholder="e.g. Phone, rent" onChange={(e) => setBills(bills.map((x) => (x.id === b.id ? { ...x, name: e.target.value } : x)))} className={input} />
                  <div className="grid grid-cols-2 gap-2.5">
                    <div>
                      <label className="sr-only" htmlFor={`${id}-ba-${b.id}`}>Amount</label>
                      <BahtInput id={`${id}-ba-${b.id}`} value={b.amount} onChange={(v) => setBills(bills.map((x) => (x.id === b.id ? { ...x, amount: v } : x)))} />
                    </div>
                    <div>
                      <label className="sr-only" htmlFor={`${id}-bd-${b.id}`}>Due date</label>
                      <input id={`${id}-bd-${b.id}`} type="date" value={b.due} onChange={(e) => setBills(bills.map((x) => (x.id === b.id ? { ...x, due: e.target.value } : x)))} className={input} />
                    </div>
                  </div>
                </div>
              ))}
              <button type="button" onClick={() => setBills([...bills, { id: Date.now(), name: "", amount: "", due: "" }])} className="flex min-h-12 items-center justify-center gap-2 rounded-[var(--radius-ctl)] border-2 border-dashed border-[#d0d4da] text-[15px] font-semibold text-muted-foreground">
                <Plus className="size-5" aria-hidden />
                Add another bill
              </button>
              <div className="rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
                <Field label="Essentials each month" htmlFor={`${id}-ess`} hint="The least you need for food and getting around. I'll never plan below this.">
                  <BahtInput id={`${id}-ess`} value={essentials} onChange={setEssentials} />
                </Field>
              </div>
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <div>
              <h1 className="text-2xl leading-[30px] font-extrabold">Saving for something?</h1>
              <p className="mt-1.5 text-[15px] text-muted-foreground">Optional. You can add a goal later.</p>
            </div>
            <div className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
              <Field label="Goal" htmlFor={`${id}-gn`}>
                <input id={`${id}-gn`} value={goalName} placeholder="e.g. Trip to Chiang Mai" onChange={(e) => setGoalName(e.target.value)} className={input} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Amount" htmlFor={`${id}-ga`}>
                  <BahtInput id={`${id}-ga`} value={goalAmount} onChange={setGoalAmount} />
                </Field>
                <Field label="By" htmlFor={`${id}-gb`}>
                  <input id={`${id}-gb`} type="date" value={goalBy} onChange={(e) => setGoalBy(e.target.value)} className={input} />
                </Field>
              </div>
            </div>
            <div className="rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
              <Field label="Safety buffer" htmlFor={`${id}-buf`} hint="Money I always keep aside, so a surprise doesn't leave you at zero.">
                <BahtInput id={`${id}-buf`} value={buffer} onChange={setBuffer} />
              </Field>
            </div>
            <section aria-label="First look" className="rounded-[var(--radius-card)] bg-mint-soft p-[18px]">
              <h2 className="text-[15px] font-bold">First look, based on what you told me</h2>
              {flexible >= 0 ? (
                <p className="mt-1 text-sm">
                  About <b className="text-mint-text">{baht(flexible / 100)}</b> a month left for everyday spending after bills, essentials and your buffer. I&apos;ll split it into pockets in the chat.
                </p>
              ) : (
                <p className="mt-1 text-sm">
                  Bills, essentials and your buffer add up to <b>{baht(-flexible / 100)} more</b> than your income. Let&apos;s look at it together in the chat.
                </p>
              )}
              <p className="mt-2 text-[13px] text-muted-foreground">This simple monthly estimate is based only on the amounts above. Your live plan uses dates and confirmed records.</p>
            </section>
          </>
        )}
      </main>

      <div className="sticky bottom-0 border-t border-line bg-card px-[18px] pt-3 pb-[max(14px,env(safe-area-inset-bottom))]">
        {error && <p role="alert" className="mb-2 rounded-xl bg-danger-soft p-3 text-sm text-danger">{error}</p>}
        {pendingPlan && <ServerActionCard initial={pendingPlan} onChanged={() => router.push("/pockets")} />}
        {pendingGoal && <div className="mb-3 rounded-xl bg-mint-soft p-3 text-sm">
          <strong>Review your goal</strong>
          <p>{pendingGoal.card.summary?.text}</p>
          {pendingGoal.card.warnings?.map((w, i) => <p key={i} className="mt-1">{w.text}</p>)}
          <p className="mt-1">Your goal is not saved until you approve.</p>
        </div>}
        <button
          type="button"
          disabled={!canNext || saving || !!pendingPlan}
          onClick={() => (pendingGoal ? approveGoal() : step === STEPS.length - 1 ? finish(false) : setStep(step + 1))}
          className="min-h-[52px] w-full rounded-[var(--radius-ctl)] bg-ink text-[15px] font-bold text-white disabled:opacity-40"
        >
          {saving ? "Saving…" : pendingGoal ? "Approve goal" : step === STEPS.length - 1 ? "Make my plan" : "Continue"}
        </button>
        {(step === 2 || step === 3) && (
          <button type="button" disabled={saving} onClick={() => (pendingGoal ? (setPendingGoal(null), void makePlan().catch(e => setError(errorMessage(e)))) : step === 3 ? finish(true) : setStep(step + 1))} className="mt-1 min-h-11 w-full text-sm font-semibold text-muted-foreground">
            {pendingGoal ? "Leave goal for later" : "Skip for now"}
          </button>
        )}
      </div>
    </div>
  );
}
