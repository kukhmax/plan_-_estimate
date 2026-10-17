import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/calendar';
import * as projectsApi from '../api/projects';
import * as workApi from '../api/workPlans';
import { I18nProvider } from '../hooks/useI18n';
import type { Agenda, AgendaItem, AgendaWork, CalendarSettings } from '../types/calendar';
import { CalendarScreen } from './CalendarScreen';

vi.mock('../api/calendar', () => ({
  fetchAgenda: vi.fn(), cancelReminder: vi.fn(), fetchCalendarSettings: vi.fn(), saveCalendarSettings: vi.fn(), createReminder: vi.fn(),
}));
vi.mock('../api/projects', () => ({ fetchProjects: vi.fn() }));
vi.mock('../api/workPlans', async (importOriginal) => ({ ...(await importOriginal<typeof import('../api/workPlans')>()), transitionWorkExecution: vi.fn() }));

const WORK = (key: string, day: string, status: AgendaWork['status'] = 'NOT_STARTED'): AgendaWork => ({
  occurrence_key: key, planned_date: day, status, wait_after_hours: null, project_id: 'p1', project_name: 'Kowalski, ul. Kwiatowa 1',
  room_id: 'room1', room_name: 'Łazienka', surface_id: 's1', surface_name: 'Ściana A', work_name_key: null, work_display_name: 'Gładź',
});

const ITEM = (key: string, day: string, over: Partial<AgendaItem> = {}): AgendaItem => ({
  source: 'EVENT', kind: 'DELIVERY_DEADLINE', key, day, on: day, at: null, ref: '', title_key: 'calendar.event.delivery_deadline', title: null, params: {},
  sends: true, reminder_id: null, project_id: 'p1', project_name: 'Kowalski, ul. Kwiatowa 1', room_id: null, room_name: null, surface_id: null, surface_name: null,
  occurrence_key: null, ...over,
});

const AGENDA: Agenda = {
  today: '2026-10-12', start: '2026-10-12', end: '2026-12-11',
  overdue: [WORK('k-late', '2026-10-09')],
  works: [WORK('k-today', '2026-10-12', 'IN_PROGRESS'), WORK('k-later', '2026-10-14')],
  items: [
    ITEM('i-today', '2026-10-12', { kind: 'OBJECT_START', title_key: 'calendar.event.object_start' }),
    ITEM('i-break', '2026-10-13', { kind: 'BREAK_END', title_key: 'calendar.event.break_end', at: '2026-10-13T08:30:00Z', on: null, room_name: 'Łazienka', surface_name: 'Ściana A' }),
    ITEM('i-appear', '2026-10-15', { kind: 'ACCEPTANCE_TERM', title_key: 'calendar.event.acceptance_term.appearance', ref: 'appearance', sends: true }),
    ITEM('i-pay', '2026-10-16', { kind: 'PAYMENT_TERM', title_key: 'calendar.event.payment_term.advance', ref: 'advance', sends: false }),
    ITEM('i-inv', '2026-10-16', { kind: 'INVOICE_DUE', title_key: 'calendar.event.invoice_due', params: { what: 'FV 7/2026' }, sends: true }),
    ITEM('r-1', '2026-10-17', { source: 'REMINDER', kind: 'USER', title_key: null, title: 'Zadzwonić do klienta', on: null, at: '2026-10-17T07:00:00Z', reminder_id: 'rem-1' }),
  ],
};

const SETTINGS: CalendarSettings = {
  timezone: 'Europe/Warsaw', enabled: true, kind_overrides: {}, quiet_from: '21:00:00', quiet_to: '07:00:00', digest_at: '08:00:00', language: null,
  kinds: [{ kind: 'BREAK_END', default_push: true, sends: true }], timezones: ['Europe/Warsaw'],
};

function screenOf(props: Partial<React.ComponentProps<typeof CalendarScreen>> = {}) {
  const onOpenProject = vi.fn();
  render(
    <I18nProvider>
      <CalendarScreen onOpenProject={onOpenProject} {...props} />
    </I18nProvider>,
  );
  return { onOpenProject };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(api.fetchAgenda).mockResolvedValue(AGENDA);
  vi.mocked(api.fetchCalendarSettings).mockResolvedValue(SETTINGS);
  vi.mocked(api.cancelReminder).mockResolvedValue({} as never);
  vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [{ id: 'p1', name: 'Kowalski, ul. Kwiatowa 1' }, { id: 'p2', name: 'Nowak' }] as never, total: 2 });
  vi.mocked(workApi.transitionWorkExecution).mockResolvedValue({} as never);
});

