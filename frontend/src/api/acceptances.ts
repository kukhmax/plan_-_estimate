import type { Acceptance, AcceptanceChange, AcceptanceListResponse } from '../types/acceptance';
import type { IssuedDocument } from '../types/document';
import { apiRequest } from './http';

function basePath(projectId: string): string {
  return `/api/projects/${projectId}/acceptances`;
}

export function fetchAcceptances(projectId: string): Promise<AcceptanceListResponse> {
  return apiRequest(basePath(projectId));
}

/** The draft of the object's protocol: created when there is none, the same draft otherwise. */
export function openAcceptanceDraft(projectId: string): Promise<Acceptance> {
  return apiRequest(basePath(projectId), { method: 'POST' });
}

/** Record the assessment; only what is sent changes (a null clears), the server answers with the whole protocol and its derived result. */
export function updateAcceptance(projectId: string, protocolId: string, changes: AcceptanceChange): Promise<Acceptance> {
  return apiRequest(`${basePath(projectId)}/${protocolId}`, { method: 'PATCH', body: JSON.stringify(changes) });
}

export function abandonAcceptanceDraft(projectId: string, protocolId: string): Promise<Acceptance> {
  return apiRequest(`${basePath(projectId)}/${protocolId}/archive`, { method: 'POST' });
}

/** Freeze the draft and send the protocol to the owner's chat; the server refuses with the list of blockers while the gate is shut. */
export function issueAcceptance(projectId: string, protocolId: string): Promise<IssuedDocument> {
  return apiRequest(`${basePath(projectId)}/${protocolId}/issue`, { method: 'POST' });
}
