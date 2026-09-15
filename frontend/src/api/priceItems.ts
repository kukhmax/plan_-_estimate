import {
  PriceItem,
  PriceItemCreatePayload,
  PriceItemListParams,
  PriceItemListResponse,
  PriceItemUpdatePayload,
} from '../types/priceItem';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Owner-scoped /api/price-items client (Stage 9C). The backend bootstraps the
 * owner's seed catalog on list, edits existing rows are never overwritten, and
 * the semantic ``code`` is server-generated on create and immutable afterwards.
 */
export async function fetchPriceItems(
  params?: PriceItemListParams,
): Promise<PriceItemListResponse> {
  const url = new URL(`${API_BASE}/api/price-items`, window.location.origin);
  if (params?.search) url.searchParams.set('search', params.search);
  if (params?.category) url.searchParams.set('category', params.category);
  if (params?.archived && params.archived !== 'active') {
    url.searchParams.set('archived', params.archived);
  }

  const resp = await fetch(url.toString(), {
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
  });
  if (!resp.ok) throw new Error(`Failed to fetch price items: ${resp.status}`);
  return resp.json();
}

export async function createPriceItem(
  payload: PriceItemCreatePayload,
): Promise<PriceItem> {
  const resp = await fetch(`${API_BASE}/api/price-items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail ?? `Failed to create price item: ${resp.status}`);
  }
  return resp.json();
}

export async function updatePriceItem(
  id: string,
  payload: PriceItemUpdatePayload,
): Promise<PriceItem> {
  const resp = await fetch(`${API_BASE}/api/price-items/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`Failed to update price item: ${resp.status}`);
  return resp.json();
}

export async function archivePriceItem(id: string): Promise<PriceItem> {
  const resp = await fetch(`${API_BASE}/api/price-items/${id}/archive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
  });
  if (!resp.ok) throw new Error(`Failed to archive price item: ${resp.status}`);
  return resp.json();
}

export async function restorePriceItem(id: string): Promise<PriceItem> {
  const resp = await fetch(`${API_BASE}/api/price-items/${id}/restore`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
  });
  if (!resp.ok) throw new Error(`Failed to restore price item: ${resp.status}`);
  return resp.json();
}