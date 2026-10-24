import { PriceItemListResponse } from '../types/priceItem';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** The example object of the account (V2-3): `project_id` is null when there is none. */
export interface ExampleStatus {
  project_id: string | null;
  client_id: string | null;
}

export interface ExampleCreated extends ExampleStatus {
  created: boolean;
}

export interface ExampleRemoved {
  removed_project: boolean;
  removed_client: boolean;
}

async function call<T>(method: string, path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}/api/onboarding/${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
  });
  if (!resp.ok) throw new Error(`Onboarding request failed: ${resp.status}`);
  return resp.json();
}

/** The five rows a new contractor prices first (the choice of rows is the server's). */
export const fetchStarterPrices = (): Promise<PriceItemListResponse> => call('GET', 'starter-prices');
export const fetchExample = (): Promise<ExampleStatus> => call('GET', 'example');
export const createExample = (): Promise<ExampleCreated> => call('POST', 'example');
export const deleteExample = (): Promise<ExampleRemoved> => call('DELETE', 'example');
