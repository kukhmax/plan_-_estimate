/** The protocol of acceptance of the work, final or partial (Stage 16H; mirrors backend `schemas/acceptance.py`). */
import type { HandoverAttendee } from './handover';

export type AcceptanceStatus = 'DRAFT' | 'ISSUED' | 'ARCHIVED';
export type AcceptanceResult = 'ACCEPTED' | 'ACCEPTED_WITH_REMARKS' | 'NOT_ACCEPTED';
export type RemarkClass = 'REMOVABLE' | 'SIGNIFICANT';
export type WorkState = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';

export type AcceptanceBlockerCode =
  | 'EXECUTOR_PROFILE_REQUIRED'
  | 'CLIENT_REQUIRED'
  | 'CONTRACT_REQUIRED'
  | 'SCOPE_REQUIRED'
  | 'HELD_ON_REQUIRED'
  | 'NOTIFIED_ON_REQUIRED'
  | 'RENOTIFIED_ON_REQUIRED'
  | 'NOTIFICATION_ORDER'
  | 'NO_ATTENDEES'
  | 'CONDITIONS_NOTE_REQUIRED'
  | 'SURFACE_NOT_ASSESSED';

export interface AcceptanceBlocker {
  code: AcceptanceBlockerCode;
  details: Record<string, unknown> | null;
}

export interface AcceptanceRemark {
  id: string;
  place: string;
  description: string;
  classification: RemarkClass;
  deadline: string | null;
  photo_ids: string[];
}

export interface AcceptancePhoto {
  id: string;
  caption: string | null;
  captured_at: string | null;
}

export interface AcceptanceSurface {
  id: string;
  name: string;
  surface_type: string;
  room_id: string;
  room_name: string;
  quality_target: string | null;
  works: Array<{ name: string; status: WorkState }>;
  /** The planned works that are not completed. */
  incomplete: number;
  assessed: boolean;
  remarks: AcceptanceRemark[];
  /** Derived by the server from the works and the remarks; never typed. */
  result: AcceptanceResult;
  /** The photos of defects of this surface that a remark may point at. */
  photo_options: AcceptancePhoto[];
}

export interface AcceptanceRoom {
  id: string;
  name: string;
  /** Surfaces with planned works. */
  surfaces: number;
}

export interface AcceptanceCondition {
  key: string;
  lighting: string;
  requires_agreement: boolean;
  text_pl: string;
}

export interface Acceptance {
  id: string;
  project_id: string;
  sequence: number;
  status: AcceptanceStatus;
  held_on: string | null;
  held_time: string | null;
  customer_absent: boolean;
  notified_on: string | null;
  renotified_on: string | null;
  attendees: HandoverAttendee[];
  room_ids: string[];
  conditions_note: string | null;
  instrument_keys: string[];
  batches: string | null;
  instructions_given: boolean;
  amount_due: string | null;
  amount_retained: string | null;
  notes: string | null;
  scope_kind: 'FINAL' | 'PARTIAL' | null;
  result: AcceptanceResult | null;
  rooms: AcceptanceRoom[];
  surfaces: AcceptanceSurface[];
  conditions: AcceptanceCondition[];
  blockers: AcceptanceBlocker[];
  contract: { id: string; version: number; status: string } | null;
  created_at: string;
  updated_at: string;
}

export interface AcceptanceListResponse {
  items: Acceptance[];
  total: number;
}

export interface RemarkChange {
  place?: string;
  description?: string;
  classification?: RemarkClass;
  deadline?: string | null;
  photo_ids?: string[];
}

/** Only the fields that are sent change; null clears. `surfaces[id].remarks[rid] = null` removes a remark. */
export interface AcceptanceChange {
  held_on?: string | null;
  held_time?: string | null;
  customer_absent?: boolean;
  notified_on?: string | null;
  renotified_on?: string | null;
  attendees?: Array<{ person_id: string } | { name: string; role?: string | null }>;
  room_ids?: string[];
  conditions_note?: string | null;
  instrument_keys?: string[];
  surfaces?: Record<string, { assessed?: boolean; remarks?: Record<string, RemarkChange | null> } | null>;
  batches?: string | null;
  instructions_given?: boolean;
  amount_due?: string | null;
  amount_retained?: string | null;
  notes?: string | null;
}
