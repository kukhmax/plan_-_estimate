import { apiRequest } from './http';
import { ClientType, ClientListResponse, ClientCreatePayload, ClientUpdatePayload } from '../types/client';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function fetchClients(params?: {
  search?: string;
  include_archived?: boolean;
}): Promise<ClientListResponse> {
  const query = new URLSearchParams();
  if (params?.search) query.set('search', params.search);
  if (params?.include_archived) query.set('include_archived', 'true');
  const suffix = query.toString();
  // through apiRequest: the list of clients is one of the copies kept on the phone for work without a signal (Stage 19B)
  return apiRequest(`/api/clients${suffix ? `?${suffix}` : ''}`);
}

export function fetchClient(id: string): Promise<ClientType> {
  return apiRequest(`/api/clients/${id}`);
}

export async function createClient(payload: ClientCreatePayload): Promise<ClientType> {
  const resp = await fetch(`${API_BASE}/api/clients`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail ?? `Failed to create client: ${resp.status}`);
  }
  return resp.json();
}

export async function updateClient(id: string, payload: ClientUpdatePayload): Promise<ClientType> {
  const resp = await fetch(`${API_BASE}/api/clients/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`Failed to update client: ${resp.status}`);
  return resp.json();
}

export async function archiveClient(id: string): Promise<ClientType> {
  const resp = await fetch(`${API_BASE}/api/clients/${id}/archive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
  });
  if (!resp.ok) throw new Error(`Failed to archive client: ${resp.status}`);
  return resp.json();
}

export async function restoreClient(id: string): Promise<ClientType> {
  const resp = await fetch(`${API_BASE}/api/clients/${id}/restore`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
  });
  if (!resp.ok) throw new Error(`Failed to restore client: ${resp.status}`);
  return resp.json();
}
