import { api } from "@/lib/api";

export type GoalRecord = {
  id: string; name: string; target_satang: number; saved_satang: number;
  deadline: string; contribution_satang_per_period: number; status: string;
};

export type Proposal = {
  proposal_id: string; status: string; kind: string; payload_hash: string; card_hash: string;
  card: { summary?: { text: string }; warnings?: { text: string }[]; uncertainty?: { text: string }[];
    effects?: { this_goal?: { required_per_event_satang: number; contribution_per_event_satang: number; contribution_covers_required: boolean } } };
};

export function parseSatang(value: string): number | null {
  const clean = value.replace(/,/g, "").trim();
  if (!/^(?:\d+)(?:\.\d{1,2})?$/.test(clean)) return null;
  const [whole, fractional = ""] = clean.split(".");
  const amount = Number(whole) * 100 + Number(fractional.padEnd(2, "0"));
  return Number.isSafeInteger(amount) ? amount : null;
}

export function formatSatang(amount: number): string {
  return `฿${(amount / 100).toLocaleString("en-US", { minimumFractionDigits: amount % 100 ? 2 : 0, maximumFractionDigits: 2 })}`;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed. Please try again.";
}

export async function createGoalProposal(payload: {
  name: string; target_satang: number; saved_satang: number; deadline: string;
  contribution_satang_per_period: number;
}): Promise<Proposal> {
  return api<Proposal>("/proposals", { method: "POST", body: JSON.stringify({ kind: "goal_create", payload }) });
}

export async function approveProposal(proposal: Proposal): Promise<void> {
  await api(`/proposals/${proposal.proposal_id}/approve`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ payload_hash: proposal.payload_hash, card_hash: proposal.card_hash }),
  });
}
