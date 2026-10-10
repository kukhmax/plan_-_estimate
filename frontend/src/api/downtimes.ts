import type { Downtime, DowntimeChange, DowntimeListResponse } from '../types/downtime';
import type { IssuedDocument } from '../types/document';
import { apiRequest } from './http';

function basePath(projectId: string): string {
  return `/api/projects/${projectId}/downtimes`;
}

export function fetchDowntimes(projectId: string): Promise<DowntimeListResponse> {
  return apiRequest(basePath(projectId));
}

/** The open episode of the object: created when there is none, the same one otherwise. */
export function openDowntime(projectId: string): Promise<Downtime> {
  return apiRequest(basePath(projectId), { method: 'POST' });
}

/** Record the notice (a draft) or the protocol (a noticed episode); only what is sent changes, the server answers with the whole episode. */
export function updateDowntime(projectId: string, episodeId: string, changes: DowntimeChange): Promise<Downtime> {
  return apiRequest(`${basePath(projectId)}/${episodeId}`, { method: 'PATCH', body: JSON.stringify(changes) });
}

export function abandonDowntime(projectId: string, episodeId: string): Promise<Downtime> {
  return apiRequest(`${basePath(projectId)}/${episodeId}/archive`, { method: 'POST' });
}

/** Freeze the notice and send it to the owner's chat; the server refuses with the list of blockers while the gate is shut. */
export function issueDowntimeNotice(projectId: string, episodeId: string): Promise<IssuedDocument> {
  return apiRequest(`${basePath(projectId)}/${episodeId}/issue-notice`, { method: 'POST' });
}

/** Freeze the protocol and send it to the owner's chat; the server refuses with the list of blockers while the gate is shut. */
export function issueDowntimeProtocol(projectId: string, episodeId: string): Promise<IssuedDocument> {
  return apiRequest(`${basePath(projectId)}/${episodeId}/issue-protocol`, { method: 'POST' });
}
