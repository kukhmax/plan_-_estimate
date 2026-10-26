import type { IssuedDocument } from '../types/document';
import type { Pressure, PressureChange, PressureListResponse } from '../types/pressure';
import { apiRequest } from './http';

function basePath(projectId: string): string {
  return `/api/projects/${projectId}/pressure-tests`;
}

export function fetchPressureTests(projectId: string): Promise<PressureListResponse> {
  return apiRequest(basePath(projectId));
}

/** The draft of the object's protocol: created when there is none, the same draft otherwise. */
export function openPressureDraft(projectId: string): Promise<Pressure> {
  return apiRequest(basePath(projectId), { method: 'POST' });
}

/** Record the test; only what is sent changes (a null clears), the server answers with the whole protocol. */
export function updatePressure(projectId: string, protocolId: string, changes: PressureChange): Promise<Pressure> {
  return apiRequest(`${basePath(projectId)}/${protocolId}`, { method: 'PATCH', body: JSON.stringify(changes) });
}

export function abandonPressureDraft(projectId: string, protocolId: string): Promise<Pressure> {
  return apiRequest(`${basePath(projectId)}/${protocolId}/archive`, { method: 'POST' });
}

/** Freeze the draft and send the protocol to the owner's chat; the server refuses with the list of blockers while the gate is shut. */
export function issuePressure(projectId: string, protocolId: string): Promise<IssuedDocument> {
  return apiRequest(`${basePath(projectId)}/${protocolId}/issue`, { method: 'POST' });
}
