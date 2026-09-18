import { EstimateLineRead, EstimateLineUpdatePayload, EstimateListResponse, EstimateRead, EstimateSummaryRead, RegenerationPreviewResponse } from '../types/estimate';
import { apiRequest } from './http';

function estimatesPath(projectId: string): string {
  return `/api/projects/${projectId}/estimates`;
}

export function listEstimates(projectId: string): Promise<EstimateListResponse> {
  return apiRequest(estimatesPath(projectId));
}

export function generateEstimate(projectId: string): Promise<EstimateSummaryRead> {
  return apiRequest(`${estimatesPath(projectId)}/generate`, { method: 'POST' });
}

export function getEstimate(projectId: string, estimateId: string): Promise<EstimateRead> {
  return apiRequest(`${estimatesPath(projectId)}/${estimateId}`);
}

// Payload keys are built so that an omitted key means "leave unchanged" and an
// explicit `unit_price: null` means "mark as Do ustalenia" (Stage 10E contract) —
// callers must never send `quantity: null` (rejected by the backend).
export function patchEstimateLine(
  projectId: string,
  estimateId: string,
  lineId: string,
  payload: EstimateLineUpdatePayload,
): Promise<EstimateLineRead> {
  return apiRequest(`${estimatesPath(projectId)}/${estimateId}/lines/${lineId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

// Stage 10G.3B — read-only diff of what regeneration would change. Never
// mutates the estimate (Stage 10E contract); no request body.
export function previewEstimateRegeneration(
  projectId: string,
  estimateId: string,
): Promise<RegenerationPreviewResponse> {
  return apiRequest(`${estimatesPath(projectId)}/${estimateId}/regenerate-preview`, {
    method: 'POST',
  });
}

// Stage 10G.3B — explicitly confirmed regeneration; re-derives planned lines
// in-place on the DRAFT estimate, preserving quantity/price overrides per
// the existing Stage 10F backend contract. No request body.
export function regenerateEstimate(
  projectId: string,
  estimateId: string,
): Promise<RegenerationPreviewResponse> {
  return apiRequest(`${estimatesPath(projectId)}/${estimateId}/regenerate`, {
    method: 'POST',
  });
}
