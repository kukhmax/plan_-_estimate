import type { Decision, DecisionChange, DecisionListResponse } from '../types/decision';
import type { IssuedDocument } from '../types/document';
import { apiRequest } from './http';

function basePath(projectId: string): string {
  return `/api/projects/${projectId}/decisions`;
}

export function fetchDecisions(projectId: string): Promise<DecisionListResponse> {
  return apiRequest(basePath(projectId));
}

/** The draft of the object's protocol: created when there is none, the same draft otherwise. */
export function openDecisionDraft(projectId: string): Promise<Decision> {
  return apiRequest(basePath(projectId), { method: 'POST' });
}

/** Record the items and the decisions; only what is sent changes (a null clears), the server answers with the whole protocol. */
export function updateDecision(projectId: string, protocolId: string, changes: DecisionChange): Promise<Decision> {
  return apiRequest(`${basePath(projectId)}/${protocolId}`, { method: 'PATCH', body: JSON.stringify(changes) });
}

export function abandonDecisionDraft(projectId: string, protocolId: string): Promise<Decision> {
  return apiRequest(`${basePath(projectId)}/${protocolId}/archive`, { method: 'POST' });
}

/** Freeze the draft and send the protocol to the owner's chat; the server refuses with the list of blockers while the gate is shut. */
export function issueDecision(projectId: string, protocolId: string): Promise<IssuedDocument> {
  return apiRequest(`${basePath(projectId)}/${protocolId}/issue`, { method: 'POST' });
}
