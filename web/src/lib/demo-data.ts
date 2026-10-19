// Fictional demo data, following the brief's own example: a ฿6,000 flexible budget and
// "Make Shopping 30%". Replace with backend results once the calculation engine exists.

import type { BudgetChangeProposal, NotPossibleDetail } from "@/components/action-card/types";
import type { UpcomingBill } from "@/components/activity/types";
import type { GoalPlan } from "@/components/goal/types";
import type { Insight } from "@/components/insight-card";
import type { Pocket } from "@/components/pocket-card";
import type { ExtractedDocument } from "@/components/review-sheet/types";

export const demoUser = { firstName: "Mook", initials: "MK", nextIncome: "Nov 1" };

export const demoMoney = {
  balance: 12640,
  safeToSpend: 2832,
  dailyAmount: 177,
  spentToday: 76,
};

// October pockets before the Shopping change is approved.
export const demoPockets: Pocket[] = [
  { id: "food", name: "Food", kind: "food", budget: 2400, spent: 1430 },
  { id: "shopping", name: "Shopping", kind: "shopping", budget: 1200, spent: 1400 },
  { id: "transport", name: "Transport", kind: "transport", budget: 900, spent: 590 },
  { id: "leisure", name: "Leisure", kind: "leisure", budget: 1500, spent: 480 },
  { id: "bills", name: "Bills", kind: "bills", budget: 3200, spent: 1850, protected: true, note: "2 upcoming bills" },
  { id: "savings", name: "Savings", kind: "savings", budget: 2125, spent: 0, protected: true, saved: 3500, note: "For: Trip to Chiang Mai" },
];

export const demoUnallocated = 0;

export const demoShoppingTo30: BudgetChangeProposal = {
  id: "demo-proposal-shopping-30",
  kind: "budget-change",
  flexibleBudget: 6000,
  changes: [
    { pocketId: "shopping", name: "Shopping", kind: "shopping", before: 1200, after: 1800 },
    { pocketId: "food", name: "Food", kind: "food", before: 2400, after: 2200 },
    { pocketId: "transport", name: "Transport", kind: "transport", before: 900, after: 700 },
    { pocketId: "leisure", name: "Leisure", kind: "leisure", before: 1500, after: 1300 },
  ],
  lockedPockets: "Bills and Savings",
  assumptions: ["Oct 16 – Nov 1", "Based on Aug–Oct spending (3 complete months)"],
  appliedSummary: "Shopping is now ฿1,800",
};

export const demoShoppingTo60: NotPossibleDetail = {
  request: "Shopping 20% → 60%",
  requested: 2400,
  canFree: 1650,
  reason: "Food, Transport and Leisure can only drop to their minimums.",
  alternatives: [
    { id: "max-fit", label: "Shopping 47.5%", detail: "The most that fits · +฿1,650" },
    { id: "from-savings", label: "Move ฿750 from Savings", detail: "Delays your trip goal by 2 weeks" },
  ],
};

// What the reader "finds" in any uploaded photo until image reading is built: an electricity
// bill whose payment status is unclear, so the sheet asks.
export const demoExtractedBill: ExtractedDocument = {
  docType: "bill",
  merchant: "MEA Electricity",
  date: "Oct 12",
  dueDate: "Oct 25",
  amount: 642,
  pocket: "bills",
  paid: null,
  reference: "INV 2026-10-4471",
  unsure: ["paid"],
};

// The brief's example insight. Today is Oct 16, so Oct 16–31 leaves 2 full weeks: 2 × ฿150 = ฿300.
export const demoDeliveryInsight: Insight = {
  id: "demo-insight-delivery",
  subject: "Delivery",
  period: { current: "Oct 1–14", previous: "Sep 1–14" },
  amounts: { current: 900, previous: 600 },
  action: "Spend ฿150 less a week on delivery",
  saving: { amount: 300, by: "Oct 31", toward: "your trip" },
  tradeoff: "about 1 fewer delivery order a week.",
  actionLabel: "Plan this",
};

