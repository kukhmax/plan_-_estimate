import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchArchivedPayments, fetchPaymentPurgePreview, purgePayment } from './payments';

function respond(status: number, body: unknown) {
  vi.mocked(fetch).mockResolvedValueOnce({ ok: status < 400, status, json: vi.fn().mockResolvedValue(body) } as unknown as Response);
}
const lastCall = () => {
  const calls = vi.mocked(fetch).mock.calls;
  const [url, init] = calls[calls.length - 1] as [string, RequestInit | undefined];
  return { url, init: init ?? {} };
};

describe('payments API: the archive of the records (IA-7)', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'tok');
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('reads the archived records of all objects', async () => {
    respond(200, { items: [], total: 0 });
    await fetchArchivedPayments();
    const call = lastCall();
    expect(call.url).toBe('/api/archive/payments');
    expect(call.init.method ?? 'GET').toBe('GET');
  });

  it('asks the server what a deletion would remove, with a GET and no body', async () => {
    respond(200, {});
    await fetchPaymentPurgePreview('p1', 'r1');
    const call = lastCall();
    expect(call.url).toBe('/api/projects/p1/payments/r1/purge-preview');
    expect(call.init.method ?? 'GET').toBe('GET');
    expect(call.init.body).toBeUndefined();
  });

  it('deletes with a POST (never a GET) on the route of the record', async () => {
    respond(200, { purged: true, photo_files: 0, storage_pending: 0 });
    await purgePayment('p1', 'r1');
    const call = lastCall();
    expect(call.url).toBe('/api/projects/p1/payments/r1/purge');
    expect(call.init.method).toBe('POST');
  });
});
