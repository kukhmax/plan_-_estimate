import { PriceItem } from '../types/priceItem';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface QuickWork {
  code: string;
  ceiling_code: string;
  default_on: boolean;
}

/** What the quick estimate offers (V2-4): the works in order, the price rows behind them, the substrates and the defaults. */
export interface QuickEstimateOptions {
  works: QuickWork[];
  items: PriceItem[];
  substrates: SubstrateValue[];
  default_substrate: SubstrateValue;
  default_quality: QualityLevelValue;
}

export interface QuickRoomPayload {
  name: string;
  length: string;
  width: string;
  height: string;
}

export interface QuickEstimatePayload {
  client_id?: string;
  client_name?: string;
  client_phone?: string;
  address: string;
  city: string;
  rooms: QuickRoomPayload[];
  work_codes: string[];
  include_ceiling: boolean;
  substrate: SubstrateValue;
  quality_target: QualityLevelValue;
}

export interface QuickEstimateResult {
  project_id: string;
  client_id: string;
  estimate_id: string;
  rooms: number;
  lines: number;
  unpriced_lines: number;
  total: string | null;
}

/** An answer of the server that the screen can name: the machine code of `detail.code`. */
export class QuickEstimateRequestError extends Error {
  constructor(public readonly code: string | null, public readonly status: number) {
    super(code ?? `quick estimate failed: ${status}`);
  }
}

export async function fetchQuickEstimateOptions(): Promise<QuickEstimateOptions> {
  const resp = await fetch(`${API_BASE}/api/quick-estimate/options`, { headers: { 'Content-Type': 'application/json', ...getAuthHeaders() } });
  if (!resp.ok) throw new QuickEstimateRequestError(null, resp.status);
  return resp.json();
}

export async function createQuickEstimate(payload: QuickEstimatePayload): Promise<QuickEstimateResult> {
  const resp = await fetch(`${API_BASE}/api/quick-estimate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    const code = typeof body?.detail?.code === 'string' ? body.detail.code : null;
    throw new QuickEstimateRequestError(code, resp.status);
  }
  return resp.json();
}
