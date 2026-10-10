/** The notice and the protocol of downtime on the customer's side (Stage 16I; mirrors backend `schemas/downtime.py`). */
import type { HandoverAttendee } from './handover';

export type DowntimeStatus = 'DRAFT' | 'NOTICED' | 'CLOSED' | 'ARCHIVED';

export interface DowntimeBlocker {
  code:
    | 'EXECUTOR_PROFILE_REQUIRED'
    | 'CLIENT_REQUIRED'
    | 'CONTRACT_REQUIRED'
    | 'CAUSE_REQUIRED'
    | 'CAUSE_NOTE_REQUIRED'
    | 'NOTICED_ON_REQUIRED'
    | 'NEED_REQUIRED'
    | 'PHOTOS_REQUIRED'
    | 'DAYS_REQUIRED'
    | 'HELD_ON_REQUIRED'
    | 'DAY_AFTER_PROTOCOL'
    | 'NO_ATTENDEES'
    | 'REFUSAL_NOTE_REQUIRED';
  details: { days?: string[] } | null;
}

export interface DowntimePhoto {
  id: string;
  caption: string | null;
  captured_at: string | null;
  room_name: string | null;
}

export interface DowntimeDay {
  date: string;
  /** 0 = Monday. */
  weekday: number;
  other_work: boolean;
  note: string | null;
}

export interface DowntimeSettlement {
  listed: number;
  chargeable: number;
  rate: string | null;
  amount: string | null;
  cap: string | null;
  capped: boolean;
  payable: string | null;
  limit_days: number | null;
  limit_exceeded: boolean;
}

export interface Downtime {
  id: string;
  project_id: string;
  sequence: number;
  status: DowntimeStatus;
  cause_key: string | null;
  cause_text: string | null;
  cause_note: string | null;
  room_ids: string[];
  noticed_on: string | null;
  noticed_time: string | null;
  notice_channel: string | null;
  photo_ids: string[];
  need_text: string | null;
  need_by: string | null;
  days: DowntimeDay[];
  held_on: string | null;
  held_time: string | null;
  attendees: HandoverAttendee[];
  signature_refused: boolean;
  deadline_note: string | null;
  notes: string | null;
  notice_number: string | null;
  notice_issued_at: string | null;
  protocol_issued_at: string | null;
  /** The chosen photos. */
  photos: DowntimePhoto[];
  /** What may be chosen (while a draft). */
  photo_options: DowntimePhoto[];
  rooms: Array<{ id: string; name: string }>;
  settlement: DowntimeSettlement;
  /** Of the document that is next to be issued. */
  blockers: DowntimeBlocker[];
  contract: { id: string; version: number; status: string } | null;
  created_at: string;
  updated_at: string;
}

export interface DowntimeListResponse {
  items: Downtime[];
  total: number;
}

/** Only the fields that are sent change; null clears. `days[date] = null` removes a day. */
export interface DowntimeChange {
  cause_key?: string | null;
  cause_note?: string | null;
  room_ids?: string[];
  noticed_on?: string | null;
  noticed_time?: string | null;
  notice_channel?: string | null;
  photo_ids?: string[];
  need_text?: string | null;
  need_by?: string | null;
  days?: Record<string, { other_work?: boolean; note?: string | null } | null>;
  held_on?: string | null;
  held_time?: string | null;
  attendees?: Array<{ person_id: string } | { name: string; role?: string | null }>;
  signature_refused?: boolean;
  deadline_note?: string | null;
  notes?: string | null;
}
