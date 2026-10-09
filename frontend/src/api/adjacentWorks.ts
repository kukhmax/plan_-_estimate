import {
  AdjacentWork,
  AdjacentWorkCreatePayload,
  AdjacentWorkListResponse,
  AdjacentWorkUpdatePayload,
} from '../types/adjacentWork';
import { apiRequest } from './http';

function basePath(projectId: string): string {
  return `/api/projects/${projectId}/adjacent-works`;
}

export function fetchAdjacentWorks(projectId: string, includeArchived = false): Promise<AdjacentWorkListResponse> {
  return apiRequest(`${basePath(projectId)}${includeArchived ? '?include_archived=true' : ''}`);
}

export function createAdjacentWork(projectId: string, payload: AdjacentWorkCreatePayload): Promise<AdjacentWork> {
  return apiRequest(basePath(projectId), { method: 'POST', body: JSON.stringify(payload) });
}

export function updateAdjacentWork(projectId: string, workId: string, payload: AdjacentWorkUpdatePayload): Promise<AdjacentWork> {
  return apiRequest(`${basePath(projectId)}/${workId}`, { method: 'PATCH', body: JSON.stringify(payload) });
}

export function archiveAdjacentWork(projectId: string, workId: string): Promise<AdjacentWork> {
  return apiRequest(`${basePath(projectId)}/${workId}/archive`, { method: 'POST' });
}

export function restoreAdjacentWork(projectId: string, workId: string): Promise<AdjacentWork> {
  return apiRequest(`${basePath(projectId)}/${workId}/restore`, { method: 'POST' });
}
