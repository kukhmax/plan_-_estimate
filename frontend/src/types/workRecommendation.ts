/** Stage 11 recommended-work lifecycle (Stage 11B.1/11B.2 backend contract).
 *
 * `status` (PENDING/ACCEPTED/DISMISSED) is an owner lifecycle decision and
 * `is_active` (the underlying Risk/Finding source still being confirmed) is
 * an independent dimension — a recommendation can be ACCEPTED and later
 * become inactive, or DISMISSED while its source is still active. Never
 * collapse the two into one label.
 */
import { SurfacePriceItemSummaryRead } from './workPlan';

export type WorkRecommendationTriggerTypeValue = 'RISK_RULE' | 'FINDING';

export type WorkRecommendationTargetKindValue = 'WALL' | 'FLOOR' | 'CEILING' | 'ROOM';

export type WorkRecommendationStatusValue = 'PENDING' | 'ACCEPTED' | 'DISMISSED';

export type WorkRecommendationActivityValue = 'active' | 'resolved' | 'all';

export interface WorkRecommendationRead {
  id: string;
  trigger_type: WorkRecommendationTriggerTypeValue;
  trigger_code: string;
  source_signature: string;
  inspection_id: string;
  room_id: string;
  surface_id: string | null;
  target_kind: WorkRecommendationTargetKindValue;
  recommended_work_code: string;
  status: WorkRecommendationStatusValue;
  is_active: boolean;
  resolved_at: string | null;
  accepted_at: string | null;
  dismissed_at: string | null;
  resolved_price_item_id: string | null;
  created_at: string;
  updated_at: string;
  current_price_item: SurfacePriceItemSummaryRead | null;
}

export interface WorkRecommendationListResponse {
  items: WorkRecommendationRead[];
  total: number;
}

export interface WorkRecommendationEvaluateResponse {
  created: number;
  reactivated: number;
  unchanged: number;
  resolved: number;
  items: WorkRecommendationRead[];
  total: number;
}
