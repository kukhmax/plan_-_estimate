import type { AddMaterialsResult, CalcFields, MaterialCalc, MaterialNorm, NormChanges, Statement } from '../types/materials';
import { apiRequest } from './http';

const calcs = (projectId: string, roomId: string) => `/api/projects/${projectId}/rooms/${roomId}/material-calcs`;

export async function fetchCalcs(projectId: string, roomId: string): Promise<MaterialCalc[]> {
  return (await apiRequest<{ items: MaterialCalc[] }>(calcs(projectId, roomId))).items;
}

export function createCalc(projectId: string, roomId: string, fields: CalcFields): Promise<MaterialCalc> {
  return apiRequest(calcs(projectId, roomId), { method: 'POST', body: JSON.stringify(fields) });
}

/** The data of a calculation are replaced whole; `title: null` clears the title. */
export function updateCalc(projectId: string, roomId: string, calcId: string, fields: { title?: string | null; params?: CalcFields['params'] }): Promise<MaterialCalc> {
  return apiRequest(`${calcs(projectId, roomId)}/${calcId}`, { method: 'PATCH', body: JSON.stringify(fields) });
}

export function deleteCalc(projectId: string, roomId: string, calcId: string): Promise<void> {
  return apiRequest(`${calcs(projectId, roomId)}/${calcId}`, { method: 'DELETE' });
}

/** The statement of an object: the totals by material (packs once over the sum) and every calculation. */
export function fetchStatement(projectId: string): Promise<Statement> {
  return apiRequest(`/api/projects/${projectId}/materials`);
}

export async function fetchNorms(): Promise<MaterialNorm[]> {
  return (await apiRequest<{ items: MaterialNorm[] }>('/api/material-norms')).items;
}

export function updateNorm(normId: string, changes: NormChanges): Promise<MaterialNorm> {
  return apiRequest(`/api/material-norms/${normId}`, { method: 'PATCH', body: JSON.stringify(changes) });
}

/** The materials of the object become the lines of a draft estimate (a snapshot; what is in it already is not added twice). */
export function addMaterialsToEstimate(projectId: string, estimateId: string): Promise<AddMaterialsResult> {
  return apiRequest(`/api/projects/${projectId}/estimates/${estimateId}/add-materials`, { method: 'POST' });
}
