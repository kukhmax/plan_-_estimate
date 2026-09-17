import { EstimateListResponse, EstimateRead, EstimateSummaryRead } from '../types/estimate';
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
