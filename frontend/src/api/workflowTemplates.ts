import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { SurfaceTypeValue } from '../types/surface';
import { SurfaceWorkPlanRead } from '../types/workPlan';
import {
  ApplyTemplateRequest,
  WorkflowTemplateCreatePayload,
  WorkflowTemplateListResponse,
  WorkflowTemplateRead,
  WorkflowTemplateStepWrite,
  WorkflowTemplateUpdatePayload,
} from '../types/workflowTemplate';
import { ApiError, apiRequest } from './http';

export interface CompatibleTemplateFilter {
  substrate: SubstrateValue;
  quality_target: QualityLevelValue;
  surface_type?: SurfaceTypeValue;
}

/** Active templates matching a work-plan context (server-side filtering). */
export function fetchCompatibleTemplates(
  filter: CompatibleTemplateFilter,
): Promise<WorkflowTemplateListResponse> {
  const query = new URLSearchParams({
    archived: 'active',
    substrate: filter.substrate,
    quality_target: filter.quality_target,
  });
  if (filter.surface_type) query.set('surface_type', filter.surface_type);
  return apiRequest(`/api/workflow-templates?${query.toString()}`);
}

/** Owner template catalog for management (Stage 13F.3, Cennik → Procesy).
 * `surface_type` uses the server semantics: a template with an empty filter
 * ("any") matches every surface type. */
export function fetchWorkflowTemplates(filter: {
  archived: 'active' | 'archived';
  surface_type?: SurfaceTypeValue;
}): Promise<WorkflowTemplateListResponse> {
  const query = new URLSearchParams({ archived: filter.archived });
  if (filter.surface_type) query.set('surface_type', filter.surface_type);
  return apiRequest(`/api/workflow-templates?${query.toString()}`);
}

export function fetchWorkflowTemplate(templateId: string): Promise<WorkflowTemplateRead> {
  return apiRequest(`/api/workflow-templates/${templateId}`);
}

// ---- Stage 13F.4: management actions (metadata only; steps are 13F.5) -------

export function createWorkflowTemplate(payload: WorkflowTemplateCreatePayload): Promise<WorkflowTemplateRead> {
  return apiRequest('/api/workflow-templates', { method: 'POST', body: JSON.stringify(payload) });
}

export function updateWorkflowTemplate(
  templateId: string,
  payload: WorkflowTemplateUpdatePayload,
): Promise<WorkflowTemplateRead> {
  return apiRequest(`/api/workflow-templates/${templateId}`, { method: 'PATCH', body: JSON.stringify(payload) });
}

export function archiveWorkflowTemplate(templateId: string): Promise<WorkflowTemplateRead> {
  return apiRequest(`/api/workflow-templates/${templateId}/archive`, { method: 'POST' });
}

export function restoreWorkflowTemplate(templateId: string): Promise<WorkflowTemplateRead> {
  return apiRequest(`/api/workflow-templates/${templateId}/restore`, { method: 'POST' });
}

/** Stage 13F.5: full ordered step replacement with the 13F.2 optimistic
 * precondition -- `expected_step_ids` is the exact ordered step-id list the
 * editor was opened with; any difference is a 409 and nothing changes. */
export function replaceWorkflowTemplateSteps(
  templateId: string,
  steps: WorkflowTemplateStepWrite[],
  expectedStepIds: string[],
): Promise<WorkflowTemplateRead> {
  return apiRequest(`/api/workflow-templates/${templateId}/steps`, {
    method: 'PUT',
    body: JSON.stringify({ steps, expected_step_ids: expectedStepIds }),
  });
}

export type TemplateManagementErrorKind =
  | 'network'
  | 'stale_steps'
  | 'price_item_not_found'
  | 'not_found'
  | 'name_required'
  | 'quality_scale'
  | 'archived_item'
  | 'validation'
  | 'other';

/** Classifies a management failure so the UI can show a localized message.
 * The backend distinguishes these 422 cases only by message text, so the
 * known messages live HERE and nowhere else. */
export function classifyTemplateManagementError(error: unknown): TemplateManagementErrorKind {
  if (!(error instanceof ApiError) || error.status >= 500) return 'network';
  if (error.status === 409 && error.message.includes('steps changed since they were read')) return 'stale_steps';
  if (error.status === 404 && error.message === 'Price item not found') return 'price_item_not_found';
  if (error.status === 404) return 'not_found';
  if (error.status === 422) {
    if (error.message.includes('require a display_name')) return 'name_required';
    if (error.message.includes('does not fit any substrate')) return 'quality_scale';
    if (error.message.includes('Archived price item')) return 'archived_item';
    return 'validation';
  }
  return 'other';
}

export function applyTemplateToWorkPlan(
  projectId: string,
  roomId: string,
  surfaceId: string,
  payload: ApplyTemplateRequest,
): Promise<SurfaceWorkPlanRead> {
  return apiRequest(
    `/api/projects/${projectId}/rooms/${roomId}/surfaces/${surfaceId}/work-plan/apply-template`,
    { method: 'POST', body: JSON.stringify(payload) },
  );
}

export type ApplyTemplateErrorKind =
  | 'stale_template'
  | 'stale_plan'
  | 'template_unavailable'
  | 'conflict'
  | 'validation'
  | 'transport'
  | 'other';

/**
 * Classifies an apply-template failure. Stage 13E.3 distinguishes its 409
 * cases only by message, so the known messages live HERE and nowhere else.
 * Future hardening: machine-readable domain error codes on the backend.
 */
export function classifyApplyTemplateError(error: unknown): ApplyTemplateErrorKind {
  // No response, or a server/gateway failure: the outcome is uncertain, so
  // the caller must retry with the SAME application_id.
  if (!(error instanceof ApiError) || error.status >= 500) return 'transport';
  if (error.status === 404 && error.message === 'Workflow template not found') {
    return 'template_unavailable';
  }
  if (error.status === 409) {
    if (error.message.includes('changed since it was previewed')) return 'stale_template';
    if (error.message.includes('changed since it was confirmed for replacement')) return 'stale_plan';
    if (error.message.includes('workflow template is archived')) return 'template_unavailable';
    return 'conflict';
  }
  if (error.status === 422) return 'validation';
  return 'other';
}
