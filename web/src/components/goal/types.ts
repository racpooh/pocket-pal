// Goal vocabulary follows CONTEXT.md (Saved, Planned, goal statuses).

export type GoalStatus = "on-track" | "with-changes" | "not-possible";

export type Goal = {
  id: string;
  name: string;
  target: number;
  /** Money actually set aside (Saved). */
  saved: number;
  deadline: string;
  daysLeft: number;
  /** Most recent change to Saved, e.g. "+฿500 on Oct 1". */
  lastChange?: string;
  protected: boolean;
};

/** One Planned contribution on a confirmed income date. */
export type PlannedContribution = {
  date: string;
  planned: number;
  /** Free on that date after essentials, bills and the buffer. */
  free: number;
};

/** A quantified alternative to the current plan. */
export type GoalOption = {
  id: string;
  kind: "deadline" | "target" | "pocket" | "income";
  title: string;
  detail: string;
  newDeadline?: string;
  newTarget?: number;
  newPerPayday?: number;
};

export type GoalPlan = {
  goal: Goal;
  status: GoalStatus;
  schedule: PlannedContribution[];
  options: GoalOption[];
};
