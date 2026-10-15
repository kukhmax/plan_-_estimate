/** Stage 18E -- the calendar side of the card of a work: the planned date, its warning, the Remind button, the proposal of dates. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as calendarApi from './api/calendar';
import * as workPlansApi from './api/workPlans';
import { SurfaceExecutionView } from './components/SurfaceExecutionView';
import { I18nProvider } from './hooks/useI18n';
import type { Reminder, Schedule } from './types/calendar';
import type { PlannedWorkExecutionRead, SurfacePlannedWorkRead, SurfacePriceItemSummaryRead, SurfaceWorkPlanRead } from './types/workPlan';

vi.mock('./api/workPlans', async (importOriginal) => ({ ...(await importOriginal<typeof import('./api/workPlans')>()), fetchSurfaceWorkPlan: vi.fn(), transitionWorkExecution: vi.fn() }));
vi.mock('./api/calendar', () => ({
  fetchSchedule: vi.fn(), listReminders: vi.fn(), setPlannedDate: vi.fn(), createReminder: vi.fn(), cancelReminder: vi.fn(), suggestDates: vi.fn(), applyPlannedDates: vi.fn(),
}));

const NS: PlannedWorkExecutionRead = { status: 'NOT_STARTED', started_at: null, completed_at: null, ready_after: null };
const DONE: PlannedWorkExecutionRead = { status: 'COMPLETED', started_at: '2026-10-12T08:00:00Z', completed_at: '2026-10-12T10:00:00Z', ready_after: '2026-10-13T10:00:00Z' };

function item(id: string, name: string): SurfacePriceItemSummaryRead {
  return { id, code: id.toUpperCase(), name_key: null, display_name: name, category: 'SKIM_COAT', unit: 'M2', price_scope: 'LABOR', price: '10.00', currency: 'PLN', is_archived: false, quality_level: null };
}
function work(key: string, position: number, name: string, execution = NS, wait: number | null = null): SurfacePlannedWorkRead {
  return { id: `row-${key}`, work_plan_id: 'plan', price_item_id: key, position, occurrence_key: key, wait_after_hours: wait, price_item: item(key, name), coefficient_options: [], execution };
}
const PLAN = (works: SurfacePlannedWorkRead[]): SurfaceWorkPlanRead => ({ id: 'plan', surface_id: 's1', substrate: 'CONCRETE', quality_target: 'S2', planned_works: works, template_applications: [] });

const EMPTY: Schedule = { planned: [], warnings: [], window_start: null, window_end: null };
const REMINDER: Reminder = { id: 'rem-1', project_id: 'p', room_id: 'r', surface_id: 's1', occurrence_key: 'k1', origin: 'USER', kind: 'USER', title: 'Zadzwonić', send_at: '2026-10-20T08:00:00Z', status: 'PENDING', close_on_status: null };

function view() {
  return render(
    <I18nProvider>
      <SurfaceExecutionView projectId="p" roomId="r" surfaceId="s1" surfaceName="Ściana A" onClose={vi.fn()} />
    </I18nProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(PLAN([work('k1', 0, 'Gruntowanie', NS, 24), work('k2', 1, 'Gładź')]));
  vi.mocked(calendarApi.fetchSchedule).mockResolvedValue(EMPTY);
  vi.mocked(calendarApi.listReminders).mockResolvedValue([]);
});

describe('the planned date', () => {
  it('shows the date of each work and the warning of the one that starts too early', async () => {
    vi.mocked(calendarApi.fetchSchedule).mockResolvedValue({
      planned: [{ occurrence_key: 'k1', planned_date: '2026-10-12' }, { occurrence_key: 'k2', planned_date: '2026-10-12' }],
      warnings: [{ occurrence_key: 'k2', code: 'BEFORE_BREAK_END', date: '2026-10-13' }], window_start: null, window_end: null,
    });
    view();
    await waitFor(() => expect(screen.getByLabelText('planned-date-k1')).toHaveValue('2026-10-12'));
    expect(screen.getByLabelText('planned-date-k2')).toHaveValue('2026-10-12');
    expect(screen.getByLabelText('schedule-warning-k2')).toHaveTextContent('Wcześniej niż koniec przerwy poprzedniej pracy');
    expect(screen.queryByLabelText('schedule-warning-k1')).toBeNull();
  });

  it('saves a chosen date for that work and shows the warnings the server returns', async () => {
    vi.mocked(calendarApi.setPlannedDate).mockResolvedValue({
      planned: [{ occurrence_key: 'k2', planned_date: '2026-10-12' }], warnings: [{ occurrence_key: 'k2', code: 'BEFORE_CONTRACT_START', date: '2026-10-20' }], window_start: '2026-10-20', window_end: null,
    });
    view();
    const input = await screen.findByLabelText('planned-date-k2');
    fireEvent.change(input, { target: { value: '2026-10-12' } });
    await waitFor(() => expect(calendarApi.setPlannedDate).toHaveBeenCalledWith('p', 'k2', '2026-10-12'));
    expect(await screen.findByLabelText('schedule-warning-k2')).toHaveTextContent('Przed początkiem prac z umowy');
  });

  it('does not ask for a date of a work that is done', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(PLAN([work('k1', 0, 'Gruntowanie', DONE, 24)]));
    view();
    await screen.findByLabelText('remind-k1');
    expect(screen.queryByLabelText('planned-date-k1')).toBeNull();
  });
});

describe('the Remind button', () => {
  it('offers the end of the break only for a work that is done, and the day of the work only with a planned date', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(PLAN([work('k1', 0, 'Gruntowanie', DONE, 24), work('k2', 1, 'Gładź')]));
    vi.mocked(calendarApi.fetchSchedule).mockResolvedValue({ planned: [{ occurrence_key: 'k2', planned_date: '2026-10-20' }], warnings: [], window_start: null, window_end: null });
    view();
    await screen.findByLabelText('remind-k1');
    fireEvent.click(screen.getByLabelText('remind-k1'));
    expect(screen.getByLabelText('reminder-preset-BREAK_END')).toBeInTheDocument();
    expect(screen.queryByLabelText('reminder-preset-WORK_DAY')).toBeNull();
    fireEvent.click(screen.getByLabelText('reminder-cancel'));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(screen.getByLabelText('planned-date-k2')).toHaveValue('2026-10-20'));
    fireEvent.click(screen.getByLabelText('remind-k2'));
    expect(screen.getByLabelText('reminder-preset-WORK_DAY')).toBeInTheDocument();
    expect(screen.getByLabelText('reminder-preset-DAY_BEFORE')).toBeInTheDocument();
    expect(screen.queryByLabelText('reminder-preset-BREAK_END')).toBeNull();
  });

  it('makes a reminder about this work with its place and its name, then reads the reminders again and shows the chip', async () => {
    vi.mocked(calendarApi.createReminder).mockResolvedValue(REMINDER);
    view();
    fireEvent.click(await screen.findByLabelText('remind-k1'));
    fireEvent.click(screen.getByLabelText('reminder-preset-TOMORROW'));
    vi.mocked(calendarApi.listReminders).mockResolvedValue([REMINDER]);
    fireEvent.click(screen.getByLabelText('reminder-save'));
    await waitFor(() => expect(calendarApi.createReminder).toHaveBeenCalledWith({
      preset: 'TOMORROW', title: 'Gruntowanie — Ściana A', project_id: 'p', room_id: 'r', surface_id: 's1', occurrence_key: 'k1',
    }));
    expect(await screen.findByLabelText('reminder-chips-k1')).toHaveTextContent('🔔');
    expect(screen.queryByLabelText('reminder-chips-k2')).toBeNull();
  });

  it('shows the reminders of the work in the sheet and removes one', async () => {
    vi.mocked(calendarApi.listReminders).mockResolvedValue([REMINDER]);
    vi.mocked(calendarApi.cancelReminder).mockResolvedValue({ ...REMINDER, status: 'CANCELLED' });
    view();
    fireEvent.click(await screen.findByLabelText('remind-k1'));
    expect(screen.getByLabelText('reminder-existing')).toHaveTextContent('Zadzwonić');
    fireEvent.click(screen.getByLabelText('reminder-remove-rem-1'));
    await waitFor(() => expect(calendarApi.cancelReminder).toHaveBeenCalledWith('rem-1'));
  });
});

describe('the calendar follows the status', () => {
  it('reads the calendar again after a work is completed', async () => {
    vi.mocked(workPlansApi.transitionWorkExecution).mockResolvedValue({ occurrence_key: 'k1', ...DONE });
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(PLAN([work('k1', 0, 'Gruntowanie', { ...NS, status: 'IN_PROGRESS', started_at: '2026-10-12T08:00:00Z' }, 24)]));
    view();
    await screen.findByLabelText('execution-complete-k1');
    const before = vi.mocked(calendarApi.fetchSchedule).mock.calls.length;
    fireEvent.click(screen.getByLabelText('execution-complete-k1'));
    await waitFor(() => expect(vi.mocked(calendarApi.fetchSchedule).mock.calls.length).toBeGreaterThan(before));
    expect(vi.mocked(calendarApi.listReminders).mock.calls.length).toBeGreaterThan(1);
  });

  it('keeps the card working when the calendar cannot be read', async () => {
    vi.mocked(calendarApi.fetchSchedule).mockRejectedValue(new Error('down'));
    vi.mocked(calendarApi.listReminders).mockRejectedValue(new Error('down'));
    view();
    const list = await screen.findByLabelText('execution-works-s1');
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByLabelText('execution-start-k1')).toBeInTheDocument();
    expect(screen.getByLabelText('planned-date-k1')).toHaveValue('');
  });
});

describe('the proposal of dates', () => {
  it('is offered for a plan with works, proposes for the room and fills the dates when accepted', async () => {
    vi.mocked(calendarApi.suggestDates).mockResolvedValue([{ occurrence_key: 'k1', planned_date: '2026-10-12' }, { occurrence_key: 'k2', planned_date: '2026-10-13' }]);
    const saved: Schedule = { planned: [{ occurrence_key: 'k1', planned_date: '2026-10-12' }, { occurrence_key: 'k2', planned_date: '2026-10-13' }], warnings: [], window_start: null, window_end: null };
    vi.mocked(calendarApi.applyPlannedDates).mockImplementation(async () => {
      vi.mocked(calendarApi.fetchSchedule).mockResolvedValue(saved); // from now on the server has the dates
      return saved;
    });
    view();
    fireEvent.click(await screen.findByLabelText('schedule-suggest-open-s1'));
    fireEvent.click(screen.getByLabelText('suggest-show'));
    expect(await screen.findByLabelText('suggest-proposal')).toHaveTextContent('Gruntowanie');
    expect(calendarApi.suggestDates).toHaveBeenCalledWith('p', expect.any(String), 'r');
    fireEvent.click(screen.getByLabelText('suggest-apply'));
    await waitFor(() => expect(calendarApi.applyPlannedDates).toHaveBeenCalledWith('p', expect.arrayContaining([{ occurrence_key: 'k2', planned_date: '2026-10-13' }])));
    await waitFor(() => expect(screen.getByLabelText('planned-date-k2')).toHaveValue('2026-10-13'));
  });

  it('is not offered for a surface without works', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(PLAN([]));
    view();
    await screen.findByLabelText('close-execution-bottom-s1');
    expect(screen.queryByLabelText('schedule-suggest-open-s1')).toBeNull();
  });
});
