"use client";

import { AlertCircle, Check, ChevronDown, Loader2, Lock, RefreshCw, X } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export type ServerProposal = {
  proposal_id: string;
  kind: string;
  status: string;
  payload: Record<string, unknown>;
  payload_hash: string;
  card_hash: string | null;
  card: {
    summary: { text: string };
    changes: Record<string, unknown>[];
    warnings: { text: string; severity: string }[];
    uncertainty: { text: string }[];
    assumptions: { text: string }[];
    not_computed: { item: string; reason_code: string }[];
    effects?: Record<string, unknown>;
    period?: { start: string; end_exclusive: string };
  } | null;
  actions: { action: string; body?: Record<string, string> }[];
};

type Props = { initial: ServerProposal; onChanged?: () => void; onEdit?: (proposal: ServerProposal) => void };
function satang(value: unknown) {
  if (typeof value !== "number" || !Number.isInteger(value)) return String(value ?? "—");
  const negative = value < 0 ? "−" : "";
  const digits = String(Math.abs(value));
  const whole = (digits.length > 2 ? digits.slice(0, -2) : "0").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${negative}฿${whole}.${digits.slice(-2).padStart(2, "0")}`;
}
function detail(change: Record<string, unknown>) {
  if (typeof change.name === "string" && "allocation_after_satang" in change) return `${change.name}: ${satang(change.allocation_before_satang)} → ${satang(change.allocation_after_satang)}`;
  if (typeof change.field === "string") {
    const money = change.field.endsWith("_satang");
    return `${change.field.replaceAll("_", " ")}: ${money ? satang(change.before) : String(change.before ?? "New")} → ${money ? satang(change.after) : String(change.after ?? "—")}`;
  }
  return "Change in this proposal";
}

export function ServerActionCard({ initial, onChanged, onEdit }: Props) {
  const [proposal, setProposal] = useState(initial);
  const [approvalKey, setApprovalKey] = useState(() => crypto.randomUUID());
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const card = proposal.card;
  if (!card) return null;
  const pending = proposal.status === "pending";
  const approveAction = proposal.actions?.find((action) => action.action === "approve");
  const run = async (action: "approve" | "cancel") => {
    setBusy(true); setError(null);
    try {
      const body = action === "approve" ? (approveAction?.body || { payload_hash: proposal.payload_hash, card_hash: proposal.card_hash }) : undefined;
      const result = await api<Record<string, unknown>>(`/proposals/${proposal.proposal_id}/${action}`, {
        method: "POST",
        headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...(action === "approve" ? { "Idempotency-Key": approvalKey } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (typeof result.status === "string") setProposal((current) => ({ ...current, status: result.status as string, actions: [] }));
      else {
        const refreshed = await api<ServerProposal>(`/proposals/${proposal.proposal_id}`);
        setProposal(refreshed);
      }
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update this proposal.");
      const code = cause && typeof cause === "object" && "code" in cause ? String(cause.code) : "";
      if (cause instanceof ApiError && cause.details.replacement) {
        setProposal(cause.details.replacement as ServerProposal);
        setApprovalKey(crypto.randomUUID());
        return;
      }
      if (["PROPOSAL_STALE", "PROPOSAL_EXPIRED", "PROPOSAL_NOT_PENDING"].includes(code)) {
        try { setProposal(await api<ServerProposal>(`/proposals/${proposal.proposal_id}`)); } catch { /* Original error remains visible. */ }
      }
    } finally { setBusy(false); }
  };
  return <article className="rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]" aria-label="Proposed change">
    <div className="flex items-center gap-2 rounded-full bg-mint-soft px-3 py-2 text-[13px] leading-[18px]"><Lock className="size-3.5 shrink-0 text-mint-text" /><span><b className="text-mint-text">Balance unchanged</b> · {pending ? "Approval required" : proposal.status}</span></div>
    <div className="num mt-4 text-[20px] leading-7 font-extrabold">{card.summary.text}</div>
    {card.changes.length > 0 && <div className="mt-3 rounded-2xl bg-background px-3 py-2.5 text-[13px]">{card.changes.slice(0, open ? undefined : 2).map((change, index) => <div key={index} className="py-1">{detail(change)}</div>)}</div>}
    {card.changes.length > 2 && <button type="button" className="mt-1 flex min-h-11 w-full items-center justify-center gap-1 text-sm font-semibold text-muted-foreground" onClick={() => setOpen(!open)}>{open ? "Hide details" : `See all ${card.changes.length} changes`}<ChevronDown className={cn("size-4", open && "rotate-180")} /></button>}
    {card.effects && ["money_left", "buffer", "unspent_budget"].map((key) => {
      const effect = card.effects?.[key] as { before_satang?: number; after_satang?: number } | undefined;
      return effect?.before_satang !== undefined && effect.after_satang !== undefined ? <p key={key} className="mt-2 text-sm">{key.replaceAll("_", " ")}: {satang(effect.before_satang)} → {satang(effect.after_satang)}</p> : null;
    })}
    {card.warnings.map((warning, index) => <p key={`w${index}`} className={cn("mt-3 rounded-2xl px-3.5 py-3 text-[13px]", warning.severity === "high" ? "bg-danger-soft text-danger" : "bg-background text-muted-foreground")}>{warning.severity === "high" && <AlertCircle className="mr-1 inline size-4" />}{warning.text}</p>)}
    {card.uncertainty.map((item, index) => <p key={`u${index}`} className="mt-2 text-[13px] text-muted-foreground">{item.text}</p>)}
    {card.assumptions.map((item, index) => <p key={`a${index}`} className="mt-2 text-[13px] text-muted-foreground">Assumption: {item.text}</p>)}
    {card.not_computed.map((item, index) => <p key={`n${index}`} className="mt-2 text-[13px] text-muted-foreground">{item.item.replaceAll("_", " ")} unavailable: {item.reason_code.replaceAll("_", " ")}</p>)}
    {error && <p role="alert" className="mt-3 rounded-2xl bg-danger-soft px-3.5 py-3 text-sm text-danger">{error}</p>}
    {pending ? <><button type="button" disabled={busy || !approveAction} onClick={() => run("approve")} className="mt-4 flex min-h-[52px] w-full items-center justify-center gap-2 rounded-[var(--radius-ctl)] bg-ink text-[15px] font-bold text-white disabled:opacity-50">{busy ? <Loader2 className="size-4 animate-spin" /> : null}{busy ? "Applying…" : "Approve change"}</button><div className="mt-1 flex justify-center gap-2"><button type="button" disabled={busy} onClick={() => onEdit ? onEdit(proposal) : window.location.assign("/?ask=" + encodeURIComponent("Help me revise the amounts in my pending plan. Show a new proposal for approval."))} className="min-h-11 px-4 text-[15px] font-semibold">Edit amounts</button><span className="self-center text-line">|</span><button type="button" disabled={busy} onClick={() => run("cancel")} className="min-h-11 px-4 text-[15px] font-semibold text-muted-foreground">Not now</button></div></> : <div role="status" className="mt-3 flex items-center gap-2 rounded-2xl bg-background p-3 text-sm font-semibold">{proposal.status === "applied" ? <Check className="size-5 text-mint-text" /> : proposal.status === "cancelled" ? <X className="size-5" /> : <RefreshCw className="size-5" />}{proposal.status === "applied" ? "Applied" : proposal.status === "cancelled" ? "Cancelled" : `Proposal ${proposal.status}`}</div>}
  </article>;
}
