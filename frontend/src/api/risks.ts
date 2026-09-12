import { apiRequest } from './http';
import {
  RiskDetail,
  RiskDetailResponse,
  RiskEvaluateRequest,
  RiskListResponse,
  RiskStatusValue,
} from '../types/risk';

function risksPath(projectId: string, roomId: string): string {
  return `/api/projects/${projectId}/rooms/${roomId}/risks`;
}

function riskPath(projectId: string, roomId: string, riskId: string): string {
  return `${risksPath(projectId, roomId)}/${riskId}`;
}

export function evaluateRisks(
  projectId: string,
  roomId: string,
  inspectionId: string,
): Promise<RiskDetailResponse> {
  const payload: RiskEvaluateRequest = { inspection_id: inspectionId };
  return apiRequest(`${risksPath(projectId, roomId)}/evaluate`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchRisks(
  projectId: string,
  roomId: string,
  {
    inspectionId,
    status,
  }: { inspectionId?: string; status?: RiskStatusValue } = {},
): Promise<RiskListResponse> {
  const params = new URLSearchParams();
  if (inspectionId) params.set('inspection_id', inspectionId);
  // "all" must be sent explicitly, not dropped: the backend defaults to active when the
  // status parameter is absent.
  if (status) params.set('status', status);
  const query = params.toString();
  return apiRequest(`${risksPath(projectId, roomId)}${query ? `?${query}` : ''}`);
}

export function fetchRiskDetail(
  projectId: string,
  roomId: string,
  riskId: string,
): Promise<RiskDetail> {
  return apiRequest(riskPath(projectId, roomId, riskId));
}