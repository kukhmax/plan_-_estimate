import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  applyPlannedDates,
  cancelReminder,
  createReminder,
  fetchAgenda,
  fetchCalendarSettings,
  fetchSchedule,
  listReminders,
  saveCalendarSettings,
  setPlannedDate,
  suggestDates,
} from './calendar';

const fetchMock = vi.fn();

function answer(body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => body });
}

const last = () => {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [string, RequestInit | undefined];
  return { url, method: init?.method ?? 'GET', body: init?.body ? JSON.parse(init.body as string) : undefined };
};

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  localStorage.setItem('access_token', 'token');
});
afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('calendar API', () => {
  it('asks for the agenda with the period and the object when given', async () => {
    answer({});
    await fetchAgenda();
    expect(last().url).toBe('/api/calendar');
    answer({});
    await fetchAgenda({ start: '2026-10-12', end: '2026-10-20', projectId: 'p 1' });
    expect(last().url).toBe('/api/calendar?start=2026-10-12&end=2026-10-20&project_id=p+1');
  });

  it('reads and saves the settings', async () => {
    answer({});
    await fetchCalendarSettings();
    expect(last()).toMatchObject({ url: '/api/calendar/settings', method: 'GET' });
    answer({});
    const body = { timezone: 'Europe/Warsaw', enabled: true, kind_overrides: {}, quiet_from: '21:00', quiet_to: '07:00', digest_at: '08:00', language: null } as const;
    await saveCalendarSettings(body);
    expect(last()).toMatchObject({ url: '/api/calendar/settings', method: 'PUT', body });
  });

  it('lists the waiting reminders of an object (the items of the answer)', async () => {
    answer({ items: [{ id: 'r1' }], total: 1 });
    expect(await listReminders('p-1')).toEqual([{ id: 'r1' }]);
    expect(last().url).toBe('/api/calendar/reminders?project_id=p-1');
    answer({ items: [], total: 0 });
    await listReminders();
    expect(last().url).toBe('/api/calendar/reminders');
  });

  it('creates a reminder by a preset and cancels one', async () => {
    answer({ id: 'r1' });
    await createReminder({ preset: 'CUSTOM', title: 'x', local_date: '2026-10-20', local_time: '09:00', occurrence_key: 'k' });
    expect(last()).toMatchObject({ url: '/api/calendar/reminders', method: 'POST', body: { preset: 'CUSTOM', local_date: '2026-10-20', local_time: '09:00', occurrence_key: 'k' } });
    answer({ id: 'r1' });
    await cancelReminder('r 1');
    expect(last()).toMatchObject({ url: '/api/calendar/reminders/r%201', method: 'DELETE' });
  });

  it('reads, sets and clears a planned date, proposes and applies dates', async () => {
    answer({});
    await fetchSchedule('p-1');
    expect(last().url).toBe('/api/projects/p-1/schedule');
    answer({});
    await setPlannedDate('p-1', 'k-1', '2026-10-20');
    expect(last()).toMatchObject({ url: '/api/projects/p-1/schedule/k-1', method: 'PUT', body: { planned_date: '2026-10-20' } });
    answer({});
    await setPlannedDate('p-1', 'k-1', null);
    expect(last().body).toEqual({ planned_date: null });
    answer([]);
    await suggestDates('p-1', '2026-10-20', 'room-1');
    expect(last()).toMatchObject({ url: '/api/projects/p-1/schedule/suggest', method: 'POST', body: { start: '2026-10-20', room_id: 'room-1' } });
    answer({});
    await applyPlannedDates('p-1', [{ occurrence_key: 'k-1', planned_date: '2026-10-20' }]);
    expect(last()).toMatchObject({ url: '/api/projects/p-1/schedule/apply', method: 'POST', body: { dates: [{ occurrence_key: 'k-1', planned_date: '2026-10-20' }] } });
  });
});
