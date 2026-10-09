/** The protocol of handing over the premises (Stage 16F; mirrors backend `schemas/handover.py`). */
export type HandoverStatus = 'DRAFT' | 'ISSUED' | 'ARCHIVED';
export type RequirementState = 'YES' | 'NO' | 'CONDITIONAL' | 'NOT_APPLICABLE';
export type HandoverDecision = 'HANDED_OVER' | 'CONDITIONAL' | 'NOT_HANDED_OVER';

/** A measured value: a number, or a range for a requirement kept between two limits. */
export type MeasuredValue = number | { min: number; max: number };

export interface RequirementEntry {
  state?: RequirementState;
  value?: MeasuredValue;
  note?: string;
}

export interface HandoverRoomEntry {
  requirements?: Record<string, RequirementEntry>;
  damages?: string;
  decision?: HandoverDecision;
}

export interface HandoverAttendee {
  person_id: string | null;
  name: string;
  role: string | null;
}

export interface HandoverBlocker {
  code:
    | 'CONTRACT_REQUIRED'
    | 'EXECUTOR_PROFILE_REQUIRED'
    | 'CLIENT_REQUIRED'
    | 'HELD_ON_REQUIRED'
    | 'NO_ATTENDEES'
    | 'NO_ROOMS'
    | 'REQUIREMENTS_MISSING'
    | 'DECISION_MISSING'
    | 'DECISION_TOO_FAVOURABLE';
  details: { rooms?: Array<{ room_id: string; keys: string[] }>; room_ids?: string[] } | null;
}

export interface Handover {
  id: string;
  project_id: string;
  sequence: number;
  status: HandoverStatus;
  held_on: string | null;
  held_time: string | null;
  attendees: HandoverAttendee[];
  rooms: Record<string, HandoverRoomEntry>;
  meters: string | null;
  notes: string | null;
  /** Per room of the protocol: the best decision the findings allow, null while a requirement is unanswered. */
  suggested: Record<string, HandoverDecision | null>;
  blockers: HandoverBlocker[];
  contract: { id: string; version: number; status: string } | null;
  /** The numbers the contract asks for (annex 4), by requirement key. */
  required_values: Record<string, MeasuredValue | boolean>;
  created_at: string;
  updated_at: string;
}

export interface HandoverListResponse {
  items: Handover[];
  total: number;
}

/** What the screen may change: only the fields that are sent change; null clears. */
export interface HandoverChange {
  held_on?: string | null;
  held_time?: string | null;
  attendees?: Array<{ person_id: string } | { name: string; role?: string | null }>;
  meters?: string | null;
  notes?: string | null;
  rooms?: Record<
    string,
    | {
        requirements?: Record<string, { state?: RequirementState; value?: MeasuredValue | null; note?: string | null } | null>;
        damages?: string | null;
        decision?: HandoverDecision | null;
      }
    | null
  >;
}
