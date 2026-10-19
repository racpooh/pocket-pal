"use client";

import { ArrowLeft, Check, ChevronRight, Lock, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { GalleryControls } from "@/components/native/gallery-controls";
import { api } from "@/lib/api";
import { clearChatMemory } from "@/lib/chat-memory";
import { errorMessage, formatSatang, parseSatang } from "@/lib/goals";

type Profile = {
  timezone: string;
  income: { amount_satang: number; frequency: "monthly" | "biweekly" | "weekly" | "irregular"; next_income_date: string } | null;
  essentials: { name: string; amount_satang: number; due_day: number }[];
};
type Consent = { scope: string; granted_at: string | null; revoked_at: string | null };
type Audit = { action: string; result: string; at: string; details: Record<string, unknown> | null };

type Scope = "photo_processing" | "auto_import" | "chat_history_retention";
const scopes: { key: Scope; name: string }[] = [
  { key: "photo_processing", name: "Photo processing" },
  { key: "auto_import", name: "Automatic import" },
  { key: "chat_history_retention", name: "Chat history retention" },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section aria-label={title} className="flex flex-col gap-2"><h2 className="px-1 text-[13px] font-bold tracking-[0.06em] text-muted-foreground uppercase">{title}</h2>{children}</section>;
}

export function Settings() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [consents, setConsents] = useState<Consent[]>([]);
  const [changes, setChanges] = useState<Audit[]>([]);
  const [editing, setEditing] = useState(false);
  const [income, setIncome] = useState("");
  const [frequency, setFrequency] = useState<NonNullable<Profile["income"]>["frequency"]>("monthly");
  const [nextIncome, setNextIncome] = useState("");
  const [essentials, setEssentials] = useState("");
  const [confirming, setConfirming] = useState<"uploads" | "all" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    const [p, c, a] = await Promise.all([
      api<Profile>("/me/profile"), api<Consent[]>("/consents"), api<Audit[]>("/audit?limit=10"),
    ]);
    setProfile(p); setConsents(c); setChanges(a);
    setIncome(p.income ? String(p.income.amount_satang / 100) : "");
    setFrequency(p.income?.frequency ?? "monthly");
    setNextIncome(p.income?.next_income_date ?? "");
    setEssentials(String(p.essentials.reduce((sum, e) => sum + e.amount_satang, 0) / 100));
  };
  useEffect(() => { void refresh().catch((error) => setNotice(errorMessage(error))); }, []);

  const saveProfile = async () => {
    const pay = parseSatang(income); const essential = parseSatang(essentials || "0");
    if (pay === null || pay <= 0 || essential === null || !nextIncome) { setNotice("Enter a positive income, essentials amount, and next payday."); return; }
    setBusy(true); setNotice(null);
    try {
      const updated = await api<Profile>("/me/profile", { method: "PUT", body: JSON.stringify({
        income_satang: pay, income_frequency: frequency, next_income_date: nextIncome,
        timezone: profile?.timezone || "Asia/Bangkok",
        essentials: essential > 0 ? [{ name: "Everyday essentials", amount_satang: essential, due_day: 1 }] : [],
      }) });
      setProfile(updated); setEditing(false); setNotice("Profile saved.");
      await refresh();
    } catch (error) { setNotice(errorMessage(error)); }
    finally { setBusy(false); }
  };

  const toggleConsent = async (scope: Scope, enabled: boolean) => {
    if (enabled && scope === "photo_processing") { router.push("/connect"); return; }
    if (!enabled && scope === "photo_processing") window.PocketPalNative?.pause();
    setBusy(true); setNotice(null);
    try {
      if (enabled) await api("/consents", { method: "POST", body: JSON.stringify({ scope, version: "1", params: {} }) });
      else { await api(`/consents/${scope}`, { method: "DELETE" }); if(scope === "chat_history_retention") clearChatMemory(); }
      setConsents(await api<Consent[]>("/consents"));
      setNotice(`${scopes.find((s) => s.key === scope)?.name} ${enabled ? "enabled" : "disabled"}.`);
    } catch (error) { setNotice(errorMessage(error)); }
    finally { setBusy(false); }
  };

  const deleteData = async () => {
    if (confirming !== "uploads") return;
    setBusy(true); setNotice(null);
    try {
      const result = await api<{ uploads_processed: number; records_removed: number; images_pending_purge: number; complete: boolean }>("/data/delete", {
        method: "POST", body: JSON.stringify({ scope: "imported" }),
      });
      setNotice(result.complete
        ? `Removed ${result.uploads_processed} imports and their associated records. Other account data remains.`
        : `Removed ${result.uploads_processed} imports; ${result.images_pending_purge} image purges are pending retry.`);
      setConfirming(null); await refresh();
    } catch (error) { setNotice(errorMessage(error)); }
    finally { setBusy(false); }
  };

  const logout = async () => {
    window.PocketPalNative?.pause();
    setBusy(true); setNotice(null);
    try {
      const response = await fetch("/api/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "logout" }) });
      if (!response.ok) throw new Error("Could not sign out. Please try again.");
      location.assign("/connect");
    } catch (error) { setNotice(errorMessage(error)); setBusy(false); }
  };

  return <div className="mx-auto flex min-h-dvh w-full max-w-[430px] flex-col bg-background">
    <header className="flex items-center gap-3 px-[18px] pt-[max(16px,env(safe-area-inset-top))] pb-2">
      <button type="button" onClick={() => router.back()} aria-label="Back" className="grid size-11 place-items-center rounded-full bg-card shadow-[var(--shadow-card)]"><ArrowLeft className="size-5" aria-hidden /></button>
      <h1 className="text-2xl leading-[30px] font-extrabold tracking-tight">Settings</h1>
    </header>
    <main className="num flex flex-1 flex-col gap-6 px-[18px] pt-3 pb-10">
      {notice && <p role="status" className="rounded-2xl bg-mint-soft px-3.5 py-3 text-sm font-semibold">{notice}</p>}
      <Section title="Recent changes">
        <ul className="rounded-[var(--radius-card)] bg-card px-3.5 shadow-[var(--shadow-card)]">
          {changes.length === 0 && <li className="py-4 text-sm text-muted-foreground">No recorded changes yet.</li>}
          {changes.map((c, index) => <li key={`${c.at}-${index}`} className="flex items-center gap-3 border-t border-line py-3 first:border-t-0">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-mint-soft text-mint-text"><Check className="size-5" aria-hidden /></span>
            <div className="min-w-0 flex-1"><div className="text-[15px] leading-5 font-bold">{c.action.replaceAll("_", " ")}</div><div className="text-[13px] text-muted-foreground">{new Date(c.at).toLocaleString()} · {c.result}</div></div>
          </li>)}
        </ul>
      </Section>
      <Section title="Profile">
        <div className="rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
          {profile ? <>
            <div className="flex items-center justify-between"><strong className="text-[15px]">Income and essentials</strong><button type="button" onClick={() => setEditing(!editing)} className="flex items-center gap-1 text-sm font-semibold">{editing ? "Cancel" : "Change"}<ChevronRight className="size-4" /></button></div>
            {!editing ? <div className="mt-2 space-y-1 text-sm"><p>{profile.income ? `${formatSatang(profile.income.amount_satang)} ${profile.income.frequency} · next ${profile.income.next_income_date}` : "No income saved"}</p><p>Essentials: {formatSatang(profile.essentials.reduce((sum, e) => sum + e.amount_satang, 0))} per month</p></div> :
              <div className="mt-3 space-y-2 text-sm">
                <label className="block">Income amount (฿)<input className="mt-1 h-11 w-full rounded-xl bg-background px-3" inputMode="decimal" value={income} onChange={(e) => setIncome(e.target.value)} /></label>
                <label className="block">How often<select className="mt-1 h-11 w-full rounded-xl bg-background px-3" value={frequency} onChange={(e) => setFrequency(e.target.value as typeof frequency)}><option value="monthly">Monthly</option><option value="biweekly">Every two weeks</option><option value="weekly">Weekly</option><option value="irregular">Irregular</option></select></label>
                <label className="block">Next payday<input className="mt-1 h-11 w-full rounded-xl bg-background px-3" type="date" value={nextIncome} onChange={(e) => setNextIncome(e.target.value)} /></label>
                <label className="block">Essentials per month (฿)<input className="mt-1 h-11 w-full rounded-xl bg-background px-3" inputMode="decimal" value={essentials} onChange={(e) => setEssentials(e.target.value)} /></label>
                <p className="text-xs text-muted-foreground">Saving replaces your existing essentials schedule with this monthly total.</p>
                <button type="button" disabled={busy} onClick={saveProfile} className="min-h-11 w-full rounded-xl bg-ink font-bold text-white disabled:opacity-40">Save profile</button>
              </div>}
          </> : <p className="text-sm text-muted-foreground">Loading your profile…</p>}
        </div>
      </Section>
      <GalleryControls />
      <Section title="Your data">
        <div className="rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
          <div className="flex items-center gap-2 text-[15px] font-bold"><Lock className="size-4 text-mint-text" aria-hidden />What Pocket Pal uses</div>
          <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-sm leading-5 text-muted-foreground"><li>The numbers you enter and the transactions you confirm.</li><li>Photos you choose to upload, plus likely slips found by gallery scanning if you enable it in the Android app.</li><li>No bank passwords. This app never moves real money.</li></ul>
        </div>
        <div className="rounded-[var(--radius-card)] bg-card px-4 shadow-[var(--shadow-card)]">
          {scopes.map((s) => { const active = consents.some((c) => c.scope === s.key && !c.revoked_at); return <div key={s.key} className="flex min-h-14 items-center justify-between border-t border-line first:border-t-0"><span className="text-sm font-semibold">{s.name}</span><button type="button" disabled={busy} aria-label={`${active ? "Disable" : "Enable"} ${s.name}`} aria-pressed={active} onClick={() => toggleConsent(s.key, !active)} className="min-h-11 rounded-xl bg-background px-3 text-sm font-bold disabled:opacity-40">{active ? "On" : "Off"}</button></div>; })}
        </div>
        {confirming ? <div role="alertdialog" aria-label="Confirm deletion" className="rounded-[var(--radius-card)] bg-danger-soft p-[18px]">
          <p className="text-[15px] font-bold text-danger">{confirming === "all" ? "Full account deletion is unavailable" : "Delete imported data?"}</p>
          <p className="mt-1 text-sm text-danger">{confirming === "all" ? "This version cannot erase your profile, goals, pockets, and account. Imported records can be deleted below." : "This removes uploads and records imported from them. Image purges may need a retry; the result will say if any remain."}</p>
          <div className="mt-3 grid grid-cols-2 gap-2.5">{confirming === "uploads" && <button type="button" disabled={busy} onClick={deleteData} className="min-h-12 rounded-[var(--radius-ctl)] bg-danger text-sm font-bold text-white disabled:opacity-40">Yes, delete</button>}<button type="button" onClick={() => setConfirming(null)} className="min-h-12 rounded-[var(--radius-ctl)] bg-card text-sm font-bold">{confirming === "all" ? "Close" : "Keep it"}</button></div>
        </div> : <div className="grid gap-2.5"><button type="button" onClick={() => setConfirming("uploads")} className="flex min-h-12 items-center justify-center gap-2 rounded-[var(--radius-ctl)] bg-card text-[15px] font-bold shadow-[var(--shadow-card)]"><Trash2 className="size-4" aria-hidden />Delete imported data and photos</button><button type="button" onClick={() => setConfirming("all")} className="flex min-h-12 items-center justify-center gap-2 rounded-[var(--radius-ctl)] text-[15px] font-bold text-danger"><Trash2 className="size-4" aria-hidden />Delete all my data</button></div>}
      </Section>
      <button type="button" disabled={busy} onClick={logout} className="min-h-12 rounded-[var(--radius-ctl)] bg-card text-[15px] font-bold shadow-[var(--shadow-card)] disabled:opacity-40">Sign out</button>
    </main>
  </div>;
}