describe('the sections', () => {
  it('shows the due day of an invoice with its name, in the language of the screen (IA-5)', async () => {
    screenOf();
    expect(await screen.findByLabelText('calendar-item-i-inv')).toHaveTextContent('Termin zapłaty faktury: FV 7/2026');
  });

  it('shows it in Russian too', async () => {
    localStorage.setItem('locale', 'ru');
    screenOf();
    expect(await screen.findByLabelText('calendar-item-i-inv')).toHaveTextContent('Срок оплаты фактуры: FV 7/2026');
  });

  it('puts the overdue works first, then today, then the days ahead', async () => {
    screenOf();
    const overdue = await screen.findByLabelText('calendar-overdue');
    expect(overdue).toHaveTextContent('Zaległe (1)');
    expect(within(overdue).getByLabelText('calendar-work-k-late')).toHaveTextContent('Gładź');
    const today = screen.getByLabelText('calendar-today');
    expect(within(today).getByLabelText('calendar-work-k-today')).toBeInTheDocument();
    expect(within(today).getByLabelText('calendar-item-i-today')).toHaveTextContent('Rozpoczęcie prac na obiekcie (wg umowy)');
    const order = ['calendar-overdue', 'calendar-today', 'calendar-upcoming'].map((name) => screen.getByLabelText(name));
    expect(order[0].compareDocumentPosition(order[1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(order[1].compareDocumentPosition(order[2]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('groups the days ahead, with the works of that day, the time of an event in the owners zone and whether it sends a message', async () => {
    screenOf();
    const day = await screen.findByLabelText('calendar-day-2026-10-13');
    expect(within(day).getByLabelText('calendar-item-i-break')).toHaveTextContent('10:30'); // 08:30 UTC = 10:30 in Warsaw (summer time)
    expect(within(day).getByLabelText('calendar-item-i-break')).toHaveTextContent('Łazienka · Ściana A');
    expect(within(day).getByLabelText('calendar-item-i-break')).toHaveTextContent('wysyła wiadomość');
    expect(within(screen.getByLabelText('calendar-day-2026-10-16')).getByLabelText('calendar-item-i-pay')).toHaveTextContent('tylko w kalendarzu');
    expect(within(screen.getByLabelText('calendar-day-2026-10-14')).getByLabelText('calendar-work-k-later')).toBeInTheDocument();
    expect(screen.getByLabelText('calendar-item-i-appear')).toHaveTextContent('Upływa termin stawienia się Zamawiającego do odbioru (§ 14)');
  });

  it('shows today once, in its own section, and not again among the days ahead', async () => {
    screenOf();
    await screen.findByLabelText('calendar-today');
    expect(screen.queryByLabelText('calendar-day-2026-10-12')).toBeNull();
    expect(screen.getAllByLabelText('calendar-work-k-today')).toHaveLength(1);
    expect(screen.getAllByLabelText('calendar-item-i-today')).toHaveLength(1);
  });

  it('offers to remove only the own reminders, never an event derived from the data', async () => {
    screenOf();
    await screen.findByLabelText('calendar-today');
    expect(screen.getByLabelText('calendar-remove-r-1')).toBeInTheDocument();
    for (const key of ['i-today', 'i-break', 'i-appear', 'i-pay']) expect(screen.queryByLabelText(`calendar-remove-${key}`)).toBeNull();
  });

  it('shows an own reminder with its words and the bell', async () => {
    screenOf();
    expect(await screen.findByLabelText('calendar-item-r-1')).toHaveTextContent('🔔');
    expect(screen.getByLabelText('calendar-item-r-1')).toHaveTextContent('Zadzwonić do klienta');
  });

  it('says so when nothing is planned', async () => {
    vi.mocked(api.fetchAgenda).mockResolvedValue({ ...AGENDA, overdue: [], works: [], items: [] });
    screenOf();
    expect(await screen.findByText('Na dziś nic nie zaplanowano.')).toBeInTheDocument();
    expect(screen.getByText('Brak zdarzeń w tym okresie.')).toBeInTheDocument();
    expect(screen.queryByLabelText('calendar-overdue')).toBeNull();
  });

  it('is in Russian when the application is', async () => {
    localStorage.setItem('locale', 'ru');
    screenOf();
    expect(await screen.findByLabelText('calendar-overdue')).toHaveTextContent('Просрочено (1)');
    expect(screen.getByLabelText('calendar-item-i-break')).toHaveTextContent('Технологический перерыв закончился — можно продолжать работы');
    expect(screen.getByLabelText('calendar-item-i-pay')).toHaveTextContent('только в календаре');
  });
});

describe('marking a work from the list', () => {
  it('starts a work that is not started, with the status the owner saw, and reads the agenda again', async () => {
    screenOf();
    await screen.findByLabelText('calendar-overdue');
    fireEvent.click(screen.getByLabelText('calendar-start-k-late'));
    await waitFor(() => expect(workApi.transitionWorkExecution).toHaveBeenCalledWith('p1', 'room1', 's1', 'k-late', { status: 'IN_PROGRESS', expected_status: 'NOT_STARTED' }));
    await waitFor(() => expect(api.fetchAgenda).toHaveBeenCalledTimes(2));
  });

  it('completes a work in progress with one press, and a not started one can be completed at once', async () => {
    screenOf();
    await screen.findByLabelText('calendar-today');
    fireEvent.click(screen.getByLabelText('calendar-done-k-today'));
    await waitFor(() => expect(workApi.transitionWorkExecution).toHaveBeenCalledWith('p1', 'room1', 's1', 'k-today', { status: 'COMPLETED', expected_status: 'IN_PROGRESS' }));
    expect(screen.queryByLabelText('calendar-start-k-today')).toBeNull(); // already in progress: no "start"
    fireEvent.click(screen.getByLabelText('calendar-done-k-late'));
    await waitFor(() => expect(workApi.transitionWorkExecution).toHaveBeenCalledWith('p1', 'room1', 's1', 'k-late', { status: 'COMPLETED', expected_status: 'NOT_STARTED' }));
  });

  it('has no buttons on the works of the days ahead (they are marked when their day comes)', async () => {
    screenOf();
    const later = await screen.findByLabelText('calendar-work-k-later');
    expect(within(later).queryAllByRole('button')).toHaveLength(0);
  });

  it('says it when the status could not be changed, and keeps the list', async () => {
    vi.mocked(workApi.transitionWorkExecution).mockRejectedValueOnce(new Error('409'));
    screenOf();
    await screen.findByLabelText('calendar-overdue');
    fireEvent.click(screen.getByLabelText('calendar-done-k-late'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się zmienić statusu pracy.');
    expect(screen.getByLabelText('calendar-work-k-late')).toBeInTheDocument();
  });

  it('keeps the buttons at least 44 px tall', async () => {
    screenOf();
    await screen.findByLabelText('calendar-overdue');
    for (const name of ['calendar-start-k-late', 'calendar-done-k-late', 'calendar-add-reminder', 'calendar-open-settings']) {
      expect(screen.getByLabelText(name).className).toContain('min-h-11');
    }
  });
});

describe('the filter, the reminders, the settings', () => {
  it('reads the agenda of one object when it is chosen', async () => {
    screenOf();
    await screen.findByLabelText('calendar-today');
    await waitFor(() => expect(screen.getByLabelText('calendar-project-filter')).toHaveTextContent('Nowak'));
    fireEvent.change(screen.getByLabelText('calendar-project-filter'), { target: { value: 'p2' } });
    await waitFor(() => expect(api.fetchAgenda).toHaveBeenLastCalledWith({ projectId: 'p2' }));
  });

  it('removes an own reminder and reads the agenda again', async () => {
    screenOf();
    fireEvent.click(await screen.findByLabelText('calendar-remove-r-1'));
    await waitFor(() => expect(api.cancelReminder).toHaveBeenCalledWith('rem-1'));
    await waitFor(() => expect(api.fetchAgenda).toHaveBeenCalledTimes(2));
  });

  it('opens the object of a line', async () => {
    const { onOpenProject } = screenOf();
    fireEvent.click(await screen.findByLabelText('calendar-open-i-break'));
    expect(onOpenProject).toHaveBeenCalledWith('p1');
  });

  it('opens the Remind sheet without a work', async () => {
    screenOf();
    fireEvent.click(await screen.findByLabelText('calendar-add-reminder'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(4);
  });

  it('opens the settings and comes back', async () => {
    screenOf();
    fireEvent.click(await screen.findByLabelText('calendar-open-settings'));
    expect(await screen.findByLabelText('calendar-settings-form')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('calendar-settings-back'));
    expect(await screen.findByLabelText('calendar-section')).toBeInTheDocument();
  });

  it('shows a retry when the agenda cannot be read', async () => {
    vi.mocked(api.fetchAgenda).mockRejectedValueOnce(new Error('down'));
    screenOf();
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać kalendarza.');
    await act(async () => {
      fireEvent.click(screen.getByLabelText('calendar-retry'));
    });
    expect(await screen.findByLabelText('calendar-today')).toBeInTheDocument();
  });
});
