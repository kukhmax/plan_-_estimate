/**
 * Stage 13H.5 — Realizacja (execution) view: rendering, immediate transitions
 * with expected_status, server-truth updates, conflict refresh without retry,
 * generic errors, empty states, PL/RU, touch targets and theme-safe styling.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api/http';
import * as workPlansApi from './api/workPlans';
import { SurfaceExecutionView } from './components/SurfaceExecutionView';
import { I18nProvider } from './hooks/useI18n';
import {
  PlannedWorkExecutionRead,
  SurfacePlannedWorkRead,
  SurfacePriceItemSummaryRead,
  SurfaceWorkExecutionRead,
  SurfaceWorkPlanRead,
} from './types/workPlan';
import { formatRecordedDateTime } from './utils/executionFormat';

vi.mock('./api/workPlans', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workPlans')>();
  return { ...actual, fetchSurfaceWorkPlan: vi.fn(), transitionWorkExecution: vi.fn() };
});

const S = 's-1';
const NS: PlannedWorkExecutionRead = { status: 'NOT_STARTED', started_at: null, completed_at: null, ready_after: null };
const STARTED = '2026-09-27T08:00:00Z';
const DONE = '2026-09-27T10:00:00Z';
const READY = '2026-09-28T10:00:00Z';

function item(id: string, name: string | null, nameKey: string | null = null): SurfacePriceItemSummaryRead {
  return { id, code: id.toUpperCase(), name_key: nameKey, display_name: name, category: 'SKIM_COAT', unit: 'M2',
    price_scope: 'LABOR', price: '10.00', currency: 'PLN', is_archived: false, quality_level: null };
}

function work(key: string, position: number, execution: PlannedWorkExecutionRead = NS,
  wait: number | null = null, priceItem = item('p1', 'Gładź')): SurfacePlannedWorkRead {
  return { id: `row-${key}`, work_plan_id: 'plan-1', price_item_id: priceItem.id, position, occurrence_key: key,
    wait_after_hours: wait, price_item: priceItem, coefficient_options: [], execution };
}

function plan(works: SurfacePlannedWorkRead[]): SurfaceWorkPlanRead {
  return { id: 'plan-1', surface_id: S, substrate: 'CONCRETE', quality_target: 'S2', planned_works: works, template_applications: [] };
}

const PLAN = plan([
  work('k-ns', 0, NS, 4, item('p0', 'Gruntowanie')),
  work('k-ip', 1, { status: 'IN_PROGRESS', started_at: STARTED, completed_at: null, ready_after: null }),
  work('k-done', 2, { status: 'COMPLETED', started_at: STARTED, completed_at: DONE, ready_after: READY }, 24),
  work('k-dup', 3, NS),  // same PriceItem as k-ip ("Gładź"), independent card
  work('k-done-nowait', 4, { status: 'COMPLETED', started_at: STARTED, completed_at: DONE, ready_after: null },
    null, item('p9', 'Malowanie nawierzchniowe dwukrotne farbą lateksową bardzo długa nazwa pracy')),
]);

const onOpenPlan = vi.fn();

function renderView() {
  return render(
    <I18nProvider>
      <SurfaceExecutionView projectId="p" roomId="r" surfaceId={S} surfaceName="Ściana A" onClose={vi.fn()} onOpenPlan={onOpenPlan} />
    </I18nProvider>,
  );
}

const card = (key: string) => screen.getByLabelText(`execution-card-${key}`);
const patchCalls = () => vi.mocked(workPlansApi.transitionWorkExecution).mock.calls;

function response(key: string, execution: PlannedWorkExecutionRead): SurfaceWorkExecutionRead {
  return { occurrence_key: key, ...execution };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(PLAN);
});

describe('rendering', () => {
  it('renders every current occurrence as its own numbered card with status, breaks, times and readiness', async () => {
    renderView();
    const list = await screen.findByLabelText(`execution-works-${S}`);
    expect(within(list).getAllByRole('listitem')).toHaveLength(5);

    expect(card('k-ns')).toHaveTextContent('1. Gruntowanie');
    expect(screen.getByLabelText('execution-status-k-ns')).toHaveTextContent('Zaplanowano');
    expect(card('k-ns')).toHaveTextContent('Przerwa technologiczna po tej pracy: 4 h');
    expect(within(card('k-ns')).getByLabelText('execution-start-k-ns')).toHaveTextContent('Rozpocznij');
    expect(within(card('k-ns')).queryByLabelText('execution-started-k-ns')).toBeNull();

    expect(screen.getByLabelText('execution-status-k-ip')).toHaveTextContent('W trakcie');
    expect(within(card('k-ip')).getByLabelText('execution-complete-k-ip')).toHaveTextContent('Oznacz jako wykonane');
    expect(screen.getByLabelText('execution-started-k-ip')).toHaveTextContent(
      `Rozpoczęcie zapisano: ${formatRecordedDateTime(STARTED, 'pl')}`);

    const done = card('k-done');
    expect(screen.getByLabelText('execution-status-k-done')).toHaveTextContent('Wykonano');
    expect(within(done).queryByLabelText('execution-start-k-done')).toBeNull();
    expect(within(done).queryByLabelText('execution-complete-k-done')).toBeNull();  // no permanent primary action
    expect(screen.getByLabelText('execution-completed-k-done')).toHaveTextContent(
      `Ukończenie zapisano: ${formatRecordedDateTime(DONE, 'pl')}`);
    const ready = screen.getByLabelText('execution-ready-k-done');
    expect(ready).toHaveTextContent(`Gotowe do dalszych prac po: ${formatRecordedDateTime(READY, 'pl')}`);
    expect(ready).toHaveTextContent('Na podstawie ustawionej przerwy technologicznej.');
    expect(done).toHaveTextContent('24 h · 1 dzień');
    // ready_after null -> no readiness block; raw ISO never shown
    expect(screen.queryByLabelText('execution-ready-k-done-nowait')).toBeNull();
    expect(list.textContent).not.toMatch(/\d{4}-\d{2}-\d{2}T/);

    // duplicate PriceItem: separate card, own status
    expect(card('k-dup')).toHaveTextContent('4. Gładź');
    expect(screen.getByLabelText('execution-status-k-dup')).toHaveTextContent('Zaplanowano');
  });

  it('status is spelled out with a symbol (not color alone) and uses theme tokens only', async () => {
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    for (const key of ['k-ns', 'k-ip', 'k-done']) {
      const badge = screen.getByLabelText(`execution-status-${key}`);
      expect(badge.querySelector('[aria-hidden="true"]')?.textContent).toMatch(/[○◐✓]/);
      expect(badge.className).toContain('var(--tg-');
    }
    const view = screen.getByLabelText(`execution-view-${S}`);
    // No hardcoded light-only pairs (13G FIX.1 lesson): nothing slate/white here.
    expect(view.innerHTML).not.toMatch(/bg-white|bg-slate-|text-slate-|bg-gray-|text-gray-/);
  });

  it('every action is a >= 44 px control and long names wrap', async () => {
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    fireEvent.click(screen.getByLabelText('execution-options-k-done'));
    for (const button of screen.getByLabelText(`execution-view-${S}`).querySelectorAll('button')) {
      expect(button.className).toMatch(/min-h-11|min-h-\[44px\]/);
    }
    expect(card('k-done-nowait').querySelector('p.break-words')).not.toBeNull();
  });

  it('renders RU labels', async () => {
    localStorage.setItem('locale', 'ru');
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    expect(screen.getByLabelText('execution-status-k-ns')).toHaveTextContent('Запланировано');
    expect(screen.getByLabelText('execution-status-k-ip')).toHaveTextContent('В работе');
    expect(screen.getByLabelText('execution-status-k-done')).toHaveTextContent('Выполнено');
    expect(screen.getByLabelText('execution-start-k-ns')).toHaveTextContent('Начать');
    expect(screen.getByLabelText('execution-complete-k-ip')).toHaveTextContent('Отметить выполненной');
    expect(screen.getByLabelText('execution-started-k-ip')).toHaveTextContent('Начало отмечено:');
    expect(screen.getByLabelText('execution-ready-k-done')).toHaveTextContent('Следующие работы можно выполнять после:');
    expect(screen.getByLabelText('execution-ready-k-done')).toHaveTextContent('На основании заданного технологического перерыва.');
    fireEvent.click(screen.getByLabelText('execution-options-k-done'));
    expect(screen.getByLabelText('execution-reopen-k-done')).toHaveTextContent('Возобновить работу');
  });

  it('empty states: no saved plan and a plan without works point to the plan editor', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockRejectedValueOnce(new ApiError('Surface work plan not found', 404));
    const { unmount } = renderView();
    expect(await screen.findByLabelText(`execution-empty-${S}`)).toHaveTextContent('nie ma jeszcze zapisanego planu prac');
    expect(screen.getByLabelText(`execution-empty-${S}`)).toHaveTextContent('„Rodzaje prac i jakość”');
    fireEvent.click(screen.getByLabelText(`execution-open-plan-${S}`));
    expect(onOpenPlan).toHaveBeenCalledTimes(1);
    unmount();

    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValueOnce(plan([]));
    renderView();
    expect(await screen.findByLabelText(`execution-empty-${S}`)).toHaveTextContent('nie zawiera jeszcze żadnych prac');
    expect(workPlansApi.transitionWorkExecution).not.toHaveBeenCalled();
  });

  it('a load failure offers retry', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockRejectedValueOnce(new ApiError('boom', 500));
    renderView();
    fireEvent.click(await screen.findByLabelText(`retry-execution-${S}`));
    expect(await screen.findByLabelText(`execution-works-${S}`)).toBeInTheDocument();
  });
});

describe('transitions', () => {
  it.each([
    ['start', 'k-ns', 'execution-start-k-ns', null, 'IN_PROGRESS', 'NOT_STARTED'],
    ['complete', 'k-ip', 'execution-complete-k-ip', null, 'COMPLETED', 'IN_PROGRESS'],
    ['reopen', 'k-done', 'execution-reopen-k-done', 'execution-options-k-done', 'IN_PROGRESS', 'COMPLETED'],
    ['reset', 'k-ip', 'execution-reset-k-ip', 'execution-options-k-ip', 'NOT_STARTED', 'IN_PROGRESS'],
    ['direct complete', 'k-ns', 'execution-complete-now-k-ns', 'execution-options-k-ns', 'COMPLETED', 'NOT_STARTED'],
  ] as const)('%s sends status + the displayed expected_status and shows the server response', async (_n, key, action, options, status, expected) => {
    const serverAt = '2026-09-27T12:34:00Z';
    const result: PlannedWorkExecutionRead = status === 'NOT_STARTED' ? NS
      : status === 'IN_PROGRESS' ? { status, started_at: serverAt, completed_at: null, ready_after: null }
        : { status, started_at: serverAt, completed_at: serverAt, ready_after: null };
    vi.mocked(workPlansApi.transitionWorkExecution).mockResolvedValue(response(key, result));
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    if (options) fireEvent.click(screen.getByLabelText(options));
    fireEvent.click(screen.getByLabelText(action));
    await waitFor(() => expect(screen.getByLabelText(`execution-status-${key}`)).toHaveTextContent(
      { NOT_STARTED: 'Zaplanowano', IN_PROGRESS: 'W trakcie', COMPLETED: 'Wykonano' }[status]));
    expect(patchCalls()).toEqual([['p', 'r', S, key, { status, expected_status: expected }]]);
    if (result.started_at) {
      expect(screen.getByLabelText(`execution-started-${key}`)).toHaveTextContent(formatRecordedDateTime(serverAt, 'pl'));
    } else {
      expect(screen.queryByLabelText(`execution-started-${key}`)).toBeNull();
    }
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(1); // no reload needed
  });

  it('pending blocks double submit and never shows a state before the server answers', async () => {
    let resolve!: (value: SurfaceWorkExecutionRead) => void;
    vi.mocked(workPlansApi.transitionWorkExecution).mockReturnValue(new Promise((r) => { resolve = r; }));
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    const start = screen.getByLabelText('execution-start-k-ns');
    fireEvent.click(start);
    fireEvent.click(start);
    fireEvent.click(screen.getByLabelText('execution-complete-k-ip'));
    expect(patchCalls()).toHaveLength(1);
    expect(start).toBeDisabled();
    expect(screen.getByLabelText('execution-complete-k-ip')).toBeDisabled();
    expect(card('k-ns')).toHaveTextContent('Zapisywanie statusu...');
    expect(screen.getByLabelText('execution-status-k-ns')).toHaveTextContent('Zaplanowano');  // not optimistic
    await act(async () => resolve(response('k-ns', { status: 'IN_PROGRESS', started_at: STARTED, completed_at: null, ready_after: null })));
    expect(screen.getByLabelText('execution-status-k-ns')).toHaveTextContent('W trakcie');
  });

  it('a generic error keeps the displayed state and allows retry', async () => {
    vi.mocked(workPlansApi.transitionWorkExecution)
      .mockRejectedValueOnce(new ApiError('Request failed (500)', 500))
      .mockResolvedValueOnce(response('k-ns', { status: 'IN_PROGRESS', started_at: STARTED, completed_at: null, ready_after: null }));
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    fireEvent.click(screen.getByLabelText('execution-start-k-ns'));
    expect(await screen.findByLabelText('execution-message-k-ns')).toHaveTextContent('Nie udało się zmienić statusu. Spróbuj ponownie.');
    expect(screen.getByLabelText('execution-status-k-ns')).toHaveTextContent('Zaplanowano');
    expect(within(screen.getByLabelText(`execution-works-${S}`)).getAllByRole('listitem')).toHaveLength(5);
    fireEvent.click(screen.getByLabelText('execution-start-k-ns'));
    await waitFor(() => expect(screen.getByLabelText('execution-status-k-ns')).toHaveTextContent('W trakcie'));
    expect(screen.queryByLabelText('execution-message-k-ns')).toBeNull();
  });

  it('an archived hierarchy 422 is shown localized', async () => {
    vi.mocked(workPlansApi.transitionWorkExecution).mockRejectedValueOnce(new ApiError(
      'execution cannot change on an archived project, room or surface; restore it first', 422, 'execution_archived'));
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    fireEvent.click(screen.getByLabelText('execution-start-k-ns'));
    expect(await screen.findByLabelText('execution-message-k-ns')).toHaveTextContent('zarchiwizowanym');
  });

  it('WORK_EXECUTION_CONFLICT reloads the server state, explains it and never retries', async () => {
    vi.mocked(workPlansApi.transitionWorkExecution).mockRejectedValueOnce(new ApiError(
      'execution of occurrence k-ip is COMPLETED', 409, 'WORK_EXECUTION_CONFLICT',
      { code: 'WORK_EXECUTION_CONFLICT', message: 'x', current_status: 'COMPLETED' }));
    const elsewhere = plan(PLAN.planned_works.map((w) => w.occurrence_key === 'k-ip'
      ? { ...w, execution: { status: 'COMPLETED' as const, started_at: STARTED, completed_at: DONE, ready_after: null } } : w));
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValueOnce(elsewhere);
    fireEvent.click(screen.getByLabelText('execution-complete-k-ip'));
    expect(await screen.findByLabelText('execution-message-k-ip')).toHaveTextContent(
      'Status tej pracy zmienił się w innym miejscu. Dane zostały odświeżone.');
    await waitFor(() => expect(screen.getByLabelText('execution-status-k-ip')).toHaveTextContent('Wykonano'));
    expect(patchCalls()).toHaveLength(1);
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(2);
  });
});
