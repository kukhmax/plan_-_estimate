import { EstimateLineRead, EstimateLineUpdatePayload, EstimateListResponse, EstimateRead, EstimateSummaryRead } from '../types/estimate';
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