// Trip goal: ฿8,500 to go over the 2 paydays before Dec 15 = ฿4,250 each. Nov 1 has only
// ฿3,400 free, so the plan needs a change.
export const demoTripPlan: GoalPlan = {
  goal: {
    id: "trip",
    name: "Trip to Chiang Mai",
    target: 12000,
    saved: 3500,
    deadline: "Dec 15",
    daysLeft: 60,
    lastChange: "+฿500 on Oct 1",
    protected: true,
  },
  status: "with-changes",
  schedule: [
    { date: "Nov 1", planned: 4250, free: 3400 },
    { date: "Dec 1", planned: 4250, free: 4600 },
  ],
  options: [
    { id: "cut-leisure", kind: "pocket", title: "Take ฿850 from Leisure in November", detail: "Leisure goes from ฿1,500 to ฿650 next month. Everything else stays." },
    { id: "later", kind: "deadline", title: "Move the deadline to Jan 15", detail: "3 paydays instead of 2, all within what's free.", newDeadline: "Jan 15", newPerPayday: 2834 },
    { id: "lower", kind: "target", title: "Lower the target to ฿11,150", detail: "฿3,400 on Nov 1 and ฿4,250 on Dec 1, with no other changes.", newTarget: 11150 },
    { id: "income", kind: "income", title: "Add income you're sure of", detail: "Only confirmed income counts. Nothing is assumed." },
  ],
};

export const demoBills: UpcomingBill[] = [
  { id: "mea", provider: "MEA Electricity", amount: 642, due: "Oct 25", daysUntilDue: 9, status: "unpaid", changeVsLast: 118 },
  { id: "phone", provider: "AIS Phone", amount: 399, due: "Oct 28", daysUntilDue: 12, status: "unpaid" },
  { id: "rent", provider: "Dorm rent", amount: 3500, due: "Oct 5", daysUntilDue: 0, status: "paid" },
];

export const demoTransactions = [
  { id: "t1", day: "Today", merchant: "7-Eleven", pocket: "food", pocketName: "Food", amount: -89, source: "receipt" },
  { id: "t2", day: "Today", merchant: "BTS Skytrain", pocket: "transport", pocketName: "Transport", amount: -47, source: "manual" },
  { id: "t3", day: "Oct 15", merchant: "PromptPay to Ploy S.", pocket: null, pocketName: null, amount: -350, source: "slip", needsReview: true, askPurpose: true },
  { id: "t4", day: "Oct 15", merchant: "Uniqlo", pocket: "shopping", pocketName: "Shopping", amount: -590, source: "receipt" },
  { id: "t5", day: "Oct 14", merchant: "Grab Food", pocket: "food", pocketName: "Food", amount: -245, source: "receipt", needsReview: true, possibleDuplicateOf: { merchant: "Grab Food", date: "Oct 14", amount: 245, source: "Payment slip you saved on Oct 14" } },
  { id: "t6", day: "Oct 14", merchant: "Grab Food", pocket: "food", pocketName: "Food", amount: -245, source: "slip" },
  { id: "t7", day: "Oct 14", merchant: "Major Cineplex", pocket: "leisure", pocketName: "Leisure", amount: -220, source: "manual" },
  { id: "t8", day: "Oct 13", merchant: "Shopee refund", pocket: "shopping", pocketName: "Shopping", amount: 160, source: "csv" },
];

export const demoRecentChanges = [
  { id: "c1", title: "Moved ฿500 to Food", detail: "From Shopping · Balance unchanged", when: "Today, 9:12", canUndo: true },
  { id: "c2", title: "Grab Food set to Food", detail: "Was Shopping", when: "Yesterday", canUndo: true },
  {
    id: "c3",
    title: "October budget approved",
    detail: "7 pockets · ฿6,000 flexible",
    when: "Oct 1",
    canUndo: false,
    whyNoUndo: "Can't undo: later changes build on it. Ask Pal for a new plan instead.",
  },
].map((c) => ({ ...c, undone: false }));

export const demoProfile = [
  { label: "Income", value: "฿14,000 monthly · next Nov 1 · confirmed" },
  { label: "Balance snapshot", value: "฿12,640 as of Oct 1" },
  { label: "Bills", value: "Dorm rent, MEA Electricity, AIS Phone" },
  { label: "Safety buffer", value: "฿500" },
];
