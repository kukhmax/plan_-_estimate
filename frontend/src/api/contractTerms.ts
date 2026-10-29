import type { AnswerValue } from '../types/contract';
import type { ContractTerms } from '../types/contractTerms';
import { apiRequest } from './http';

/** "Moje standardowe warunki umowy" (UX walk B2): the owner's terms, the keys a term may have and his latest contract's terms. */
export function fetchContractTerms(): Promise<ContractTerms> {
  return apiRequest('/api/contract-terms');
}

/** Replace all the terms (a missing key is no term); the server checks every answer like an answer of the contract. */
export function saveContractTerms(answers: Record<string, AnswerValue>): Promise<ContractTerms> {
  return apiRequest('/api/contract-terms', { method: 'PUT', body: JSON.stringify({ answers }) });
}
