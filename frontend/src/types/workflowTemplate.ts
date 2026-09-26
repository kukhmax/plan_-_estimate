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
  /** Stage 13F.3 FIX.2: locale key of an untouched canonical built-in note. */
  note_key?: string | null;
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
  /** Stage 13F.2: derived server-side from the seeded recipe codes (read-only). */
  is_default?: boolean;
  /** Stage 13F.3 FIX.1: locale key of an untouched canonical built-in
   * description (null for custom / owner-edited descriptions). */
  description_key?: string | null;
  created_at: string;
  updated_at: string;
  steps: WorkflowTemplateStepRead[];
}

/** One step in a create payload (Stage 13F.4 duplicate copies them verbatim). */
export interface WorkflowTemplateStepWrite {
  price_item_id: string;
  is_optional: boolean;
  note: string | null;
  wait_after_hours: number | null;
}

/** POST /workflow-templates. `code` is always server-generated (CUSTOM_*). */
export interface WorkflowTemplateCreatePayload {
  display_name: string;
  description: string | null;
  applies_to_substrates: SubstrateValue[];
  applies_to_quality: QualityLevelValue[];
  applies_to_surface_types: SurfaceTypeValue[];
  steps: WorkflowTemplateStepWrite[];
}

/** PATCH /workflow-templates/{id}: only changed fields are sent. For
 * `display_name` an explicit null clears a built-in's custom name. */
export type WorkflowTemplateUpdatePayload = Partial<{
  display_name: string | null;
  description: string | null;
  applies_to_substrates: SubstrateValue[];
  applies_to_quality: QualityLevelValue[];
  applies_to_surface_types: SurfaceTypeValue[];
}>;

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
