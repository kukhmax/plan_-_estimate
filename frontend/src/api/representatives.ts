import {
  ProjectRepresentative,
  ProjectRepresentativeCreatePayload,
  ProjectRepresentativeListResponse,
  ProjectRepresentativeUpdatePayload,
} from '../types/representative';
import { apiRequest } from './http';

function basePath(projectId: string): string {
  return `/api/projects/${projectId}/representatives`;
}

export function fetchRepresentatives(projectId: string, includeArchived = false): Promise<ProjectRepresentativeListResponse> {
  return apiRequest(`${basePath(projectId)}${includeArchived ? '?include_archived=true' : ''}`);
}

export function createRepresentative(projectId: string, payload: ProjectRepresentativeCreatePayload): Promise<ProjectRepresentative> {
  return apiRequest(basePath(projectId), { method: 'POST', body: JSON.stringify(payload) });
}

export function updateRepresentative(
  projectId: string,
  representativeId: string,
  payload: ProjectRepresentativeUpdatePayload,
): Promise<ProjectRepresentative> {
  return apiRequest(`${basePath(projectId)}/${representativeId}`, { method: 'PATCH', body: JSON.stringify(payload) });
}

export function archiveRepresentative(projectId: string, representativeId: string): Promise<ProjectRepresentative> {
  return apiRequest(`${basePath(projectId)}/${representativeId}/archive`, { method: 'POST' });
}

export function restoreRepresentative(projectId: string, representativeId: string): Promise<ProjectRepresentative> {
  return apiRequest(`${basePath(projectId)}/${representativeId}/restore`, { method: 'POST' });
}
