import { Contract, ContractAnswersChange, ContractGate, ContractListResponse } from '../types/contract';
import type { IssuedDocument } from '../types/document';
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

/** What stands between the draft and its issue (an empty list of blockers = ready). */
export function fetchContractGate(projectId: string, contractId: string): Promise<ContractGate> {
  return apiRequest(`${basePath(projectId)}/${contractId}/gate`);
}

/** Freeze the draft and send the contract to the owner's chat; the server refuses with the list of blockers while the gate is shut. */
export function issueContract(projectId: string, contractId: string): Promise<IssuedDocument> {
  return apiRequest(`${basePath(projectId)}/${contractId}/issue`, { method: 'POST' });
}
