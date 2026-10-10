import type { IssuedDocument } from '../types/document';
import type { Concealed, ConcealedChange, ConcealedListResponse } from '../types/concealed';
import { apiRequest } from './http';

function basePath(projectId: string): string {
  return `/api/projects/${projectId}/concealed-works`;
}

export function fetchConcealedWorks(projectId: string): Promise<ConcealedListResponse> {
  return apiRequest(basePath(projectId));
}

/** The draft of the object's protocol: created when there is none, the same draft otherwise. */
export function openConcealedDraft(projectId: string): Promise<Concealed> {
  return apiRequest(basePath(projectId), { method: 'POST' });
}

/** Record what was accepted; only what is sent changes (a null clears), the server answers with the whole protocol. */
export function updateConcealed(projectId: string, protocolId: string, changes: ConcealedChange): Promise<Concealed> {
  return apiRequest(`${basePath(projectId)}/${protocolId}`, { method: 'PATCH', body: JSON.stringify(changes) });
}

export function abandonConcealedDraft(projectId: string, protocolId: string): Promise<Concealed> {
  return apiRequest(`${basePath(projectId)}/${protocolId}/archive`, { method: 'POST' });
}

/** Freeze the draft and send the protocol to the owner's chat; the server refuses with the list of blockers while the gate is shut. */
export function issueConcealed(projectId: string, protocolId: string): Promise<IssuedDocument> {
  return apiRequest(`${basePath(projectId)}/${protocolId}/issue`, { method: 'POST' });
}
