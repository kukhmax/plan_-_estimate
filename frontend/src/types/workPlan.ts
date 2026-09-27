import { QualityLevelValue, SubstrateValue } from './checklist';
import { PriceCategoryValue, PriceScopeValue, PriceUnitValue } from './priceItem';

export interface SurfacePriceItemSummaryRead {
  id: string;
  code: string;
  name_key: string | null;
  display_name: string | null;
  category: PriceCategoryValue;
  unit: PriceUnitValue;
  price_scope: PriceScopeValue;
  price: string | null;
  currency: string;
  is_archived: boolean;
  quality_level: QualityLevelValue | null;
}

export interface PlannedWorkCoefficientOptionRead {
  id: string;
  group_id: string;
  group_code: string;
  code: string;
  display_name: string | null;
  percentage: string;
  is_base: boolean;
}

export interface OrderedPriceItemSelection {
  price_item_id: string;
  coefficient_option_ids: string[];
  /** Echo of an EXISTING occurrence's server key; omitted for new work
   * (the server generates it). Never generated on the client. */
  occurrence_key?: string;
  /** Technological break after this occurrence (whole hours >= 1) or null. */
  wait_after_hours?: number | null;
}

/** Stage 13H: execution status of one CURRENT planned-work occurrence. */
export type WorkExecutionStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';

/** Read-only execution state embedded in every WorkPlan response (13H.3).
 * Timestamps are when the state was RECORDED in the app (server UTC ISO), not
 * proof of the physical moment; ready_after is derived from the break. */
export interface PlannedWorkExecutionRead {
  status: WorkExecutionStatus;
  started_at: string | null;
  completed_at: string | null;
  ready_after: string | null;
}

/** Response of PATCH …/occurrences/{occurrence_key}/execution. */
export interface SurfaceWorkExecutionRead extends PlannedWorkExecutionRead {
  occurrence_key: string;
}

export interface WorkExecutionTransition {
  status: WorkExecutionStatus;
  /** The status the owner saw when starting the action (optimistic concurrency). */
  expected_status: WorkExecutionStatus;
}

/** One entry of the 409 WORK_EXECUTION_DETACH_CONFIRMATION_REQUIRED list (13H.4). */
export interface ExecutionDetachAffected {
  surface_id: string;
  occurrence_key: string;
  position: number;
  status: WorkExecutionStatus;
  price_item_id: string;
  price_item_code: string;
  price_item_name_key: string | null;
  price_item_display_name: string | null;
}

export interface SurfacePlannedWorkRead {
  id: string;
  work_plan_id: string;
  price_item_id: string;
  position: number;
  /** Stable logical identity of this occurrence (Stage 13 D13). */
  occurrence_key: string;
  wait_after_hours: number | null;
  price_item: SurfacePriceItemSummaryRead | null;
  coefficient_options?: PlannedWorkCoefficientOptionRead[];
  /** Stage 13H.3: read-only; never sent back in a save. */
  execution?: PlannedWorkExecutionRead;
}

export interface TemplateApplicationRead {
  id: string;
  template_id: string | null;
  template_code: string;
  /** Snapshot: an owner display name, or a built-in template's name_key. */
  template_name: string;
  mode: 'APPEND' | 'REPLACE';
  steps_applied: number;
  applied_at: string;
}

export interface SurfaceWorkPlanRead {
  id: string;
  surface_id: string;
  substrate: SubstrateValue;
  quality_target: QualityLevelValue | null;
  planned_works: SurfacePlannedWorkRead[];
  /** Historical template-application provenance (Stage 13C), oldest first. */
  template_applications?: TemplateApplicationRead[];
}

export interface SurfaceWorkPlanUpsert {
  substrate: SubstrateValue;
  quality_target: QualityLevelValue | null;
  price_item_ids?: string[];
  planned_works?: OrderedPriceItemSelection[];
  /** Stage 13H.4: exact keys returned by a detach-confirmation 409. */
  confirm_execution_detach_keys?: string[];
}

export interface SurfaceWorkPlanApplyResult {
  source_surface_id: string;
  target_count: number;
  target_surface_ids: string[];
  targets: SurfaceWorkPlanRead[];
}

/** Stage 13H.5B: one entry of the exact ordered source snapshot. */
export interface ExecutionSnapshotItem {
  occurrence_key: string;
  status: WorkExecutionStatus;
}

/** Per target wall: one bucket per source work (changed + unchanged +
 * unmatched + ambiguous == source works). has_plan=false -> all unmatched. */
export interface BulkExecutionWallRead {
  surface_id: string;
  has_plan: boolean;
  changed: number;
  unchanged: number;
  unmatched: number;
  ambiguous: number;
  unmatched_price_item_ids: string[];
  ambiguous_price_item_ids: string[];
}

/** Preview (applied=false) and apply (applied=true) share this shape. */
export interface BulkExecutionResultRead {
  source_surface_id: string;
  applied: boolean;
  /** Server-canonical snapshot to send back verbatim on apply. */
  expected_source: ExecutionSnapshotItem[];
  changed: number;
  unchanged: number;
  unmatched: number;
  ambiguous: number;
  walls: BulkExecutionWallRead[];
}
