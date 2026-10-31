import type { PortalDecideInput, PortalEstimateDecision, PortalPage, PortalWhy } from '../types/clientLink';
import { API_BASE, ApiError } from './http';

/**
 * The open page of the client (V2-8). It never uses the login, the offline copies or the queue of the application: the secret of the link goes in
 * the header `X-Client-Link`, nothing is stored in the browser, and every answer is fresh.
 */
async function request<T>(token: string, path: string, lang: string | null, init?: RequestInit): Promise<T> {
  const query = lang ? `?lang=${encodeURIComponent(lang)}` : '';
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/public/client${path}${query}`, {
      ...init,
      cache: 'no-store',
      referrerPolicy: 'no-referrer',
      headers: { 'Content-Type': 'application/json', 'X-Client-Link': token },
    });
  } catch {
    throw new ApiError('network', 0, 'NETWORK');
  }
  if (response.ok) return (await response.json()) as T;
  let code: string | undefined;
  let message = `Request failed (${response.status})`;
  try {
    const payload: unknown = await response.json();
    const detail = payload && typeof payload === 'object' && 'detail' in payload ? (payload as { detail: unknown }).detail : null;
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const d = detail as { code?: unknown; message?: unknown };
      if (typeof d.code === 'string') code = d.code;
      if (typeof d.message === 'string') message = d.message;
    }
  } catch {
    // the answer was not JSON: the status alone says what happened
  }
  throw new ApiError(message, response.status, code);
}

export function fetchPortalPage(token: string, lang: string | null): Promise<PortalPage> {
  return request(token, '', lang);
}

export function decidePortalEstimate(token: string, lang: string | null, input: PortalEstimateDecision): Promise<PortalPage> {
  return request(token, '/estimate/decide', lang, { method: 'POST', body: JSON.stringify(input) });
}

export function decidePortalProposal(token: string, proposalId: string, lang: string | null, input: PortalDecideInput): Promise<PortalPage> {
  return request(token, `/proposals/${encodeURIComponent(proposalId)}/decide`, lang, { method: 'POST', body: JSON.stringify(input) });
}

/** Owner 2026-10-31: "Dlaczego te prace?" -- read only when the client asks (the photos come with links signed for half an hour). */
export function fetchPortalWhy(token: string): Promise<PortalWhy> {
  return request(token, '/why', null);
}
