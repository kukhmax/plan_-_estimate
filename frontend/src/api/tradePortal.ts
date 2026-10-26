import type { PortalTradePage, RoomWrite } from '../types/tradeLink';
import { API_BASE, ApiError } from './http';

/**
 * The open page of the electrician and the plumber (V2-14). Like the page of the client it never uses the login, the offline copies or the queue
 * of the application: the secret of the link goes in the header `X-Trade-Link`, nothing is stored in the browser, and every answer is fresh.
 */
async function request<T>(token: string, path: string, lang: string | null, init?: RequestInit): Promise<T> {
  const query = lang ? `?lang=${encodeURIComponent(lang)}` : '';
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/public/trade${path}${query}`, {
      ...init,
      cache: 'no-store',
      referrerPolicy: 'no-referrer',
      headers: { 'Content-Type': 'application/json', 'X-Trade-Link': token },
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

export function fetchTradePage(token: string, lang: string | null): Promise<PortalTradePage> {
  return request(token, '', lang);
}

export function saveTradeRoom(token: string, roomId: string, lang: string | null, input: RoomWrite): Promise<PortalTradePage> {
  return request(token, `/rooms/${encodeURIComponent(roomId)}`, lang, { method: 'PUT', body: JSON.stringify(input) });
}

export function submitTradeAnswers(token: string, lang: string | null, masterName: string): Promise<PortalTradePage> {
  return request(token, '/submit', lang, { method: 'POST', body: JSON.stringify({ master_name: masterName }) });
}
