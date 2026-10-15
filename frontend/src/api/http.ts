import { reportNetworkFailure, reportNetworkSuccess, reportServedFromCache } from '../offline/connection';
import { isCacheablePath } from '../offline/cacheRules';
import { loadRead, saveRead } from '../offline/readCache';

export const API_BASE = import.meta.env.VITE_API_URL ?? '';

// Map stable FastAPI domain-detail phrases without weakening backend validation.
const DOMAIN_ERROR_PATTERNS: Array<{ pattern: RegExp; code: string }> = [
  {
    pattern: /reveal work belongs under an opening/i,
    code: 'reveal_work_requires_opening',
  },
  {
    pattern: /(?:total opening deductions|restoring opening with deduction)[\s\S]*would exceed wall gross area/i,
    code: 'openings_deductions_exceed_gross',
  },
  {
    // Room size corrected below what the openings of a generated wall need (422).
    pattern: /new room size would make .* smaller than its openings/i,
    code: 'room_resize_exceeds_openings',
  },
  {
    pattern: /openings can only be attached to wall surfaces/i,
    code: 'openings_require_wall_surface',
  },
  {
    // Stage 13H.3: execution mutation on an archived project/room/surface (422).
    pattern: /execution cannot change on an archived project, room or surface/i,
    code: 'execution_archived',
  },
];

export function domainErrorCodeFromMessage(message: string): string | undefined {
  for (const entry of DOMAIN_ERROR_PATTERNS) {
    if (entry.pattern.test(message)) return entry.code;
  }
  return undefined;
}

function readDetail(payload: unknown): unknown {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    return payload.detail;
  }
  return null;
}

/** FastAPI/Pydantic 422s carry `detail` as an array of {loc, msg, type} items. */
function formatArrayMessage(detail: unknown[]): string {
  const messages = detail
    .map((item): string | null => {
      if (!item || typeof item !== 'object') return null;
      const { loc, msg } = item as { loc?: unknown; msg?: unknown };
      if (typeof msg !== 'string') return null;
      const path = Array.isArray(loc)
        ? loc.filter((segment): segment is string => typeof segment === 'string').join('.')
        : '';
      return path ? `${path}: ${msg}` : msg;
    })
    .filter((message): message is string => typeof message === 'string' && message.length > 0);
  return messages.join('; ');
}

// ApiError carries a stable domain code when the backend detail is recognized:
// a structured `{code, message, ...}` detail supplies it directly; a plain
// string detail may map to one through DOMAIN_ERROR_PATTERNS. `detail` keeps
// the raw structured payload (e.g. Stage 13H conflict data) for typed parsers.
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly detail?: unknown;

  constructor(message: string, status: number, code?: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

function structuredCode(detail: unknown): string | undefined {
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'code' in detail) {
    const { code } = detail as { code?: unknown };
    return typeof code === 'string' ? code : undefined;
  }
  return undefined;
}

function errorMessage(payload: unknown, status: number): string {
  const detail = readDetail(payload);
  if (typeof detail === 'string') return detail;
  if (
    detail && typeof detail === 'object' && !Array.isArray(detail) &&
    'message' in detail && typeof detail.message === 'string'
  ) {
    return detail.message;
  }
  if (Array.isArray(detail)) {
    const formatted = formatArrayMessage(detail);
    if (formatted) return formatted;
  }
  return `Request failed (${status})`;
}

/** A read of the cached kinds that gets no answer in this time is given up: the saved copy (if any) is shown instead (Stage 19B). */
export const READ_TIMEOUT_MS = 12_000;

/** `fetch` rejects with a `TypeError` when the network cannot be reached (no signal, a refused connection). */
function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError;
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = localStorage.getItem('access_token');
  const method = (init.method ?? 'GET').toUpperCase();
  const cacheable = method === 'GET' && isCacheablePath(path);

  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let controller: AbortController | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let timedOut = false;
  if (cacheable && !init.signal) {
    controller = new AbortController();
    timer = setTimeout(() => {
      timedOut = true;
      controller?.abort();
    }, READ_TIMEOUT_MS);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, controller ? { ...init, headers, signal: controller.signal } : { ...init, headers });
  } catch (error) {
    clearTimeout(timer);
    if (timedOut || isNetworkError(error)) {
      reportNetworkFailure();
      if (cacheable) {
        const saved = await loadRead(path);
        if (saved) {
          reportServedFromCache(saved.savedAt);
          return saved.data as T;
        }
      }
    }
    throw error;
  }
  clearTimeout(timer);
  reportNetworkSuccess();
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail = readDetail(payload);
    const code = typeof detail === 'string' ? domainErrorCodeFromMessage(detail) : structuredCode(detail);
    throw new ApiError(errorMessage(payload, response.status), response.status, code, detail);
  }
  // 204 No Content (e.g. DELETE) has no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  const data = (await response.json()) as T;
  if (cacheable) void saveRead(path, data); // keeps its own failures (warned, never thrown)
  return data;
}
