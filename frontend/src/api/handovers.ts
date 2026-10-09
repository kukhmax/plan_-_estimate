import type { Handover, HandoverChange, HandoverListResponse } from '../types/handover';
import type { IssuedDocument } from '../types/document';
import { apiRequest } from './http';

function basePath(projectId: string): string {
  return `/api/projects/${projectId}/handovers`;
}

export function fetchHandovers(projectId: string): Promise<HandoverListResponse> {
  return apiRequest(basePath(projectId));
}

/** The draft of the object's protocol: created when there is none, the same draft otherwise. */
export function openHandoverDraft(projectId: string): Promise<Handover> {
  return apiRequest(basePath(projectId), { method: 'POST' });
}

/** Record what was found; only what is sent changes (a null clears), the server answers with the whole protocol. */
export function updateHandover(projectId: string, handoverId: string, changes: HandoverChange): Promise<Handover> {
  return apiRequest(`${basePath(projectId)}/${handoverId}`, { method: 'PATCH', body: JSON.stringify(changes) });
}

export function abandonHandoverDraft(projectId: string, handoverId: string): Promise<Handover> {
  return apiRequest(`${basePath(projectId)}/${handoverId}/archive`, { method: 'POST' });
}

/** Freeze the draft and send the protocol to the owner's chat; the server refuses with the list of blockers while the gate is shut. */
export function issueHandover(projectId: string, handoverId: string): Promise<IssuedDocument> {
  return apiRequest(`${basePath(projectId)}/${handoverId}/issue`, { method: 'POST' });
}
