/**
 * Stage 13E.2C — WorkPlan editor occurrence identity compatibility.
 *
 * Every ordinary save uses planned_works[]; an existing occurrence echoes its
 * server occurrence_key and keeps its wait_after_hours and coefficient
 * selection; a new occurrence omits the key and picks up the server key from
 * the save response; a stale-key 409 asks for a reload and never retries
 * without keys.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as workPlansApi from './api/workPlans';
import * as priceItemsApi from './api/priceItems';
import { ApiError } from './api/http';
import { SurfaceWorkPlanEditor } from './components/SurfaceWorkPlanEditor';
import { I18nProvider } from './hooks/useI18n';
import { PriceItem } from './types/priceItem';
import {
  PlannedWorkCoefficientOptionRead,
  SurfacePlannedWorkRead,
  SurfaceWorkPlanRead,
} from './types/workPlan';

vi.mock('./api/workPlans', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workPlans')>();
  return {
    ...actual,
    fetchSurfaceWorkPlan: vi.fn(),
    putSurfaceWorkPlan: vi.fn(),
    applyWorkPlanToRoomWalls: vi.fn(),
  };
});

vi.mock('./api/priceItems', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/priceItems')>();
  return { ...actual, fetchPriceItems: vi.fn(), createPriceItem: vi.fn() };
});

vi.mock('./api/coefficients', () => ({ fetchCoefficientGroups: vi.fn() }));

const projectId = 'p-1';
const roomId = 'r-1';
const surfaceId = 's-1';

const summary = {
  id: 'price-p',
  code: 'CUSTOM_P',
  name_key: null,
  display_name: 'Gładź',
  category: 'SKIM_COAT' as const,
  unit: 'M2' as const,
  price_scope: 'LABOR' as const,
  price: '20.00',
  currency: 'PLN',
  is_archived: false,
  quality_level: null,
};

function option(id: string, percentage: string): PlannedWorkCoefficientOptionRead {
  return {
    id, group_id: `grp-${id}`, group_code: 'HEIGHT', code: id,
    display_name: id, percentage, is_base: false,
  };
}

function work(
  id: string, key: string, position: number, wait: number | null, options: PlannedWorkCoefficientOptionRead[] = [],
): SurfacePlannedWorkRead {
  return {
    id, work_plan_id: 'plan-1', price_item_id: 'price-p', position,
    occurrence_key: key, wait_after_hours: wait, price_item: summary, coefficient_options: options,
  };
}

// Two occurrences of the SAME PriceItem with different identity/configuration.
const A = work('row-a', 'key-A', 0, 24, [option('opt-15', '15.00')]);
const B = work('row-b', 'key-B', 1, null, [option('opt-25', '25.00')]);

function plan(works: SurfacePlannedWorkRead[], overrides: Partial<SurfaceWorkPlanRead> = {}): SurfaceWorkPlanRead {
  return {
    id: 'plan-1', surface_id: surfaceId, substrate: 'CONCRETE', quality_target: 'S2',
    planned_works: works, ...overrides,
  };
}

const sentA = { price_item_id: 'price-p', occurrence_key: 'key-A', wait_after_hours: 24, coefficient_option_ids: ['opt-15'] };
const sentB = { price_item_id: 'price-p', occurrence_key: 'key-B', wait_after_hours: null, coefficient_option_ids: ['opt-25'] };

const pickerItem: PriceItem = {
  ...summary,
  display_name: 'Gładź',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} as PriceItem;

function renderEditor() {
  return render(
    <I18nProvider>
      <SurfaceWorkPlanEditor
        projectId={projectId}
        roomId={roomId}
        surfaceId={surfaceId}
        surfaceName="Ściana"
        isWall={false}
        onClose={vi.fn()}
      />
    </I18nProvider>,
  );
}

async function rows() {
  await screen.findByLabelText(`work-plan-form-${surfaceId}`);
  return within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
}

async function start() {
  renderEditor();
  return rows();
}

function save() {
  fireEvent.click(screen.getByLabelText(`save-work-plan-${surfaceId}`));
}

function lastPayload() {
  const calls = vi.mocked(workPlansApi.putSurfaceWorkPlan).mock.calls;
  return calls[calls.length - 1][3];
}

describe('SurfaceWorkPlanEditor — occurrence identity (13E.2C)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(plan([A, B]));
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [pickerItem], total: 1 });
  });

  it('reorder keeps each duplicate occurrence with its own key, wait and coefficients', async () => {
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(plan([B, A]));
    const [first] = await start();
    fireEvent.click(within(first).getByText('↓'));
    save();
    await waitFor(() => expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(1));
    const payload = lastPayload();
    expect(payload).not.toHaveProperty('price_item_ids');
    expect(payload.planned_works).toEqual([sentB, sentA]);
  });

  it('an unrelated edit re-sends every occurrence unchanged (waits, NULL waits, coefficients)', async () => {
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(plan([A, B], { quality_target: 'S3' }));
    await start();
    fireEvent.change(screen.getByLabelText(`work-plan-quality-${surfaceId}`), { target: { value: 'S3' } });
    save();
    await waitFor(() => expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(1));
    expect(lastPayload()).toEqual({ substrate: 'CONCRETE', quality_target: 'S3', planned_works: [sentA, sentB] });
  });

  it('a single occurrence without coefficients still uses planned_works[]', async () => {
    const lone = work('row-x', 'key-X', 0, null);
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(plan([lone]));
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(plan([lone], { quality_target: 'S3' }));
    await start();
    fireEvent.change(screen.getByLabelText(`work-plan-quality-${surfaceId}`), { target: { value: 'S3' } });
    save();
    await waitFor(() => expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(1));
    expect(lastPayload().planned_works).toEqual([
      { price_item_id: 'price-p', occurrence_key: 'key-X', wait_after_hours: null, coefficient_option_ids: [] },
    ]);
    expect(lastPayload()).not.toHaveProperty('price_item_ids');
  });

  it('deleting A leaves B exactly as it was', async () => {
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(plan([B]));
    const [first] = await start();
    fireEvent.click(within(first).getByLabelText(/^remove-occurrence-/));
    save();
    await waitFor(() => expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(1));
    expect(lastPayload().planned_works).toEqual([sentB]);
  });

  it('new work is sent without a key, takes the server key from the response, and the next save echoes it', async () => {
    const created = work('row-new', 'key-NEW', 2, null);
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValueOnce(plan([A, B, created]));
    await start();
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    fireEvent.click(await screen.findByLabelText('picker-item-price-p'));
    save();
    await waitFor(() => expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(1));
    const first = lastPayload().planned_works!;
    expect(first).toEqual([
      sentA, sentB, { price_item_id: 'price-p', wait_after_hours: null, coefficient_option_ids: [] },
    ]);
    expect(first[2]).not.toHaveProperty('occurrence_key'); // never a client-made key

    // Second ordinary save after re-hydration: the new row echoes the server key.
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValueOnce(plan([created, A, B]));
    const current = await rows();
    expect(current).toHaveLength(3);
    fireEvent.click(within(current[2]).getByText('↑'));
    fireEvent.click(within((await rows())[1]).getByText('↑'));
    save();
    await waitFor(() => expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(2));
    expect(lastPayload().planned_works).toEqual([
      { price_item_id: 'price-p', occurrence_key: 'key-NEW', wait_after_hours: null, coefficient_option_ids: [] },
      sentA,
      sentB,
    ]);
  });

  it('a stale-key 409 asks to reload, never retries without keys, and reload refetches', async () => {
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockRejectedValue(
      new ApiError('occurrence_key key-B is not a current occurrence of this work plan; reload the plan and try again', 409),
    );
    const [first] = await start();
    fireEvent.click(within(first).getByText('↓'));
    save();
    const alert = await screen.findByLabelText(`stale-work-plan-${surfaceId}`);
    expect(alert).toHaveTextContent('Plan prac zmienił się od czasu jego otwarcia. Odśwież plan przed ponownym zapisem.');
    expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(1);
    expect(lastPayload().planned_works).toEqual([sentB, sentA]); // keys were sent, nothing re-sent keyless
    const reload = screen.getByLabelText(`reload-work-plan-${surfaceId}`);
    expect(reload.className).toContain('min-h-11');
    fireEvent.click(reload);
    await waitFor(() => expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByLabelText(`stale-work-plan-${surfaceId}`)).not.toBeInTheDocument());
  });

  it('other save errors keep the existing error path (no stale message)', async () => {
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockRejectedValue(
      new ApiError('application_id x cannot be recorded for this save; generate a new one for a new application', 409),
    );
    const [first] = await start();
    fireEvent.click(within(first).getByText('↓'));
    save();
    expect(await screen.findByText('Nie udało się zapisać planu prac.')).toBeInTheDocument();
    expect(screen.queryByLabelText(`stale-work-plan-${surfaceId}`)).not.toBeInTheDocument();
  });

  it('shows the stale-plan message in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockRejectedValue(
      new ApiError('occurrence_key key-A is not a current occurrence of this work plan; reload the plan and try again', 409),
    );
    const [first] = await start();
    fireEvent.click(within(first).getByText('↓'));
    save();
    const alert = await screen.findByLabelText(`stale-work-plan-${surfaceId}`);
    expect(alert).toHaveTextContent('План работ изменился после его открытия. Обновите план перед повторным сохранением.');
    expect(screen.getByLabelText(`reload-work-plan-${surfaceId}`)).toHaveTextContent('Обновить план');
  });
});
