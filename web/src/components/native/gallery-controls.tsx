"use client";

import { useEffect, useState } from "react";

type NativeStatus = {
  available: boolean; enabled: boolean; busy?: boolean; permission: "full" | "selected" | "denied";
  owner_bound?: boolean; windowDays: number; dailyLimit: number; attemptsToday: number;
  lastScan: number; message: string; scanned?: number; candidates?: number; uploaded?: number;
  diagnostics?: { stage?: string; updatedAt?: number; filterVersion?: string; permissionMode?: string; visibleTotal?: number; undated?: number; olderThanWindow?: number; futureDated?: number; alreadyUploaded?: number; alreadyFiltered?: number; serverRefusedBefore?: number; legacyRechecked?: number; unreadable?: number; filteredMoneyOnly?: number; inWindow?: number; alreadyChecked?: number; unsupported?: number; outsideConsent?: number; checked?: number; filteredOut?: number; candidates?: number; accepted?: number; lastHttpStatus?: number };
  skipped_undated?: number; daily_remaining?: number;
};
type GalleryBridge = { getStatus: () => string; configure: (enabled: boolean) => void; scanNow: () => void; requestPermission: () => void; pause: () => void };
declare global { interface Window { PocketPalNative?: GalleryBridge } }

export function useNativeGallery() {
  const [status, setStatus] = useState<NativeStatus | null>(null);
  useEffect(() => {
    const read = () => {
      try {
        const raw = window.PocketPalNative?.getStatus();
        if (raw) { const value = JSON.parse(raw); if (value.available === true) setStatus(value); }
      } catch { /* Bridge may not have delivered its first status yet. */ }
    };
    read();
    const receive = (event: Event) => {
      const value = (event as CustomEvent<NativeStatus>).detail;
      if (value?.available === true) setStatus(value);
    };
    window.addEventListener("pocketpal-native-status", receive);
    const timer = window.setInterval(read, 1500);
    return () => { window.clearInterval(timer); window.removeEventListener("pocketpal-native-status", receive); };
  }, []);
  return status;
}

export function GalleryControls() {
  const status = useNativeGallery();
  const [agreed, setAgreed] = useState(false);
  if (!status) return null;
  return <section aria-label="Gallery scanning" className="rounded-[var(--radius-card)] bg-card p-[18px] shadow-[var(--shadow-card)]">
    <h2 className="text-lg font-bold">Slips from the last 30 days</h2>
    <p className="mt-2 text-sm text-muted-foreground">The app checks accessible photos on this phone for likely slips. Only matching photos with a capture date within the last 30 days and your allowed date range are sent for processing. Dates that cannot be verified are skipped.</p>
    <p className="mt-2 text-sm">Photo access: <b>{status.permission === "full" ? "All photos" : status.permission === "selected" ? "Selected photos only" : "Not allowed"}</b>. {status.permission === "selected" && "Only photos you selected can be scanned."}</p>
    <p className="mt-2 text-sm">{status.enabled ? "Automatic scanning enabled" : "Scanning paused"} · {status.busy ? "Scanning…" : "Idle"}</p>
    <p className="mt-2 text-xs text-muted-foreground">Up to 10 candidates per scan and 20 upload attempts per day. Android may delay background scans. The local filter can miss slips (it reads digits and English words, not Thai words); use manual upload for missed photos.</p>
    {!status.enabled && <label className="mt-3 flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={agreed} onChange={e => setAgreed(e.target.checked)} />I allow likely slips in this date window to be sent automatically. With real OCR, these photos are sent to Anthropic and use API credit.</label>}
    <div className="mt-3 flex flex-wrap gap-2">
      <button type="button" className="min-h-11 rounded-xl bg-background px-3 text-sm font-bold" onClick={() => window.PocketPalNative?.requestPermission()}>Choose photo access</button>
      {status.enabled ? <button type="button" className="min-h-11 rounded-xl bg-background px-3 text-sm font-bold" onClick={() => {window.PocketPalNative?.pause(); setAgreed(false);}}>Pause scanning</button> : <button type="button" disabled={!agreed} className="min-h-11 rounded-xl bg-ink px-3 text-sm font-bold text-white disabled:opacity-40" onClick={() => window.PocketPalNative?.configure(true)}>Enable scanning</button>}
      <button type="button" disabled={!status.enabled || status.busy} className="min-h-11 rounded-xl bg-mint px-3 text-sm font-bold disabled:opacity-40" onClick={() => window.PocketPalNative?.scanNow()}>Scan now</button>
    </div>
    {status.message && <p role="status" className="mt-3 rounded-xl bg-background p-3 text-sm">{status.message}</p>}
    {status.diagnostics?.stage && <div className="mt-3 rounded-xl bg-background p-3 text-sm" aria-label="Scan diagnostics">
      <p className="font-bold">Scan monitor: {status.diagnostics.stage.replaceAll("_", " ")}</p>
      <dl className="mt-2 grid grid-cols-2 gap-2">
        {([
          ["Photos Pocket Pal can see", status.diagnostics.visibleTotal],
          ["No capture date (never sent automatically)", status.diagnostics.undated],
          ["Captured more than 30 days ago", status.diagnostics.olderThanWindow],
          ["Accessible photos dated within 30 days", status.diagnostics.inWindow],
          ["Already checked in earlier scans", status.diagnostics.alreadyChecked],
          ["Already sent before (not sent again)", status.diagnostics.alreadyUploaded],
          ["Rechecked with the updated filter", status.diagnostics.legacyRechecked],
          ["Unsupported format or size", status.diagnostics.unsupported],
          ["Outside your consent dates", status.diagnostics.outsideConsent],
          ["Read locally this scan", status.diagnostics.checked],
          ["Not matched by local slip filter", status.diagnostics.filteredOut],
          ["Unmatched but showing an amount", status.diagnostics.filteredMoneyOnly],
          ["Could not be read", status.diagnostics.unreadable],
          ["Likely slips", status.diagnostics.candidates],
          ["Accepted by server", status.diagnostics.accepted],
        ] as const).map(([label, count]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="font-bold">{count ?? 0}</dd></div>)}
      </dl>
      {status.diagnostics.lastHttpStatus && <p className="mt-2">Last upload HTTP status: {status.diagnostics.lastHttpStatus}</p>}
      <p className="mt-2 text-xs text-muted-foreground">Counts describe this scan, not completed imports. Photos without a capture date (for example, images saved or copied from another app) are never sent automatically; upload them in Chat. Photos that did not match an older filter version are checked once more on this phone; photos already sent are never sent again. Use manual upload for a missed slip.{status.diagnostics.filterVersion && ` Local filter v${status.diagnostics.filterVersion}.`}</p>
    </div>}
    {status.lastScan > 0 && <p className="mt-2 text-xs text-muted-foreground">Last scan: {new Date(status.lastScan).toLocaleString()}</p>}
    <p className="mt-2 text-xs text-muted-foreground">Upload attempts today: {status.attemptsToday} / {status.dailyLimit}. Sending a photo does not mean OCR or import has completed; check Activity for the result.</p>
  </section>;
}
