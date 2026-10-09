export type AdjacentWorkOrder = 'BEFORE_OURS' | 'PARALLEL' | 'AFTER_OURS';

export const ADJACENT_WORK_ORDERS: AdjacentWorkOrder[] = ['BEFORE_OURS', 'PARALLEL', 'AFTER_OURS'];

/** A work of another contractor on the object (Stage 16D.1); `room_ids` null = the whole object. */
export interface AdjacentWork {
  id: string;
  project_id: string;
  work_name: string;
  performer: string | null;
  room_ids: string[] | null;
  period_from: string | null;
  period_to: string | null;
  order_relation: AdjacentWorkOrder;
  order_note: string | null;
  responsibility_note: string | null;
  coordination_note: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdjacentWorkListResponse {
  items: AdjacentWork[];
  total: number;
}

export interface AdjacentWorkCreatePayload {
  work_name: string;
  performer?: string;
  room_ids?: string[];
  period_from?: string;
  period_to?: string;
  order_relation: AdjacentWorkOrder;
  order_note?: string;
  responsibility_note?: string;
  coordination_note?: string;
}

/** Only what changes is sent; null clears an optional field (and `room_ids: null` means the whole object). */
export interface AdjacentWorkUpdatePayload {
  work_name?: string;
  performer?: string | null;
  room_ids?: string[] | null;
  period_from?: string | null;
  period_to?: string | null;
  order_relation?: AdjacentWorkOrder;
  order_note?: string | null;
  responsibility_note?: string | null;
  coordination_note?: string | null;
}
