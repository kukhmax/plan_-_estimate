/** The payment schedule, the work hours and the margin of an object (V2-9); mirrors backend `schemas/payment_schedule.py`. Money arrives as strings with two places. */
export type StageState = 'PAID' | 'PARTIAL' | 'OVERDUE' | 'OPEN';

export interface PaymentStage {
  id: string;
  project_id: string;
  title: string;
  /** A share of the agreed amount, or null for a fixed amount. */
  percent: string | null;
  /** The fixed amount the owner typed, or null for a share. */
  amount_fixed: string | null;
  due_on: string | null;
  /** What the stage is worth (the server's): null while a share has no agreed amount to follow. */
  amount: string | null;
  received: string;
  remaining: string | null;
  state: StageState;
  created_at: string;
  updated_at: string;
}

export interface ScheduleSummary {
  agreed: string | null;
  stages_total: string;
  unpriced: number;
  /** Agreed less the stages: positive = not scheduled yet, negative = scheduled above the agreed amount. */
  difference: string | null;
  received: string;
  to_receive: string | null;
}

export interface Schedule {
  items: PaymentStage[];
  summary: ScheduleSummary;
}

/** What the form sends: a title, a share or an amount (never both), an optional day. */
export interface StageFields {
  title: string;
  percent?: string | null;
  amount?: string | null;
  due_on?: string | null;
}

export interface WorkHour {
  id: string;
  project_id: string;
  worked_on: string;
  hours: string;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkHours {
  items: WorkHour[];
  total_hours: string;
  hourly_rate: string | null;
}

export interface HourFields {
  worked_on: string;
  hours: string;
  note: string | null;
}

export interface Margin {
  basis: string | null;
  basis_source: 'AGREED' | 'ESTIMATE' | null;
  expenses: string;
  hours: string;
  hourly_rate: string | null;
  labor_cost: string | null;
  /** Whether `margin` is after the owner's own work (a rate is set) or before it. */
  labor_included: boolean;
  margin: string | null;
  percent: string | null;
  per_hour: string | null;
}

export const MAX_STAGE_TITLE_LENGTH = 255;
export const MAX_HOUR_NOTE_LENGTH = 1000;
