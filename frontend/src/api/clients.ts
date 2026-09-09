import { ClientType, ClientListResponse, ClientCreatePayload, ClientUpdatePayload } from '../types/client';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchClients(params?: {
  search?: string;
  include_archived?: boolean;
}): Promise<ClientListResponse> {
  const url = new URL(`${API_BASE}/api/clients`, window.location.origin);
  if (params?.search) url.searchParams.set('search', params.search);
  if (params?.include_archived) url.searchParams.set('include_archived', 'true');

  const resp = await fetch(url.toString(), {
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
  });
  if (!resp.ok) throw new Error(`Failed to fetch clients: ${resp.status}`);
  return resp.json();
}

export async function fetchClient(id: string): Promise<ClientType> {
  const resp = await fetch(`${API_BASE}/api/clients/${id}`, {
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
  });
  if (!resp.ok) throw new Error(`Client not found: ${resp.status}`);
  return resp.json();
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
