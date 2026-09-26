import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { SurfaceTypeValue } from '../types/surface';
import { SurfaceWorkPlanRead } from '../types/workPlan';
import {
  ApplyTemplateRequest,
  WorkflowTemplateListResponse,
  WorkflowTemplateRead,
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

export function fetchWorkflowTemplate(templateId: string): Promise<WorkflowTemplateRead> {
  return apiRequest(`/api/workflow-templates/${templateId}`);
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
