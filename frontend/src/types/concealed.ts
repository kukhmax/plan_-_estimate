/** The protocol of acceptance of concealed works (Stage 16G; mirrors backend `schemas/concealed.py`). */
import type { HandoverAttendee } from './handover';

export type ConcealedStatus = 'DRAFT' | 'ISSUED' | 'ARCHIVED';
export type ConcealedResult = 'ACCEPTED' | 'WITH_REMARKS';
export type CoverConsent = 'GIVEN' | 'WITHHELD';

export interface ConcealedBlocker {
  code:
    | 'CONTRACT_REQUIRED'
    | 'EXECUTOR_PROFILE_REQUIRED'
    | 'CLIENT_REQUIRED'
    | 'SURFACE_REQUIRED'
    | 'WORK_KIND_REQUIRED'
    | 'WORK_NOTE_REQUIRED'
    | 'HELD_ON_REQUIRED'
    | 'NOTIFIED_ON_REQUIRED'
    | 'NO_ATTENDEES'
    | 'PHOTOS_REQUIRED'
    | 'RESULT_REQUIRED'
    | 'REMARKS_REQUIRED'
    | 'COVER_CONSENT_REQUIRED';
  details: Record<string, unknown> | null;
}

export interface ConcealedPhoto {
  id: string;
  caption: string | null;
  captured_at: string | null;
}

export interface Concealed {
  id: string;
  project_id: string;
  sequence: number;
  status: ConcealedStatus;
  held_on: string | null;
  held_time: string | null;
  customer_absent: boolean;
  notified_on: string | null;
  attendees: HandoverAttendee[];
  surface: { id: string; name: string; room_id: string; room_name: string } | null;
  work_kind: string | null;
  work_note: string | null;
  material: string | null;
  batch: string | null;
  photo_ids: string[];
  result: ConcealedResult | null;
  remarks: string | null;
  cover_consent: CoverConsent | null;
  /** The evidence photos that exist for the chosen surface. */
  photo_options: ConcealedPhoto[];
  blockers: ConcealedBlocker[];
  contract: { id: string; version: number; status: string } | null;
  created_at: string;
  updated_at: string;
}

export interface ConcealedListResponse {
  items: Concealed[];
  total: number;
}

/** Only the fields that are sent change; null clears. */
export interface ConcealedChange {
  held_on?: string | null;
  held_time?: string | null;
  customer_absent?: boolean;
  notified_on?: string | null;
  attendees?: Array<{ person_id: string } | { name: string; role?: string | null }>;
  surface_id?: string | null;
  work_kind?: string | null;
  work_note?: string | null;
  material?: string | null;
  batch?: string | null;
  photo_ids?: string[];
  result?: ConcealedResult | null;
  remarks?: string | null;
  cover_consent?: CoverConsent | null;
}
