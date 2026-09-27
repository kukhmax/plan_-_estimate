/**
 * Stage 13H.5B.2 — Realizacja: carry this wall's execution progress forward
 * to the room's other walls (preview -> summary -> apply), exact server
 * snapshot, source-changed 409, results, PL/RU and theme-safe markup.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api/http';
import * as workPlansApi from './api/workPlans';
import { SurfaceExecutionView } from './components/SurfaceExecutionView';
import { I18nProvider } from './hooks/useI18n';
import {
  BulkExecutionResultRead,
  BulkExecutionWallRead,
  PlannedWorkExecutionRead,
  SurfacePlannedWorkRead,
  SurfaceWorkPlanRead,
} from './types/workPlan';

vi.mock('./api/workPlans', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workPlans')>();
  return {
    ...actual,
    fetchSurfaceWorkPlan: vi.fn(),
    transitionWorkExecution: vi.fn(),
    previewExecutionToRoomWalls: vi.fn(),
    applyExecutionToRoomWalls: vi.fn(),
  };
});

const S = 'wall-a';
const exec = (status: PlannedWorkExecutionRead['status']): PlannedWorkExecutionRead => ({
  status, started_at: status === 'NOT_STARTED' ? null : '2026-09-27T08:00:00Z',
  completed_at: status === 'COMPLETED' ? '2026-09-27T10:00:00Z' : null, ready_after: null });

function work(key: string, position: number, status: PlannedWorkExecutionRead['status']): SurfacePlannedWorkRead {
  return { id: `row-${key}`, work_plan_id: 'plan-a', price_item_id: `p${position}`, position, occurrence_key: key,
    wait_after_hours: null, coefficient_options: [], execution: exec(status),
    price_item: { id: `p${position}`, code: `P${position}`, name_key: null, display_name: `Praca ${position + 1}`,
      category: 'SKIM_COAT', unit: 'M2', price_scope: 'LABOR', price: null, currency: 'PLN', is_archived: false, quality_level: null } };
}

const PLAN: SurfaceWorkPlanRead = {
  id: 'plan-a', surface_id: S, substrate: 'CONCRETE', quality_target: 'S2', template_applications: [],
  planned_works: [work('k1', 0, 'COMPLETED'), work('k2', 1, 'IN_PROGRESS'), work('k3', 2, 'NOT_STARTED')],
};
// The server's snapshot, including the NOT_STARTED entry: must be sent back verbatim (same object).
const SNAPSHOT = [
  { occurrence_key: 'k1', status: 'COMPLETED' as const },
  { occurrence_key: 'k2', status: 'IN_PROGRESS' as const },
  { occurrence_key: 'k3', status: 'NOT_STARTED' as const },
];

function wall(id: string, changed: number, unchanged: number, unmatched = 0, ambiguous = 0, hasPlan = true): BulkExecutionWallRead {
  return { surface_id: id, has_plan: hasPlan, changed, unchanged, unmatched, ambiguous,
    unmatched_price_item_ids: [], ambiguous_price_item_ids: [] };
}

function result(walls: BulkExecutionWallRead[], applied = false, snapshot = SNAPSHOT): BulkExecutionResultRead {
  const sum = (k: 'changed' | 'unchanged' | 'unmatched' | 'ambiguous') => walls.reduce((n, w) => n + w[k], 0);
  return { source_surface_id: S, applied, expected_source: snapshot, changed: sum('changed'), unchanged: sum('unchanged'),
    unmatched: sum('unmatched'), ambiguous: sum('ambiguous'), walls };
}

const PREVIEW = result([wall('wall-b', 2, 1), wall('wall-c', 1, 1, 1, 0), wall('wall-d', 0, 1, 0, 2), wall('wall-e', 0, 0, 3, 0, false)]);
const NAMES = { [S]: 'Ściana A', 'wall-b': 'Ściana B', 'wall-c': 'Ściana C', 'wall-d': 'Ściana D', 'wall-e': 'Ściana E' };

function renderView(props: Partial<Parameters<typeof SurfaceExecutionView>[0]> = {}) {
  return render(
    <I18nProvider>
      <SurfaceExecutionView projectId="p" roomId="r" surfaceId={S} surfaceName="Ściana A" onClose={vi.fn()}
        isWall otherActiveWallCount={4} surfaceNames={NAMES} {...props} />
    </I18nProvider>,
  );
}

const open = () => screen.getByLabelText(`execution-bulk-open-${S}`);

async function openSheet() {
  await screen.findByLabelText(`execution-works-${S}`);
  fireEvent.click(open());
  return screen.findByLabelText(`execution-bulk-sheet-${S}`);
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(PLAN);
  vi.mocked(workPlansApi.previewExecutionToRoomWalls).mockResolvedValue(PREVIEW);
});

describe('entry', () => {
  it('shows the execution-status action on a wall with other walls, distinct from WorkPlan apply-to-all', async () => {
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    expect(open()).toHaveTextContent('Zastosuj statusy dla pozostałych ścian');
    expect(open().textContent).not.toMatch(/wszystkich|Zapisz dla/);
    expect(open().className).toContain('min-h-11');
  });

  it('is absent for non-wall surfaces, a room without other walls, or an empty plan', async () => {
    const { unmount } = renderView({ isWall: false });
    await screen.findByLabelText(`execution-works-${S}`);
    expect(screen.queryByLabelText(`execution-bulk-open-${S}`)).toBeNull();
    unmount();
    const r2 = renderView({ otherActiveWallCount: 0 });
    await screen.findByLabelText(`execution-works-${S}`);
    expect(screen.queryByLabelText(`execution-bulk-open-${S}`)).toBeNull();
    r2.unmount();
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValueOnce({ ...PLAN, planned_works: [] });
    renderView();
    await screen.findByLabelText(`execution-empty-${S}`);
    expect(screen.queryByLabelText(`execution-bulk-open-${S}`)).toBeNull();
  });
});

describe('preview summary', () => {
  it('previews (no mutation) and shows every count, per-wall lines, no-plan wall, ambiguity and forward-only text', async () => {
    renderView();
    const s = await openSheet();
    expect(workPlansApi.previewExecutionToRoomWalls).toHaveBeenCalledWith('p', 'r', S);
    expect(workPlansApi.applyExecutionToRoomWalls).not.toHaveBeenCalled();
    expect(workPlansApi.transitionWorkExecution).not.toHaveBeenCalled();
    const counts = within(s).getByLabelText(`execution-bulk-counts-${S}`);
    expect(counts).toHaveTextContent('Pozostałe ściany w pomieszczeniu: 4');
    expect(counts).toHaveTextContent('Statusy do aktualizacji: 3');
    expect(counts).toHaveTextContent('Bez zmian (ten sam lub późniejszy etap): 3');
    expect(counts).toHaveTextContent('Bez odpowiednika na innej ścianie: 1');  // no-plan wall excluded
    expect(counts).toHaveTextContent('Niejednoznaczne: 2');
    expect(counts).toHaveTextContent('Ściany bez planu prac: 1');
    expect(within(s).getByLabelText(`execution-bulk-ambiguous-hint-${S}`)).toHaveTextContent('liczba powtórzeń tej samej pracy różni się');

    const b = within(s).getByLabelText('execution-bulk-wall-wall-b');
    expect(b).toHaveTextContent('Ściana B');
    expect(b).toHaveTextContent('2 do aktualizacji');
    expect(b).toHaveTextContent('1 bez zmian');
    expect(within(s).getByLabelText('execution-bulk-wall-wall-c')).toHaveTextContent('1 bez odpowiednika');
    expect(within(s).getByLabelText('execution-bulk-wall-wall-d')).toHaveTextContent('2 niejednoznaczne');
    const e = within(s).getByLabelText('execution-bulk-wall-wall-e');
    expect(e).toHaveTextContent('Brak planu prac');
    expect(e).not.toHaveTextContent(/odpowiednika|3/);

    const explain = within(s).getByLabelText(`execution-bulk-explain-${S}`);
    expect(explain).toHaveTextContent('Zmienione zostaną tylko odpowiadające sobie prace na pozostałych ścianach tego pomieszczenia.');
    expect(explain).toHaveTextContent('Postęp jest przesuwany tylko do przodu. Prace, które są już na późniejszym etapie, nie zostaną cofnięte.');
    expect(explain).toHaveTextContent('Czas rozpoczęcia lub wykonania zostanie zapisany osobno dla każdej ściany.');
    // no internal identifiers leak into the UI
    expect(s.textContent).not.toMatch(/k1|k2|k3|occurrence|PriceItem|expected_source|wall-b/);
    // the source cards were not touched by the preview
    expect(screen.getByLabelText('execution-status-k3')).toHaveTextContent('Zaplanowano');
  });

  it('prevents a double preview', async () => {
    let resolve!: (v: BulkExecutionResultRead) => void;
    vi.mocked(workPlansApi.previewExecutionToRoomWalls).mockReturnValue(new Promise((r) => { resolve = r; }));
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    fireEvent.click(open());
    fireEvent.click(open());
    expect(open()).toBeDisabled();
    expect(open()).toHaveTextContent('Sprawdzanie pozostałych ścian...');
    expect(workPlansApi.previewExecutionToRoomWalls).toHaveBeenCalledTimes(1);
    await act(async () => resolve(PREVIEW));
  });

  it.each([
    ['no other walls', result([]), 'W tym pomieszczeniu nie ma innych aktywnych ścian.'],
    ['source only NOT_STARTED', result([wall('wall-b', 0, 3)], false, SNAPSHOT.map((i) => ({ ...i, status: 'NOT_STARTED' as const }))),
      'Na tej ścianie nie ma jeszcze rozpoczętych ani wykonanych prac.'],
    ['already further', result([wall('wall-b', 0, 3)]), 'mają już ten sam lub późniejszy status'],
    ['plans do not match', result([wall('wall-b', 0, 0, 1, 2)]), 'nie pasują do tej ściany'],
  ])('changed=0 (%s) is informational with no apply button', async (_n, preview, text) => {
    vi.mocked(workPlansApi.previewExecutionToRoomWalls).mockResolvedValue(preview);
    renderView();
    const s = await openSheet();
    expect(within(s).getByLabelText(`execution-bulk-nothing-${S}`)).toHaveTextContent(text);
    expect(within(s).queryByLabelText(`execution-bulk-confirm-${S}`)).toBeNull();
    fireEvent.click(within(s).getByLabelText(`execution-bulk-close-${S}`));
    expect(screen.queryByLabelText(`execution-bulk-sheet-${S}`)).toBeNull();
    expect(workPlansApi.applyExecutionToRoomWalls).not.toHaveBeenCalled();
  });

  it('a preview error keeps the view and allows retry', async () => {
    vi.mocked(workPlansApi.previewExecutionToRoomWalls).mockRejectedValueOnce(new ApiError('boom', 500));
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    fireEvent.click(open());
    expect(await screen.findByLabelText(`execution-bulk-result-${S}`)).toHaveTextContent('Nie udało się sprawdzić pozostałych ścian');
    expect(screen.getByLabelText(`execution-works-${S}`)).toBeInTheDocument();
    fireEvent.click(open());
    expect(await screen.findByLabelText(`execution-bulk-sheet-${S}`)).toBeInTheDocument();
  });
});

describe('apply', () => {
  it('sends the preview snapshot verbatim, blocks double apply, and reports from the APPLY response', async () => {
    let resolve!: (v: BulkExecutionResultRead) => void;
    vi.mocked(workPlansApi.applyExecutionToRoomWalls).mockReturnValue(new Promise((r) => { resolve = r; }));
    renderView();
    const s = await openSheet();
    const confirm = within(s).getByLabelText(`execution-bulk-confirm-${S}`);
    expect(confirm).toHaveTextContent('Zastosuj statusy');
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(confirm).toBeDisabled();
    expect(confirm).toHaveTextContent('Zapisywanie statusów...');
    expect(workPlansApi.applyExecutionToRoomWalls).toHaveBeenCalledTimes(1);
    const sent = vi.mocked(workPlansApi.applyExecutionToRoomWalls).mock.calls[0][3];
    expect(sent).toBe(PREVIEW.expected_source);  // same object: not rebuilt, sorted or filtered
    expect(sent.map((i) => i.status)).toContain('NOT_STARTED');

    // destinations changed meanwhile: the apply result differs from the preview and is what we show
    await act(async () => resolve(result([wall('wall-b', 1, 2), wall('wall-c', 0, 2, 1, 0), wall('wall-d', 4, 1, 0, 2), wall('wall-e', 0, 0, 3, 0, false)], true)));
    await waitFor(() => expect(screen.queryByLabelText(`execution-bulk-sheet-${S}`)).toBeNull());
    const notice = screen.getByLabelText(`execution-bulk-result-${S}`);
    expect(notice).toHaveTextContent('Zaktualizowano 5 prac na 2 ścianach.');  // walls with changed > 0 only
    expect(notice).toHaveTextContent('Nie dopasowano: 1. Niejednoznaczne: 2. Ściany bez planu prac: 1.');
    // the source is re-read and unchanged
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(2);
    expect(screen.getByLabelText('execution-status-k1')).toHaveTextContent('Wykonano');
    expect(screen.getByLabelText('execution-status-k3')).toHaveTextContent('Zaplanowano');
  });

  it.each([
    [1, 1, 'Zaktualizowano 1 pracę na 1 ścianie.'],
    [3, 2, 'Zaktualizowano 3 prace na 2 ścianach.'],
    [12, 5, 'Zaktualizowano 12 prac na 5 ścianach.'],
  ])('PL plural forms (%i works / %i walls)', async (works, walls, text) => {
    const ws = Array.from({ length: walls }, (_, i) => wall(`w${i}`, i === 0 ? works - (walls - 1) : 1, 0));
    vi.mocked(workPlansApi.applyExecutionToRoomWalls).mockResolvedValue(result(ws, true));
    renderView();
    fireEvent.click(within(await openSheet()).getByLabelText(`execution-bulk-confirm-${S}`));
    expect(await screen.findByLabelText(`execution-bulk-result-${S}`)).toHaveTextContent(text);
  });

  it('changed=0 after recomputation is not presented as a success', async () => {
    vi.mocked(workPlansApi.applyExecutionToRoomWalls).mockResolvedValue(result([wall('wall-b', 0, 3)], true));
    renderView();
    fireEvent.click(within(await openSheet()).getByLabelText(`execution-bulk-confirm-${S}`));
    const notice = await screen.findByLabelText(`execution-bulk-result-${S}`);
    expect(notice).toHaveTextContent('Nie zaktualizowano żadnej pracy.');
    expect(notice).not.toHaveTextContent(/Zaktualizowano \d/);
  });

  it('WORK_EXECUTION_SOURCE_CHANGED closes the sheet, refreshes the source, never retries and requires a new preview', async () => {
    vi.mocked(workPlansApi.applyExecutionToRoomWalls).mockRejectedValueOnce(new ApiError('changed', 409,
      'WORK_EXECUTION_SOURCE_CHANGED', { code: 'WORK_EXECUTION_SOURCE_CHANGED', message: 'x', current_source: [] }));
    const changedPlan = { ...PLAN, planned_works: [work('k1', 0, 'COMPLETED'), work('k2', 1, 'COMPLETED'), work('k3', 2, 'NOT_STARTED')] };
    renderView();
    const s = await openSheet();
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValueOnce(changedPlan);
    fireEvent.click(within(s).getByLabelText(`execution-bulk-confirm-${S}`));
    expect(await screen.findByLabelText(`execution-bulk-result-${S}`)).toHaveTextContent(
      'Stan prac na tej ścianie zmienił się od czasu podglądu. Dane zostały odświeżone. Sprawdź je i spróbuj ponownie.');
    expect(screen.queryByLabelText(`execution-bulk-sheet-${S}`)).toBeNull();
    await waitFor(() => expect(screen.getByLabelText('execution-status-k2')).toHaveTextContent('Wykonano'));
    expect(workPlansApi.applyExecutionToRoomWalls).toHaveBeenCalledTimes(1);
    expect(workPlansApi.previewExecutionToRoomWalls).toHaveBeenCalledTimes(1);  // no automatic new preview
    fireEvent.click(open());
    await screen.findByLabelText(`execution-bulk-sheet-${S}`);
    expect(workPlansApi.previewExecutionToRoomWalls).toHaveBeenCalledTimes(2);
  });

  it('a generic apply error keeps the sheet, mutates nothing locally and allows retry', async () => {
    vi.mocked(workPlansApi.applyExecutionToRoomWalls)
      .mockRejectedValueOnce(new ApiError('Request failed (500)', 500))
      .mockResolvedValueOnce(result([wall('wall-b', 2, 1)], true));
    renderView();
    const s = await openSheet();
    fireEvent.click(within(s).getByLabelText(`execution-bulk-confirm-${S}`));
    expect(await within(s).findByLabelText(`execution-bulk-error-${S}`)).toHaveTextContent('Nie udało się zastosować statusów');
    expect(screen.getByLabelText('execution-status-k2')).toHaveTextContent('W trakcie');
    fireEvent.click(within(s).getByLabelText(`execution-bulk-confirm-${S}`));
    expect(await screen.findByLabelText(`execution-bulk-result-${S}`)).toHaveTextContent('Zaktualizowano 2 prace na 1 ścianie.');
    expect(vi.mocked(workPlansApi.applyExecutionToRoomWalls).mock.calls[1][3]).toBe(PREVIEW.expected_source);
  });

  it('cancel sends nothing', async () => {
    renderView();
    fireEvent.click(within(await openSheet()).getByLabelText(`execution-bulk-close-${S}`));
    expect(workPlansApi.applyExecutionToRoomWalls).not.toHaveBeenCalled();
    expect(screen.queryByLabelText(`execution-bulk-result-${S}`)).toBeNull();
  });
});

describe('language and markup', () => {
  it('renders RU', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(workPlansApi.applyExecutionToRoomWalls).mockResolvedValue(
      result([wall('wall-b', 5, 0), wall('wall-c', 4, 0, 1, 1), wall('wall-e', 0, 0, 3, 0, false)], true));
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    expect(open()).toHaveTextContent('Применить статусы к остальным стенам');
    fireEvent.click(open());
    const s = await screen.findByLabelText(`execution-bulk-sheet-${S}`);
    expect(s).toHaveTextContent('Будут изменены только соответствующие работы на остальных стенах этого помещения.');
    expect(s).toHaveTextContent('Статус продвигается только вперёд.');
    expect(s).toHaveTextContent('Время начала или выполнения будет зафиксировано отдельно для каждой стены.');
    expect(s).toHaveTextContent('Некоторые работы нельзя однозначно сопоставить');
    expect(within(s).getByLabelText('execution-bulk-wall-wall-e')).toHaveTextContent('Нет плана работ');
    expect(within(s).getByLabelText(`execution-bulk-confirm-${S}`)).toHaveTextContent('Применить статусы');
    fireEvent.click(within(s).getByLabelText(`execution-bulk-confirm-${S}`));
    const notice = await screen.findByLabelText(`execution-bulk-result-${S}`);
    expect(notice).toHaveTextContent('Обновлено 9 работ на 2 стенах.');
    expect(notice).toHaveTextContent('Не сопоставлено: 1. Неоднозначно: 1. Стены без плана работ: 1.');
  });

  it('uses only theme tokens and >= 44 px controls', async () => {
    renderView();
    const s = await openSheet();
    for (const button of [...s.querySelectorAll('button'), open()]) {
      expect(button.className).toMatch(/min-h-11|min-h-\[44px\]/);
    }
    expect(s.innerHTML).not.toMatch(/bg-white|bg-slate-|text-slate-|bg-gray-|text-gray-|bg-red-|text-red-/);
    expect(open().className).toContain('var(--tg-');
  });
});

describe('owner-verified walkthrough regression (13H.6)', () => {
  it('3 walls: 6 to update / 3 unchanged, apply, then 0 / 9 with no apply action', async () => {
    localStorage.setItem('locale', 'ru');
    const walls = ['w2', 'w3', 'w4'];
    vi.mocked(workPlansApi.previewExecutionToRoomWalls)
      .mockResolvedValueOnce(result(walls.map((w) => wall(w, 2, 1))))
      .mockResolvedValueOnce(result(walls.map((w) => wall(w, 0, 3))));
    vi.mocked(workPlansApi.applyExecutionToRoomWalls).mockResolvedValue(result(walls.map((w) => wall(w, 2, 1)), true));
    renderView({ otherActiveWallCount: 3 });
    const first = await openSheet();
    expect(first).toHaveTextContent('Остальные стены в помещении: 3');
    expect(first).toHaveTextContent('Статусов будет обновлено: 6');
    expect(first).toHaveTextContent('Без изменений (тот же или более поздний этап): 3');
    fireEvent.click(within(first).getByLabelText(`execution-bulk-confirm-${S}`));
    expect(await screen.findByLabelText(`execution-bulk-result-${S}`)).toHaveTextContent('Обновлено 6 работ на 3 стенах.');

    fireEvent.click(open());
    const second = await screen.findByLabelText(`execution-bulk-sheet-${S}`);
    expect(second).toHaveTextContent('Нет статусов для переноса');
    expect(second).toHaveTextContent('Статусов будет обновлено: 0');
    expect(second).toHaveTextContent('Без изменений (тот же или более поздний этап): 9');
    expect(within(second).queryByLabelText(`execution-bulk-confirm-${S}`)).toBeNull();
    expect(workPlansApi.applyExecutionToRoomWalls).toHaveBeenCalledTimes(1);
  });
});
