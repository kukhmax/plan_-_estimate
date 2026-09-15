import { PriceMarketReferenceListResponse } from '../types/marketEvidence';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Read-only owner market evidence for one PriceItem (Stage 9E.6A contract:
 * GET /api/price-items/{id}/market-reference → { items, total }). */
export async function fetchMarketEvidence(
  priceItemId: string,
): Promise<PriceMarketReferenceListResponse> {
  const url = new URL(
    `${API_BASE}/api/price-items/${priceItemId}/market-reference`,
    window.location.origin,
  );
  const resp = await fetch(url.toString(), {
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
  });
  if (!resp.ok) throw new Error(`Failed to fetch market evidence: ${resp.status}`);
  return resp.json();
}