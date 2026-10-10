/** The protocol of information and decisions of the customer (Stage 16I; mirrors backend `schemas/decision.py`). */
import type { HandoverAttendee } from './handover';

export type DecisionStatus = 'DRAFT' | 'ISSUED' | 'ARCHIVED';
export type DecisionChoice = 'ACCEPTED' | 'DECLINED' | 'INSISTS';
export type ExecutorAction = 'PERFORM' | 'REFUSE';
export type RiskSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface DecisionBlocker {
  code:
    | 'EXECUTOR_PROFILE_REQUIRED'
    | 'CLIENT_REQUIRED'
    | 'CONTRACT_REQUIRED'
    | 'HELD_ON_REQUIRED'
    | 'NO_ATTENDEES'
    | 'NO_ITEMS'
    | 'ITEM_RISK_GONE'
    | 'ITEM_DECISION_REQUIRED'
    | 'ITEM_ACTION_REQUIRED'
    | 'DECLARATION_REQUIRED'
    | 'REFUSAL_NOTE_REQUIRED';
  details: { item_ids?: string[] } | null;
}

export interface DecisionItem {
  id: string;
  source: 'RISK' | 'OWN';
  risk_id: string | null;
  room_id: string | null;
  room_name: string | null;
  severity: RiskSeverity | null;
  blocks_finishing: boolean;
  title: string;
  /** What was found (the risk's explanation); none for the contractor's own item. */
  state: string | null;
  recommendation: string;
  consequence: string;
  price: string | null;
  decision: DecisionChoice | null;
  executor_action: ExecutorAction | null;
  order_ref: string | null;
  note: string | null;
  /** False when the risk of the item is no longer found. */
  risk_active: boolean;
}

export interface DecisionRiskOption {
  id: string;
  room_id: string;
  room_name: string;
  severity: RiskSeverity;
  blocks_finishing: boolean;
  title: string;
  consequence: string;
  /** Already an item of this protocol. */
  used: boolean;
}

export interface Decision {
  id: string;
  project_id: string;
  sequence: number;
  status: DecisionStatus;
  held_on: string | null;
  held_time: string | null;
  attendees: HandoverAttendee[];
  understood: boolean;
  signature_refused: boolean;
  notes: string | null;
  items: DecisionItem[];
  risk_options: DecisionRiskOption[];
  rooms: Array<{ id: string; name: string }>;
  blockers: DecisionBlocker[];
  contract: { id: string; version: number; status: string } | null;
  created_at: string;
  updated_at: string;
}

export interface DecisionListResponse {
  items: Decision[];
  total: number;
}

export interface ItemChange {
  risk_id?: string;
  room_id?: string | null;
  title?: string;
  recommendation?: string;
  consequence?: string;
  price?: string | null;
  decision?: DecisionChoice | null;
  executor_action?: ExecutorAction | null;
  order_ref?: string | null;
  note?: string | null;
}

/** Only the fields that are sent change; null clears. `items[id] = null` removes an item. */
export interface DecisionChange {
  held_on?: string | null;
  held_time?: string | null;
  attendees?: Array<{ person_id: string } | { name: string; role?: string | null }>;
  items?: Record<string, ItemChange | null>;
  understood?: boolean;
  signature_refused?: boolean;
  notes?: string | null;
}
