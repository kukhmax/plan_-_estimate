const API_BASE = import.meta.env.VITE_API_URL ?? '';

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
    pattern: /openings can only be attached to wall surfaces/i,
    code: 'openings_require_wall_surface',
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

// ApiError carries a stable domain code when the backend detail is recognized.
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
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

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = localStorage.getItem('access_token');

  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail = readDetail(payload);
    const code = typeof detail === 'string' ? domainErrorCodeFromMessage(detail) : undefined;
    throw new ApiError(errorMessage(payload, response.status), response.status, code);
  }
  // 204 No Content (e.g. DELETE) has no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}
