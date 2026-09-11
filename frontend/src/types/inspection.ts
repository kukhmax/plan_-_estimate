import { QualityLevelValue, SubstrateValue } from './checklist';

export type InspectionStatusValue = 'DRAFT' | 'COMPLETED';

export interface InspectionCreatePayload {
  template_id: string;
  substrate: SubstrateValue;
  quality_target?: QualityLevelValue | null;
  surface_id?: string | null;
  plane?: 'FLOOR' | 'CEILING' | null;
  notes?: string | null;
}

export interface InspectionUpdatePayload {
  substrate?: SubstrateValue;
  quality_target?: QualityLevelValue | null;
  notes?: string | null;
}

export interface InspectionAnswerPayload {
  question_id: string;
  value_bool?: boolean | null;
  value_number?: string | null;
  value_text?: string | null;
  option_key?: string | null;
  option_keys?: string[] | null;
}

export interface InspectionAnswersPutPayload {
  answers: InspectionAnswerPayload[];
}

export interface InspectionAnswer {
  id: string;
  question_id: string;
  value_bool: boolean | null;
  value_number: string | number | null;
  value_text: string | null;
  option_key: string | null;
  option_keys: string[] | null;
  updated_at: string;
}

export interface InspectionFinding {
  id: string;
  finding_key: string;
  label_key: string | null;
  value_snapshot: Record<string, unknown> | null;
  is_active: boolean;
  resolved_at: string | null;
  position: number | null;
  answer_id: string | null;
  question_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Inspection {
  id: string;
  room_id: string;
  surface_id: string | null;
  plane: 'FLOOR' | 'CEILING' | null;
  template_id: string;
  substrate: SubstrateValue;
  quality_target: QualityLevelValue | null;
  status: InspectionStatusValue;
  notes: string | null;
  completed_at: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface InspectionDetail extends Inspection {
  answers: InspectionAnswer[];
}

export interface InspectionListResponse {
  items: Inspection[];
  total: number;
}

export interface InspectionAnswerListResponse {
  items: InspectionAnswer[];
  total: number;
}

export interface InspectionFindingListResponse {
  items: InspectionFinding[];
  total: number;
}

/** Inspection carrier: a WALL surface, a FLOOR/CEILING plane, or the room. */
export type InspectionTarget =
  | { kind: 'surface'; surfaceId: string; surfaceName?: string }
  | { kind: 'plane'; plane: 'FLOOR' | 'CEILING' }
  | { kind: 'room' };
