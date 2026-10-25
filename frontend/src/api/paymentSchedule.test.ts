import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createHours, createStage, deleteHours, deleteStage, fetchHours, fetchMargin, fetchSchedule, receiveStage, updateHours, updateStage,
} from './paymentSchedule';

// V2-9 — the routes of the schedule, the hours and the margin: addresses, methods and bodies.

function respond(status: number, body: unknown = {}) {
  vi.mocked(fetch).mockResolvedValueOnce({ ok: status < 400, status, json: vi.fn().mockResolvedValue(body) } as unknown as Response);
}
const last = () => {
  const calls = vi.mocked(fetch).mock.calls;
  const [url, init] = calls[calls.length - 1] ?? [];
  return { url: String(url), init: init as RequestInit };
};

describe('payment schedule API', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reads the schedule and creates, changes and deletes a stage', async () => {
    respond(200, { items: [], summary: {} });
    await fetchSchedule('p1');
    expect(last().url).toBe('/api/projects/p1/payment-stages');
    respond(201, {});
    await createStage('p1', { title: 'Zaliczka', percent: '30', due_on: null });
    expect(last().url).toBe('/api/projects/p1/payment-stages');
    expect(last().init.method).toBe('POST');
    expect(JSON.parse(String(last().init.body))).toEqual({ title: 'Zaliczka', percent: '30', due_on: null });
    respond(200, {});
    await updateStage('p1', 's1', { amount: '1500' });
    expect(last().url).toBe('/api/projects/p1/payment-stages/s1');
    expect(last().init.method).toBe('PATCH');
    expect(JSON.parse(String(last().init.body))).toEqual({ amount: '1500' });
    respond(204);
    await expect(deleteStage('p1', 's1')).resolves.toBeUndefined();
    expect(last().init.method).toBe('DELETE');
  });

  it('books the rest of a stage with a POST and no body', async () => {
    respond(201, { id: 'x' });
    await receiveStage('p1', 's1');
    expect(last().url).toBe('/api/projects/p1/payment-stages/s1/receive');
    expect(last().init.method).toBe('POST');
    expect(last().init.body).toBeUndefined();
  });

  it('reads, adds, changes and deletes hours', async () => {
    respond(200, { items: [], total_hours: '0.00', hourly_rate: null });
    await fetchHours('p1');
    expect(last().url).toBe('/api/projects/p1/work-hours');
    respond(201, {});
    await createHours('p1', { worked_on: '2026-10-28', hours: '7.5', note: null });
    expect(JSON.parse(String(last().init.body))).toEqual({ worked_on: '2026-10-28', hours: '7.5', note: null });
    respond(200, {});
    await updateHours('p1', 'h1', { hours: '8' });
    expect(last().url).toBe('/api/projects/p1/work-hours/h1');
    expect(last().init.method).toBe('PATCH');
    respond(204);
    await deleteHours('p1', 'h1');
    expect(last().url).toBe('/api/projects/p1/work-hours/h1');
    expect(last().init.method).toBe('DELETE');
  });

  it('reads the margin', async () => {
    respond(200, {});
    await fetchMargin('p1');
    expect(last().url).toBe('/api/projects/p1/margin');
  });
});
