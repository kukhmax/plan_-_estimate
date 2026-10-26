/** The protocol of a pressure test (V2-12b; mirrors backend `schemas/pressure.py`). The pressures arrive as strings with two places. */
import type { HandoverAttendee } from './handover';

export type PressureStatus = 'DRAFT' | 'ISSUED' | 'ARCHIVED';
export type PressureSystem = 'COLD_WATER' | 'HOT_WATER' | 'HEATING' | 'GAS' | 'SEWER';
export type PressureMedium = 'WATER' | 'AIR';
export type PressureResult = 'POSITIVE' | 'NEGATIVE';

export const PRESSURE_SYSTEMS: PressureSystem[] = ['COLD_WATER', 'HOT_WATER', 'HEATING', 'GAS', 'SEWER'];
export const PRESSURE_MEDIA: PressureMedium[] = ['WATER', 'AIR'];
export const PRESSURE_RESULTS: PressureResult[] = ['POSITIVE', 'NEGATIVE'];
/** At most this many photos of the manometer (the server enforces the same limit). */
export const MAX_PRESSURE_PHOTOS = 4;

export interface PressureBlocker {
  code:
    | 'EXECUTOR_PROFILE_REQUIRED'
    | 'CLIENT_REQUIRED'
    | 'SYSTEM_REQUIRED'
    | 'MEDIUM_REQUIRED'
    | 'PRESSURE_REQUIRED'
    | 'DURATION_REQUIRED'
    | 'DROP_REQUIRED'
    | 'HELD_ON_REQUIRED'
    | 'NOTIFIED_ON_REQUIRED'
    | 'NO_ATTENDEES'
    | 'PHOTOS_REQUIRED'
    | 'RESULT_REQUIRED'
    | 'REMARKS_REQUIRED';
  details: Record<string, unknown> | null;
}

export interface PressurePhoto {
  id: string;
  caption: string | null;
  /** The room (and the surface) the photo is attached to; null: the object itself. */
  place: string | null;
  captured_at: string | null;
  created_at: string;
}

export interface Pressure {
  id: string;
  project_id: string;
  sequence: number;
  status: PressureStatus;
  held_on: string | null;
  held_time: string | null;
  customer_absent: boolean;
  notified_on: string | null;
  attendees: HandoverAttendee[];
  system: PressureSystem | null;
  section: string | null;
  medium: PressureMedium | null;
  test_pressure_bar: string | null;
  duration_min: number | null;
  pressure_drop_bar: string | null;
  photo_ids: string[];
  result: PressureResult | null;
  remarks: string | null;
  /** The photos of the object that may be the picture of the manometer. */
  photo_options: PressurePhoto[];
  blockers: PressureBlocker[];
  created_at: string;
  updated_at: string;
}

export interface PressureListResponse {
  items: Pressure[];
  total: number;
}

/** Only the fields that are sent change; null clears. */
export interface PressureChange {
  held_on?: string | null;
  held_time?: string | null;
  customer_absent?: boolean;
  notified_on?: string | null;
  attendees?: Array<{ person_id: string } | { name: string; role?: string | null }>;
  system?: PressureSystem | null;
  section?: string | null;
  medium?: PressureMedium | null;
  test_pressure_bar?: string | null;
  duration_min?: number | null;
  pressure_drop_bar?: string | null;
  photo_ids?: string[];
  result?: PressureResult | null;
  remarks?: string | null;
}
