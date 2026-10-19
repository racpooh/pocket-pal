"use client";

import { Check, Lightbulb, Loader2, Paperclip, SendHorizontal, Sparkles } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ServerActionCard, type ServerProposal } from "@/components/action-card/server-action-card";
import { ConnectedReviewSheet, type ReviewItem, type ReviewResolution } from "@/components/review-sheet/connected-review-sheet";
import { TabBar } from "@/components/tab-bar";
import { ChatReply as FormattedReply } from "@/components/chat-reply";
import { api } from "@/lib/api";
import { useChatMemory, currentChat, changeChat, bindChatOwner, restartChat, type ChatEntry } from "@/lib/chat-memory";

const ACCEPTED_TYPES = ["image/jpeg", "image/png"];
const MAX_BYTES = 8 * 1024 * 1024;
const QUICK_PROMPTS = ["Budget this month", "What did I spend most on?", "Set a goal"];
type ChatReply = { reply: string; cards: { proposal_id?: string; type?:string; amount_satang?:number; affordable?:boolean; daily_allowance_before_satang?:number; daily_allowance_after_satang?:number; shortage_after_satang?:number }[] };
type Entry = ChatEntry;
type History = {retention_enabled:boolean; messages:{id:string;role:"user"|"assistant";content:{text:string;proposal_ids?:string[]}}[]};
type InsightRecommendation = { category: string; last_month_satang: number; average_satang: number; estimated_savings_per_month_satang: number; basis: string };
type Insights = { recommendations?: InsightRecommendation[] };
type Plan = { cashflow: { discretionary_satang: number; daily_allowance_satang: number; next_income_date?: string } };
type Upload = { file: File; imageUrl: string; confirmed: boolean; uploadId?: string; status?: string };
function money(value: number) {
  const negative = value < 0 ? "−" : "";
  const digits = String(Math.abs(value));
  const whole = (digits.length > 2 ? digits.slice(0, -2) : "0").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${negative}฿${whole}.${digits.slice(-2).padStart(2, "0")}`;
}
function errorMessage(cause: unknown) { return cause instanceof Error ? cause.message : "Something went wrong. Please try again."; }

export function ChatTab() {
  const asked = useSearchParams().get("ask");
  const sentAsk = useRef<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const memory = useChatMemory();
  const {entries,draft,sending} = memory;
  const [historyReady,setHistoryReady] = useState(false);
  const [retention,setRetention] = useState(false);
  const setDraft = (draft:string) => {const m=currentChat();if(m.owner)changeChat(m.owner,m.epoch,{draft});};
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [insight, setInsight] = useState<InsightRecommendation | null>(null);
  const [insightShown, setInsightShown] = useState(true);
  const [planError, setPlanError] = useState<string | null>(null);
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [upload, setUpload] = useState<Upload | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [review, setReview] = useState<ReviewItem | null>(null);
  const [savedDocs, setSavedDocs] = useState<string[]>([]);
  const refreshPlan = useCallback(async () => {
    try { const [p, profile] = await Promise.all([api<Plan>("/plan"), api<{income: {next_income_date:string}|null}>("/me/profile")]); setPlan({...p,cashflow:{...p.cashflow,next_income_date:profile.income?.next_income_date}}); setPlanError(null); }
    catch (cause) { setPlan(null); setPlanError(errorMessage(cause)); }
  }, []);
  useEffect(() => {
    let live=true;
    void refreshPlan();
    void api<Insights>("/insights").then((data)=>{if(live)setInsight(data.recommendations?.[0]||null);}).catch(()=>{});
    void (async()=>{
      const me=await api<{user_id:string}>("/me");
      if(!live)return;
      const epoch=bindChatOwner(me.user_id);setOwnerId(me.user_id);
      const h=await api<History>("/chat/messages");
      if(!live || currentChat().owner!==me.user_id || currentChat().epoch!==epoch)return;
      setRetention(h.retention_enabled);
      if(!currentChat().sending && h.retention_enabled){
        const restored:Entry[]=[];
        for(const row of h.messages){
          restored.push({id:row.id,role:row.role,text:row.content.text});
          for(const id of row.content.proposal_ids||[]){
            try{restored.push({id:`proposal-${id}`,role:"proposal",proposal:await api<ServerProposal>(`/proposals/${id}`)});}
            catch{restored.push({id:`proposal-${id}`,role:"status",text:"An earlier proposal is unavailable. Ask for a fresh proposal."});}
          }
        }
        if(live)changeChat(me.user_id,epoch,{entries:restored});
      }else{
        // Refresh retained cards on tab return; never expose an old approval as current.
        const snapshot=currentChat().entries;
        const updated=await Promise.all(snapshot.map(async e=>{
          if(!e.proposal)return e;
          try{return {...e,proposal:await api<ServerProposal>(`/proposals/${e.proposal.proposal_id}`)};}
          catch{return {id:e.id,role:"status" as const,text:"An earlier proposal is unavailable. Ask for a fresh proposal."};}
        }));
        if(live&&!currentChat().sending&&currentChat().entries===snapshot)changeChat(me.user_id,epoch,{entries:updated});
      }
      if(live)setHistoryReady(true);
    })().catch(cause=>{if(live)setError(errorMessage(cause));});
    return()=>{live=false;};
  }, [refreshPlan]);
  const newChat=async()=>{
    if(!ownerId||sending||!window.confirm("Delete this conversation and start a new chat? Your transactions and budgets are not deleted."))return;
    setHistoryReady(false);
    try{await api("/chat/messages",{method:"DELETE"});restartChat(ownerId);setError(null);}
    catch(cause){setError(errorMessage(cause));}
    finally{setHistoryReady(true);}
  };
  const enableMemory=async()=>{
    if(!window.confirm("Save future chat messages on the server so Pocket Pal can remember recent context across visits? You can delete the conversation here or withdraw consent in Settings. Earlier unsaved messages are not uploaded."))return;
    try{await api("/consents",{method:"POST",body:JSON.stringify({scope:"chat_history_retention",version:"1",params:{}})});setRetention(true);}
    catch(cause){setError(errorMessage(cause));}
  };
  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || currentChat().sending || !historyReady || !ownerId) return;
    const epoch=currentChat().epoch;
    const append=(entry:Entry)=>{const m=currentChat();changeChat(ownerId,epoch,{entries:[...m.entries,entry]});};
    changeChat(ownerId,epoch,{sending:true}); setError(null); setDraft("");
    append({ id: crypto.randomUUID(), role: "user", text: trimmed });
    try {
      const response = await api<ChatReply>("/chat/messages", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: trimmed }) });
      if(currentChat().owner!==ownerId||currentChat().epoch!==epoch)return;
      if (response.reply?.trim()) append({ id: crypto.randomUUID(), role: "assistant", text: response.reply });
      for (const card of response.cards || []) {
        if (card.type === "simulation" && typeof card.amount_satang === "number") {
          append({id:crypto.randomUUID(),role:"status",text:`Simulation only — no transaction recorded. Purchase ${money(card.amount_satang!)}: ${card.affordable ? "fits the current plan" : "does not fit the current plan"}. Daily guide ${money(card.daily_allowance_before_satang ?? 0)} → ${money(card.daily_allowance_after_satang ?? 0)}. Shortfall ${money(card.shortage_after_satang ?? 0)}.`});
        }
        if (!card.proposal_id) continue;
        try {
          const proposal = await api<ServerProposal>(`/proposals/${card.proposal_id}`);
          append({ id: crypto.randomUUID(), role: "proposal", proposal });
        } catch (cause) { append({ id: crypto.randomUUID(), role: "status", text: `A proposal was created, but its card could not be loaded: ${errorMessage(cause)}` }); }
      }
      void refreshPlan();
    } catch (cause) { setError(errorMessage(cause)); }
    finally { changeChat(ownerId,epoch,{sending:false}); }
  }, [historyReady, ownerId, refreshPlan]);
  useEffect(() => { if (historyReady && asked && sentAsk.current !== asked) { sentAsk.current = asked; void send(asked); } }, [asked, send, historyReady]);
  const closeUpload = () => { if (upload) URL.revokeObjectURL(upload.imageUrl); setUpload(null); setReview(null); if (fileInput.current) fileInput.current.value = ""; };
  const pickFile = (file: File | undefined) => {
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type)) return setError("That file isn't a JPG or PNG photo. Try a screenshot or photo of the slip.");
    if (file.size > MAX_BYTES) return setError("That photo is over 8 MiB. Try a screenshot or a smaller photo.");
    closeUpload(); setError(null); setUpload({ file, imageUrl: URL.createObjectURL(file), confirmed: false });
  };
  const waitForUpload = async (uploadId: string) => {
    for (let attempt = 0; attempt < 45; attempt++) {
      const current = await api<{ status: string; evidence_of?: {txn_id:string} }>(`/uploads/${uploadId}`);
      setUpload((old) => old ? { ...old, status: current.status } : old);
      if (current.status === "needs_review") {
        const queue = await api<{ items: ReviewItem[] }>("/review-items");
        const item = queue.items.find((candidate) => candidate.upload_id === uploadId);
        if (item) { setReview(item); return; }
      }
      if (["imported", "merged_duplicate", "rejected", "extract_failed", "cancelled_consent"].includes(current.status)) {
        if (current.status === "imported") {
          const records = await api<{id:string;amount_satang:number;payee_display:string|null;occurred_date:string;payment_status:string}[]>("/transactions");
          const record = records.find(t => t.id === current.evidence_of?.txn_id);
          setSavedDocs(old => [...old, record ? `${record.payee_display || "Transaction"} · ${money(record.amount_satang)} · ${record.occurred_date} · ${record.payment_status}` : "Photo imported and recorded"]);
        }
        if (current.status === "merged_duplicate") setSavedDocs((old) => [...old, "Photo matched an existing record"]);
        if (current.status === "rejected") setSavedDocs((old) => [...old, "Photo was not a financial record"]);
        if (current.status === "extract_failed") setError("The photo could not be processed. You can retry the upload.");
        if (current.status === "cancelled_consent") setError("Photo processing consent was withdrawn. Reconnect before retrying.");
        void refreshPlan(); return;
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    setError("The photo is still processing. Check Activity for its review status.");
  };
  const submitUpload = async () => {
    if (!upload || !ownerId || !upload.confirmed || uploadBusy) return;
    setUploadBusy(true); setError(null);
    try {
      const body = new FormData();
      body.append("image", upload.file, "upload" + (upload.file.type === "image/png" ? ".png" : ".jpg"));
      body.append("confirmed_undated", "true");
      body.append("expected_owner_id", ownerId);
      const result = await api<{ upload_id: string; status: string }>("/uploads", { method: "POST", body });
      setUpload((old) => old ? { ...old, uploadId: result.upload_id, status: result.status } : old);
      await waitForUpload(result.upload_id);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setUploadBusy(false); }
  };
  const retryUpload = async () => {
    if (!upload?.uploadId) return;
    setUploadBusy(true); setError(null);
    try { await api(`/uploads/${upload.uploadId}/retry`, { method: "POST" }); await waitForUpload(upload.uploadId); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setUploadBusy(false); }
  };
  const resolved = (result: ReviewResolution) => {
    setSavedDocs((old) => [...old, result.decision === "not_a_transaction" ? "Photo dismissed" : result.decision === "duplicate_of" || result.decision === "link_receipt" ? "Photo linked to an existing record" : "Photo reviewed and recorded"]);
    closeUpload(); void refreshPlan();
  };
  const editProposal = async (proposal: ServerProposal) => {
    const editingMemory=currentChat();
    if(!ownerId || editingMemory.owner!==ownerId)return;
    // The stored proposal is the source of truth. The server creates and displays a new card for every edit.
    const editable = proposal.kind === "reallocate" ? "amount_satang" : proposal.kind === "goal_create" ? "target_satang" : null;
    if (!editable) { setError("Edit this plan in the Budget or Goals tab, then request a fresh proposal."); return; }
    const current = proposal.payload[editable];
    const input = window.prompt(`New ${editable.replaceAll("_", " ")} (integer satang)`, String(current ?? ""));
    if (input === null) return;
    if (!/^\d+$/.test(input) || !Number.isSafeInteger(Number(input)) || Number(input) <= 0) { setError("Enter a positive whole number of satang."); return; }
    try {
      const next = await api<ServerProposal>(`/proposals/${proposal.proposal_id}/edit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payload_hash: proposal.payload_hash, payload: { ...proposal.payload, [editable]: Number(input) } }) });
      changeChat(ownerId,editingMemory.epoch,{entries:[...currentChat().entries,{id:crypto.randomUUID(),role:"proposal",proposal:next}]});
      setError(null);
    } catch (cause) { setError(errorMessage(cause)); }
  };
  return <div className="mx-auto flex min-h-dvh w-full max-w-[430px] flex-col bg-background">
    <header className="sticky top-0 z-10 bg-background/95 px-[18px] pt-[max(12px,env(safe-area-inset-top))] pb-3 backdrop-blur">
      <div className="flex items-center gap-3"><span className="grid size-[42px] place-items-center rounded-xl bg-mint-soft text-mint-text"><Sparkles className="size-5" /></span><div><h1 className="text-lg leading-6 font-extrabold">Pocket Pal</h1><div className="text-[13px] font-semibold text-mint-text">Ready to help</div></div><Link href="/settings" aria-label="Settings" className="ml-auto grid size-11 place-items-center rounded-full bg-mint-soft text-[15px] font-bold text-mint-text">PP</Link></div>
      <div className="num mt-3 flex items-center gap-3 rounded-[18px] bg-card px-3 py-2.5 shadow-[var(--shadow-card)]"><div><div className="text-[13px] leading-[18px] text-muted-foreground">Safe to spend</div><div className="text-xl leading-[26px] font-extrabold">{plan ? money(plan.cashflow.discretionary_satang) : "—"}</div></div><span className="ml-auto rounded-full bg-mint-soft px-2.5 py-1.5 text-[13px] font-bold whitespace-nowrap text-mint-text">{plan ? `${money(plan.cashflow.daily_allowance_satang)} a day` : "Set up your plan"}</span></div>
      {planError && <p className="mt-2 text-xs text-muted-foreground">{planError} <Link href="/connect" className="font-semibold underline">Set up</Link></p>}
    </header>
    <div className="flex items-center gap-2 px-[18px] py-2 text-xs text-muted-foreground"><span className="flex-1">{!historyReady ? "Loading conversation…" : retention ? "Memory on · recent context · up to 200 messages saved" : "Tab memory only · enable memory for follow-up context"}</span>{!retention&&historyReady&&<button onClick={()=>void enableMemory()} className="min-h-11 font-semibold underline">Enable memory</button>}<button disabled={sending||!historyReady} onClick={()=>void newChat()} className="min-h-11 font-semibold underline disabled:opacity-40">New chat</button></div>
    <main className="flex flex-1 flex-col gap-3 px-[18px] pt-2 pb-6">
      {insightShown && insight && <article className="num rounded-[var(--radius-card)] bg-card p-4 shadow-[var(--shadow-card)]"><div className="flex items-center gap-2.5"><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-mint-soft text-mint-text"><Lightbulb className="size-[18px]" /></span><div><div className="text-xs font-bold tracking-[0.06em] text-mint-text uppercase">Insight</div><div className="text-[13px] text-muted-foreground">{insight.basis}</div></div><button type="button" aria-label="Hide this insight" onClick={() => setInsightShown(false)} className="ml-auto grid size-11 place-items-center text-muted-foreground">×</button></div><h3 className="mt-3 text-xl font-extrabold">{insight.category} is up {money(insight.last_month_satang - insight.average_satang)}</h3><div className="mt-3 rounded-2xl bg-mint-soft p-3 text-sm"><b>Aim to spend {money(insight.estimated_savings_per_month_satang)} less next month.</b></div><p className="mt-2 text-[13px] text-muted-foreground">Compare this with your other spending before changing the plan.</p><button type="button" onClick={() => { setInsightShown(false); void send(`Help me plan to spend ${money(insight.estimated_savings_per_month_satang)} less per month on ${insight.category}. Show the tradeoff.`); }} className="mt-3 min-h-12 w-full rounded-[var(--radius-ctl)] bg-ink px-4 text-[15px] font-bold text-white">Plan this change</button></article>}
      {entries.map((entry) => entry.role === "proposal" && entry.proposal ? <ServerActionCard key={entry.id} initial={entry.proposal} onChanged={refreshPlan} onEdit={editProposal} /> : <div key={entry.id} role={entry.role === "status" ? "status" : undefined} className={entry.role === "user" ? "whitespace-pre-wrap break-words max-w-[82%] self-end rounded-[20px] rounded-br-md bg-ink px-4 py-3 text-[15px] leading-[22px] text-white" : "min-w-0 max-w-full self-start rounded-[20px] rounded-bl-md bg-card px-4 py-3 text-[15px] leading-[22px] shadow-[var(--shadow-card)]"}>{entry.role === "assistant" ? <FormattedReply text={entry.text || ""} /> : <span className="whitespace-pre-wrap">{entry.text}</span>}</div>)}
      {sending && <div className="flex items-center gap-2 self-start text-[13px] font-medium text-muted-foreground"><span className="size-2 rounded-full bg-mint" />Thinking…</div>}
      {savedDocs.map((text, index) => <div key={index} role="status" className="flex items-center gap-3 rounded-[var(--radius-card)] bg-card px-3.5 py-3 shadow-[var(--shadow-card)]"><span className="grid size-[42px] shrink-0 place-items-center rounded-xl bg-mint-soft text-mint-text"><Check className="size-5" /></span><span className="num text-[15px] font-bold">{text}</span></div>)}
      {error && <p role="alert" className="rounded-2xl bg-danger-soft px-3.5 py-3 text-sm text-danger">{error}</p>}
    </main>
    <div className="sticky bottom-0 bg-background"><div className="flex gap-2 overflow-x-auto px-[18px] pb-3 [scrollbar-width:none]">{QUICK_PROMPTS.map((q) => <button key={q} type="button" disabled={sending || !historyReady} onClick={() => void send(q)} className="min-h-10 shrink-0 rounded-full bg-card px-3.5 text-sm font-semibold shadow-[var(--shadow-card)]">{q}</button>)}</div>
      <form className="flex items-center gap-2 border-t border-line bg-card px-3 py-2.5" onSubmit={(event) => { event.preventDefault(); void send(draft); }}><input ref={fileInput} type="file" accept="image/jpeg,image/png" className="sr-only" tabIndex={-1} aria-hidden onChange={(event) => pickFile(event.target.files?.[0])} /><button type="button" onClick={() => fileInput.current?.click()} aria-label="Attach a slip or receipt" className="grid size-11 shrink-0 place-items-center rounded-full bg-background"><Paperclip className="size-5" /></button><label htmlFor="message" className="sr-only">Message</label><input id="message" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask about your money" className="h-11 min-w-0 flex-1 rounded-full bg-background px-4 text-base outline-none focus-visible:ring-2 focus-visible:ring-ink" /><button type="submit" disabled={sending || !historyReady || !draft.trim()} aria-label="Send" className="grid size-11 shrink-0 place-items-center rounded-full bg-mint text-ink disabled:opacity-50"><SendHorizontal className="size-5" /></button></form><TabBar /></div>
    {upload && !review && <div className="fixed inset-0 z-40 flex justify-center"><button type="button" tabIndex={-1} aria-label="Close upload" onClick={closeUpload} className="absolute inset-0 bg-ink/40" /><div role="dialog" aria-modal="true" aria-label="Upload photo" className="relative mt-auto w-full max-w-[430px] rounded-t-[28px] bg-background p-[18px]"><div className="flex items-center"><h2 className="text-lg font-extrabold">Check your photo</h2><button type="button" disabled={uploadBusy} onClick={closeUpload} className="ml-auto grid size-11 place-items-center"><span className="sr-only">Close</span>×</button></div>{/* eslint-disable-next-line @next/next/no-img-element */}<img src={upload.imageUrl} alt="Selected slip or receipt" className="mt-3 h-44 w-full rounded-2xl bg-card object-contain" /><p className="mt-3 text-sm">This photo has no verified capture timestamp. Confirm sending it for processing under your photo consent.</p><label className="mt-3 flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={upload.confirmed} disabled={uploadBusy || !!upload.uploadId} onChange={(event) => setUpload((old) => old ? { ...old, confirmed: event.target.checked } : old)} />I confirm sending this undated photo</label>{upload.status && <p role="status" className="mt-2 text-sm">Status: {upload.status.replaceAll("_", " ")}</p>}{error && <p role="alert" className="mt-2 rounded-2xl bg-danger-soft p-3 text-sm text-danger">{error}</p>}{upload.status === "extract_failed" ? <button type="button" disabled={uploadBusy} onClick={() => void retryUpload()} className="mt-3 min-h-[52px] w-full rounded-[var(--radius-ctl)] bg-ink font-bold text-white">Retry processing</button> : !upload.uploadId && <button type="button" disabled={!upload.confirmed || !ownerId || uploadBusy} onClick={() => void submitUpload()} className="mt-3 flex min-h-[52px] w-full items-center justify-center gap-2 rounded-[var(--radius-ctl)] bg-ink font-bold text-white disabled:opacity-40">{uploadBusy && <Loader2 className="size-4 animate-spin" />}Upload photo</button>}{upload.uploadId && !uploadBusy && <button type="button" onClick={closeUpload} className="mt-2 min-h-11 w-full rounded-[var(--radius-ctl)] bg-card font-bold">Done</button>}</div></div>}
    {review && upload && <ConnectedReviewSheet item={review} imageUrl={upload.imageUrl} onClose={closeUpload} onResolved={resolved} />}
  </div>;
}
