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

/** What deleting an archived object for good would remove (archive cleanup AC-5b); the server counts it, nothing changes. */
export interface ProjectPurgePreview {
  project_id: string;
  name: string;
  archived: boolean;
  can_purge: boolean;
  rooms: number;
  surfaces: number;
  openings: number;
  inspections: number;
  estimates: number;
  /** Contracts and protocols of every kind, drafts and archived ones included. */
  documents: number;
  /** Documents given to the client: their copies in Telegram chats stay. */
  sent_documents: number;
  photos: number;
  photo_files: number;
  bytes: number;
  annotations: number;
  may_be_in_backups: boolean;
  /** `kind` is a kind of document: CONTRACT | HANDOVER | CONCEALED_WORKS | DECISION | ACCEPTANCE | DOWNTIME. */
  blockers: Array<{ kind: string; protocol_id: string; status: string }>;
}

export interface ProjectPurgeResult {
  purged: boolean;
  photo_files: number;
  /** File sets still to be removed from the storage: a retry finishes them. */
  storage_pending: number;
}

export function fetchProjectPurgePreview(projectId: string): Promise<ProjectPurgePreview> {
  return apiRequest(`/api/projects/${projectId}/purge-preview`);
}

/** Only an archived object that no issued / signed document holds; refused with 409 otherwise. */
export function purgeProject(projectId: string): Promise<ProjectPurgeResult> {
  return apiRequest(`/api/projects/${projectId}/purge`, { method: 'POST' });
}
