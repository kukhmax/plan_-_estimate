import { apiRequest } from './http';
import {
  ProjectCreatePayload,
  ProjectListResponse,
  ProjectType,
  ProjectUpdatePayload,
} from '../types/project';

export function fetchProjects(includeArchived = false): Promise<ProjectListResponse> {
  const query = includeArchived ? '?include_archived=true' : '';
  return apiRequest(`/api/projects${query}`);
}

export function fetchProject(projectId: string): Promise<ProjectType> {
  return apiRequest(`/api/projects/${projectId}`);
}

export function createProject(payload: ProjectCreatePayload): Promise<ProjectType> {
  return apiRequest('/api/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateProject(
  projectId: string,
  payload: ProjectUpdatePayload,
): Promise<ProjectType> {
  return apiRequest(`/api/projects/${projectId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function archiveProject(projectId: string): Promise<ProjectType> {
  return apiRequest(`/api/projects/${projectId}/archive`, { method: 'POST' });
}

export function restoreProject(projectId: string): Promise<ProjectType> {
  return apiRequest(`/api/projects/${projectId}/restore`, { method: 'POST' });
}
