import { ContractCatalog } from '../types/contractCatalog';
import { apiRequest } from './http';

export function fetchContractCatalog(): Promise<ContractCatalog> {
  return apiRequest<ContractCatalog>('/api/contract-catalog');
}
