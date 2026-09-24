import {
  CoefficientGroupCreatePayload,
  CoefficientGroupListResponse,
  CoefficientGroupRead,
  CoefficientGroupUpdatePayload,
  CoefficientOptionCreatePayload,
  CoefficientOptionRead,
  CoefficientOptionUpdatePayload,
} from '../types/coefficient';
import { apiRequest } from './http';

export interface FetchCoefficientGroupsParams {
  archived?: 'active' | 'archived' | 'all';
  include_archived_options?: boolean;
}

export function fetchCoefficientGroups(
  params?: FetchCoefficientGroupsParams,
): Promise<CoefficientGroupListResponse> {
  const query = new URLSearchParams();
  if (params?.archived) {
    query.set('archived', params.archived);
  }
  if (params?.include_archived_options !== undefined) {
    query.set('include_archived_options', String(params.include_archived_options));
  }
  const queryString = query.toString();
  const path = `/api/price-coefficient-groups${queryString ? `?${queryString}` : ''}`;
  return apiRequest(path);
}

export function createCoefficientGroup(
  payload: CoefficientGroupCreatePayload,
): Promise<CoefficientGroupRead> {
  return apiRequest('/api/price-coefficient-groups', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getCoefficientGroup(
  groupId: string,
  params?: { include_archived_options?: boolean },
): Promise<CoefficientGroupRead> {
  const query = new URLSearchParams();
  if (params?.include_archived_options !== undefined) {
    query.set('include_archived_options', String(params.include_archived_options));
  }
  const queryString = query.toString();
  const path = `/api/price-coefficient-groups/${groupId}${queryString ? `?${queryString}` : ''}`;
  return apiRequest(path);
}

export function updateCoefficientGroup(
  groupId: string,
  payload: CoefficientGroupUpdatePayload,
): Promise<CoefficientGroupRead> {
  return apiRequest(`/api/price-coefficient-groups/${groupId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function archiveCoefficientGroup(groupId: string): Promise<CoefficientGroupRead> {
  return apiRequest(`/api/price-coefficient-groups/${groupId}/archive`, {
    method: 'POST',
  });
}

export function restoreCoefficientGroup(groupId: string): Promise<CoefficientGroupRead> {
  return apiRequest(`/api/price-coefficient-groups/${groupId}/restore`, {
    method: 'POST',
  });
}

export function createCoefficientOption(
  groupId: string,
  payload: CoefficientOptionCreatePayload,
): Promise<CoefficientOptionRead> {
  return apiRequest(`/api/price-coefficient-groups/${groupId}/options`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateCoefficientOption(
  optionId: string,
  payload: CoefficientOptionUpdatePayload,
): Promise<CoefficientOptionRead> {
  return apiRequest(`/api/price-coefficient-options/${optionId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function archiveCoefficientOption(optionId: string): Promise<CoefficientOptionRead> {
  return apiRequest(`/api/price-coefficient-options/${optionId}/archive`, {
    method: 'POST',
  });
}

export function restoreCoefficientOption(optionId: string): Promise<CoefficientOptionRead> {
  return apiRequest(`/api/price-coefficient-options/${optionId}/restore`, {
    method: 'POST',
  });
}
