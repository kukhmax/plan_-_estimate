import { QualityLevelValue, SubstrateValue } from './checklist';
import { SurfaceTypeValue } from './surface';
import { SurfacePriceItemSummaryRead } from './workPlan';

/** Mirrors backend `TemplateApplicationMode`. */
export type TemplateApplicationMode = 'APPEND' | 'REPLACE';

export interface WorkflowTemplateStepRead {
  id: string;
  position: number;
  price_item_id: string;
  is_optional: boolean;
  note: string | null;
  wait_after_hours: number | null;
  price_item: SurfacePriceItemSummaryRead | null;
}

export interface WorkflowTemplateRead {
  id: string;
  code: string;
  name_key: string | null;
  display_name: string | null;
  description: string | null;
  applies_to_substrates: SubstrateValue[];
  applies_to_quality: QualityLevelValue[];
  applies_to_surface_types: SurfaceTypeValue[];
  position: number;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  steps: WorkflowTemplateStepRead[];
}

export interface WorkflowTemplateListResponse {
  items: WorkflowTemplateRead[];
  total: number;
}

/** POST …/work-plan/apply-template (Stage 13E.3). */
export interface ApplyTemplateRequest {
  application_id: string;
  template_id: string;
  mode: TemplateApplicationMode;
  selected_optional_step_ids: string[];
  /** Final reviewed APPEND selection (13E.5B-FIX.4): template step ids only. */
  selected_step_ids?: string[];
  expected_step_ids: string[];
  expected_occurrence_keys?: string[];
  replace_confirmed?: boolean;
}
