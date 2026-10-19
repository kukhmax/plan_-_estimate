import { getConnectionState, reportNetworkFailure, reportNetworkSuccess, reportServedFromCache } from '../offline/connection';
import { isCacheablePath } from '../offline/cacheRules';
import { newId } from '../offline/ids';
import { listOps } from '../offline/outbox';
import { drainNow, getOutboxCounts } from '../offline/outboxState';
import { queueWrite } from '../offline/queueWrite';
import { loadRead, saveRead } from '../offline/readCache';
import { archivedPoolFrom, matchWrite, overlayRead, resolveFromOutbox, type ArchivedPool } from '../offline/writeRules';

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

export const ACCESS_LOST_EVENT = 'pe:access-lost';

/** Closed registration: the administrator blocked this account (or closed the registration) while the application was open. */
function announceAccessLost(code: string, detail: unknown): void {
  const contact = detail && typeof detail === 'object' && 'contact' in detail && typeof detail.contact === 'string' ? detail.contact : '';
  window.dispatchEvent(new CustomEvent(ACCESS_LOST_EVENT, { detail: { code, contact } }));
}

/** A read of the cached kinds that gets no answer in this time is given up: the saved copy (if any) is shown instead (Stage 19B). */
export const READ_TIMEOUT_MS = 12_000;
/** A write that gets no answer in this time is kept on the phone and sent later (Stage 19C); it is safe to send again. */
export const WRITE_TIMEOUT_MS = 20_000;

/** `fetch` rejects with a `TypeError` when the network cannot be reached (no signal, a refused connection). */
function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError;
}

/** The waiting changes of the owner laid over an answer (or a saved copy), so the screens show what the owner left (Stage 19C). */
async function withWaitingChanges(path: string, data: unknown): Promise<unknown> {
  if (getOutboxCounts().pending === 0) return data;
  const ops = await listOps();
  // a list that hides archived records cannot give a waiting "restore" its record: the saved list that shows them does
  let archived: ArchivedPool | undefined;
  if (!path.includes('?') && ops.some((op) => op.status === 'pending' && op.kind.endsWith('.restore'))) {
    archived = archivedPoolFrom((await loadRead(`${path}?include_archived=true`))?.data);
  }
  return overlayRead(path, data, ops, archived);
}

/** A saved copy (with the waiting changes laid over it), or the record the phone made itself; `null` when the phone knows nothing. */
async function readFromPhone(path: string): Promise<{ value: unknown } | null> {
  const saved = await loadRead(path);
  if (saved) {
    reportServedFromCache(saved.savedAt);
    return { value: await withWaitingChanges(path, saved.data) };
  }
  if (getOutboxCounts().pending > 0) {
    const made = resolveFromOutbox(path, await listOps());
    if (made !== undefined) return { value: made };
  }
  return null;
}

/**
 * A write that cannot be kept on the phone (an estimate, a contract, closing an inspection …) acts on what the server holds. While
 * changes made without a signal still wait, it would act on stale data (an estimate without the room just measured, an inspection closed
 * before its answers arrived): so the waiting changes are sent first, and the request goes on only when nothing waits any more.
 */
async function ensureEarlierChangesSent(): Promise<void> {
  if (getOutboxCounts().pending === 0) return;
  if (!getConnectionState().offline) await drainNow();
  const waiting = getOutboxCounts().pending;
  if (waiting > 0) throw new ApiError(`${waiting} change(s) made earlier are still waiting to be sent`, 0, 'CHANGES_WAITING', { waiting });
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = localStorage.getItem('access_token');
  const method = (init.method ?? 'GET').toUpperCase();
  const cacheable = method === 'GET' && isCacheablePath(path);
  // a write of the kinds that can be made without a signal (Stage 19C)
  const write = method === 'GET' ? null : matchWrite(method, path);
  let requestBody = init.body;
  let writeBody: Record<string, unknown> | null = null;
  if (write && typeof init.body === 'string') {
    try {
      const parsed: unknown = JSON.parse(init.body);
      if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
        writeBody = parsed as Record<string, unknown>;
        if (write.action === 'create' && writeBody.id === undefined) {
          // the id is chosen here, so that sending the same request again (after a lost answer) is safe
          writeBody = { ...writeBody, id: newId() };
          requestBody = JSON.stringify(writeBody);
        }
        if (write.action === 'transition' && writeBody.recorded_at === undefined) {
          // the moment of the tap goes with the status, so that a status marked without a signal is recorded when it was made
          writeBody = { ...writeBody, recorded_at: new Date().toISOString() };
          requestBody = JSON.stringify(writeBody);
        }
      }
    } catch {
      writeBody = null; // not JSON: sent as it is, never kept
    }
  }
  if (method !== 'GET' && !write) await ensureEarlierChangesSent();
  const keepable = write !== null && (write.action === 'delete' || write.action === 'archive' || write.action === 'restore' || writeBody !== null);

  if (requestBody && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  // while the server cannot be reached, or older changes are still waiting, a new change goes behind them (the order is kept)
  if (write && keepable && (getConnectionState().offline || getOutboxCounts().pending > 0)) {
    const kept = await queueWrite(write, method as 'POST' | 'PUT' | 'PATCH' | 'DELETE', path, writeBody);
    if (kept) return kept.result as T;
  }

  // the server is known to be out of reach: a read is answered from the phone at once, not after a wait for a hanging request
  // (the connection watch looks at the server every 15 s and puts things right when the signal is back)
  if (cacheable && getConnectionState().offline) {
    const kept = await readFromPhone(path);
    if (kept) return kept.value as T;
  }

  let controller: AbortController | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let timedOut = false;
  if ((cacheable || write) && !init.signal) {
    controller = new AbortController();
    timer = setTimeout(() => {
      timedOut = true;
      controller?.abort();
    }, write ? WRITE_TIMEOUT_MS : READ_TIMEOUT_MS);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, body: requestBody, headers, ...(controller ? { signal: controller.signal } : {}) });
  } catch (error) {
    clearTimeout(timer);
    if (timedOut || isNetworkError(error)) {
      reportNetworkFailure();
      if (cacheable) {
        const kept = await readFromPhone(path);
        if (kept) return kept.value as T;
      }
      if (write && keepable) {
        const kept = await queueWrite(write, method as 'POST' | 'PUT' | 'PATCH' | 'DELETE', path, writeBody);
        if (kept) return kept.result as T;
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
    if (response.status === 403 && (code === 'ACCESS_DENIED' || code === 'ACCESS_BLOCKED')) announceAccessLost(code, detail);
    throw new ApiError(errorMessage(payload, response.status), response.status, code, detail);
  }
  // 204 No Content (e.g. DELETE) has no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  const data = (await response.json()) as T;
  if (cacheable) {
    void saveRead(path, data); // the copy is what the server said; the waiting changes are laid over it when it is read
    return (await withWaitingChanges(path, data)) as T;
  }
  return data;
}
