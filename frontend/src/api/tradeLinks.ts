import type { LinkTrade, TradeAnswersResponse, TradeLinkCreated, TradeLinkInfo, TradeLinksResponse } from '../types/tradeLink';
import type { Locale } from '../utils/locale';
import { apiRequest } from './http';

const base = (projectId: string) => `/api/projects/${encodeURIComponent(projectId)}/trade-links`;

export function fetchTradeLinks(projectId: string): Promise<TradeLinksResponse> {
  return apiRequest(base(projectId));
}

export function createTradeLink(projectId: string, trade: LinkTrade, language: Locale, note: string | null): Promise<TradeLinkCreated> {
  return apiRequest(`${base(projectId)}/${trade}`, { method: 'POST', body: JSON.stringify({ language, note }) });
}

export function changeTradeLinkNote(projectId: string, trade: LinkTrade, note: string | null): Promise<TradeLinkInfo> {
  return apiRequest(`${base(projectId)}/${trade}`, { method: 'PATCH', body: JSON.stringify({ note }) });
}

export function extendTradeLink(projectId: string, trade: LinkTrade): Promise<TradeLinkInfo> {
  return apiRequest(`${base(projectId)}/${trade}/extend`, { method: 'POST' });
}

export function revokeTradeLink(projectId: string, trade: LinkTrade): Promise<void> {
  return apiRequest(`${base(projectId)}/${trade}`, { method: 'DELETE' });
}

export function fetchTradeAnswers(projectId: string, trade: LinkTrade): Promise<TradeAnswersResponse> {
  return apiRequest(`${base(projectId)}/${trade}/answers`);
}
