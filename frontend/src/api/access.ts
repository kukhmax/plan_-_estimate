import type { AccessEntry, AccessOverview, AccessSettings } from '../types/access';
import { apiRequest } from './http';

/** The access list and its settings; the administrator only (closed registration). */
export function fetchAccess(): Promise<AccessOverview> {
  return apiRequest('/api/access');
}

export function decideAccess(id: string, status: 'ACTIVE' | 'BLOCKED'): Promise<AccessEntry> {
  return apiRequest(`/api/access/entries/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });
}

export function removeAccess(id: string): Promise<void> {
  return apiRequest(`/api/access/entries/${id}`, { method: 'DELETE' });
}

/** Only the fields sent are changed. */
export function saveAccessSettings(settings: Partial<AccessSettings>): Promise<AccessSettings> {
  return apiRequest('/api/access/settings', { method: 'PUT', body: JSON.stringify(settings) });
}
