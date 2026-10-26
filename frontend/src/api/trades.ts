import type { TradeKey, TradesResponse } from '../types/trades';
import { apiRequest } from './http';

export function fetchTrades(): Promise<TradesResponse> {
  return apiRequest('/api/trades');
}

/** Choose the trades the owner works in; the server answers with the whole catalogue and the saved choice. */
export function saveTrades(enabled: TradeKey[]): Promise<TradesResponse> {
  return apiRequest('/api/trades', { method: 'PUT', body: JSON.stringify({ enabled }) });
}
