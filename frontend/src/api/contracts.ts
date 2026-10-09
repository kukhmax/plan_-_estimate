import { Contract, ContractAnswersChange, ContractListResponse } from '../types/contract';
import { apiRequest } from './http';

function basePath(projectId: string): string {
  return `/api/projects/${projectId}/contracts`;
}

export function fetchContracts(projectId: string): Promise<ContractListResponse> {
  return apiRequest(basePath(projectId));
}

/** The draft of the object's contract: created when there is none, the same draft otherwise. */
export function openContractDraft(projectId: string): Promise<Contract> {
  return apiRequest(basePath(projectId), { method: 'POST' });
}

export function saveContractAnswers(projectId: string, contractId: string, answers: ContractAnswersChange): Promise<Contract> {
  return apiRequest(`${basePath(projectId)}/${contractId}/answers`, { method: 'PATCH', body: JSON.stringify({ answers }) });
}

export function abandonContractDraft(projectId: string, contractId: string): Promise<Contract> {
  return apiRequest(`${basePath(projectId)}/${contractId}/archive`, { method: 'POST' });
}
