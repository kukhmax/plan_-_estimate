/** Stage 18E -- the calendar in the application: the menu, and the address a reminder message opens (`?open=...`). */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import * as authApi from './api/auth';
import * as calendarApi from './api/calendar';
import * as projectsApi from './api/projects';
import { chooseSection } from './test/menu';

vi.mock('./api/auth', async () => ({ ...(await vi.importActual<typeof import('./api/auth')>('./api/auth')), loginWithTelegram: vi.fn(), fetchCurrentUser: vi.fn() }));
vi.mock('./api/clients', () => ({ fetchClients: vi.fn().mockResolvedValue({ items: [], total: 0 }), createClient: vi.fn(), archiveClient: vi.fn(), restoreClient: vi.fn() }));
vi.mock('./api/projects', () => ({
  fetchProject: vi.fn(), fetchProjects: vi.fn(), createProject: vi.fn(), updateProject: vi.fn(), archiveProject: vi.fn(), restoreProject: vi.fn(),
}));
vi.mock('./api/rooms', () => ({
  fetchProjectSummary: vi.fn(async () => ({
    room_count: 0, floor_area: null, ceiling_area: null, total_wall_area: null, total_deduction_area: null, net_wall_area: null,
    reveal_total_length: null, reveal_total_area: null, opening_groups: [],
  })),
  fetchRooms: vi.fn(async () => ({ items: [], total: 0 })), fetchRoom: vi.fn(), createRoom: vi.fn(), updateRoom: vi.fn(), archiveRoom: vi.fn(), restoreRoom: vi.fn(),
}));
vi.mock('./api/calendar', () => ({
  fetchAgenda: vi.fn(), fetchCalendarSettings: vi.fn(), cancelReminder: vi.fn(), saveCalendarSettings: vi.fn(), createReminder: vi.fn(),
  fetchSchedule: vi.fn(), listReminders: vi.fn(), setPlannedDate: vi.fn(), suggestDates: vi.fn(), applyPlannedDates: vi.fn(),
}));

const PROJECT_ID = '0f8fad5b-d9cb-469f-a165-70867728950e';
const PROJECT = {
  id: PROJECT_ID, name: 'Kowalski, ul. Kwiatowa 1', address: 'ul. Kwiatowa 1', city: 'Kraków', postal_code: '30-001', client_id: null, status: 'DRAFT',
  is_archived: false, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
};

function signIn() {
  vi.mocked(authApi.loginWithTelegram).mockResolvedValue({
    access_token: 't', token_type: 'bearer', is_dev_auth: true,
    user: { id: 'u1', telegram_user_id: 1, username: 'u', first_name: 'Jan', last_name: 'K', language_code: 'pl', created_at: '2026-09-08T12:00:00Z', updated_at: '2026-09-08T12:00:00Z' },
  });
}

function openAt(search: string) {
  window.history.pushState({}, '', `/${search}`);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllEnvs();
  vi.stubEnv('DEV', true);
  vi.stubEnv('VITE_DEV_MOCK_AUTH', 'true');
  delete (window as unknown as { Telegram?: unknown }).Telegram;
  localStorage.clear();
  signIn();
  vi.mocked(calendarApi.fetchAgenda).mockResolvedValue({ today: '2026-10-12', start: '2026-10-12', end: '2026-12-11', items: [], works: [], overdue: [] });
  vi.mocked(calendarApi.fetchCalendarSettings).mockResolvedValue({
    timezone: 'Europe/Warsaw', enabled: true, kind_overrides: {}, quiet_from: '21:00:00', quiet_to: '07:00:00', digest_at: '08:00:00', language: null, kinds: [], timezones: [],
  });
  vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [PROJECT] as never, total: 1 });
  vi.mocked(projectsApi.fetchProject).mockResolvedValue(PROJECT as never);
});

afterEach(() => {
  window.history.pushState({}, '', '/');
});

describe('the calendar section', () => {
  it('is the third item of the menu and opens the calendar', async () => {
    render(<App />);
    await chooseSection('show-calendar');
    expect(await screen.findByLabelText('calendar-section')).toBeInTheDocument();
    expect(calendarApi.fetchAgenda).toHaveBeenCalled();
  });

  it('is in Russian as "Календарь"', async () => {
    localStorage.setItem('locale', 'ru');
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'open-menu' }));
    expect(screen.getByRole('button', { name: 'show-calendar' })).toHaveTextContent('Календарь');
  });
});

describe('the address a message opens', () => {
  it('?open=calendar starts on the calendar', async () => {
    openAt('?open=calendar');
    render(<App />);
    expect(await screen.findByLabelText('calendar-section')).toBeInTheDocument();
  });

  it('?open=project:<id> starts on the object and reads it', async () => {
    openAt(`?open=project:${PROJECT_ID}`);
    render(<App />);
    await waitFor(() => expect(projectsApi.fetchProject).toHaveBeenCalledWith(PROJECT_ID));
    expect(await screen.findByText('Podsumowanie obiektu')).toBeInTheDocument(); // the screen of the object, not the list
    expect(screen.queryByLabelText('calendar-section')).toBeNull();
  });

  it.each(['?open=nothing', '?open=project:not-an-id', '?open=project:', '', '?other=calendar'])('does not guess from %s: it starts where it always did', async (search) => {
    openAt(search);
    render(<App />);
    await screen.findByRole('button', { name: 'open-menu' });
    expect(screen.queryByLabelText('calendar-section')).toBeNull();
    expect(projectsApi.fetchProject).not.toHaveBeenCalled();
  });
});
