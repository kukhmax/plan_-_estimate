/**
 * Stage 13G — technological breaks (`wait_after_hours`) in the actual surface
 * work plan: display, per-occurrence editing through the existing WorkPlan
 * save, preservation of occurrence identity and coefficients.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as workPlansApi from './api/workPlans';
import * as priceItemsApi from './api/priceItems';
import * as coefficientsApi from './api/coefficients';
import { SurfaceWorkPlanEditor } from './components/SurfaceWorkPlanEditor';
import { I18nProvider } from './hooks/useI18n';
import { SurfacePlannedWorkRead, SurfacePriceItemSummaryRead, SurfaceWorkPlanRead, SurfaceWorkPlanUpsert } from './types/workPlan';

vi.mock('./api/workPlans', async (orig) => ({
  ...(await orig<typeof import('./api/workPlans')>()),
  fetchSurfaceWorkPlan: vi.fn(), putSurfaceWorkPlan: vi.fn(), applyWorkPlanToRoomWalls: vi.fn(),
}));
vi.mock('./api/priceItems', async (orig) => ({
  ...(await orig<typeof import('./api/priceItems')>()),
  fetchPriceItems: vi.fn(), createPriceItem: vi.fn(),
}));
vi.mock('./api/coefficients', () => ({ fetchCoefficientGroups: vi.fn() }));
vi.mock('./api/workflowTemplates', async (orig) => ({
  ...(await orig<typeof import('./api/workflowTemplates')>()),
  fetchCompatibleTemplates: vi.fn(async () => ({ items: [], total: 0 })),
}));

const S = 'surf-1';

function item(id: string, name: string, extra: Partial<SurfacePriceItemSummaryRead> = {}): SurfacePriceItemSummaryRead {
  return {
    id, code: id.toUpperCase(), name_key: null, display_name: name, category: 'PREPARATION', unit: 'M2',
    price_scope: 'LABOR', price: '10.00', currency: 'PLN', is_archived: false, quality_level: null, ...extra,
  };
}
const PRIME = item('p1', 'Gruntowanie');
const SKIM = item('p2', 'Gładź szpachlowa — bardzo długa nazwa pozycji do sprawdzenia zawijania na wąskim ekranie');

function work(id: string, key: string, priceItem: SurfacePriceItemSummaryRead, wait: number | null, extra: Partial<SurfacePlannedWorkRead> = {}): SurfacePlannedWorkRead {
  return {
    id, work_plan_id: 'plan-1', price_item_id: priceItem.id, position: 0, occurrence_key: key,
    wait_after_hours: wait, price_item: priceItem, coefficient_options: [], ...extra,
  };
}
const COEF = { id: 'opt-1', group_id: 'g-1', group_code: 'H', code: 'HIGH', display_name: 'Wysokość', percentage: '15.00', is_base: false };

function plan(works: SurfacePlannedWorkRead[]): SurfaceWorkPlanRead {
  return { id: 'plan-1', surface_id: S, substrate: 'CONCRETE', quality_target: 'S2', planned_works: works, template_applications: [] };
}
// A template-applied block: Gruntowanie (24 h) -> Gładź (48 h) -> Gruntowanie again (no break), last work with a break.
const PLAN = plan([
  work('w1', 'key-1', PRIME, 24, { coefficient_options: [COEF] }),
  work('w2', 'key-2', SKIM, 48),
  work('w3', 'key-3', PRIME, null),
  work('w4', 'key-4', SKIM, 12),
]);

function renderEditor() {
  return render(
    <I18nProvider>
      <SurfaceWorkPlanEditor projectId="p" roomId="r" surfaceId={S} surfaceName="Ściana" surfaceType="WALL" onClose={vi.fn()} />
    </I18nProvider>,
  );
}
const cards = () => within(screen.getByLabelText(`planned-works-${S}`)).getAllByRole('listitem');
const keyOf = (i: number) => cards()[i].getAttribute('aria-label')!.replace('draft-occurrence-', '');
const savedPayload = () => vi.mocked(workPlansApi.putSurfaceWorkPlan).mock.calls[0][3] as SurfaceWorkPlanUpsert;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(PLAN);
  vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(PLAN);
  vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [], total: 0 });
});

describe('display (13G)', () => {
  it('numbers the works and shows each break without opening anything; no break shows nothing', async () => {
    renderEditor();
    await screen.findByLabelText(`planned-works-${S}`);
    expect(cards()[0]).toHaveTextContent('1. Gruntowanie');
    expect(cards()[1]).toHaveTextContent('2. Gładź');
    expect(screen.getByLabelText(`occurrence-wait-${keyOf(0)}`)).toHaveTextContent('Przerwa technologiczna po tej pracy: 24 h · 1 dzień');
    expect(screen.getByLabelText(`occurrence-wait-${keyOf(1)}`)).toHaveTextContent('48 h · 2 dni');
    expect(screen.queryByLabelText(`occurrence-wait-${keyOf(2)}`)).toBeNull(); // null -> clean
    // the LAST work keeps its own break (it is not deleted for lack of a next step)
    expect(screen.getByLabelText(`occurrence-wait-${keyOf(3)}`)).toHaveTextContent('12 h');
    expect(screen.getByLabelText(`occurrence-wait-${keyOf(3)}`)).not.toHaveTextContent('dzień');
    // coefficient UI intact
    expect(screen.getByLabelText(`occurrence-coefficient-summary-${keyOf(0)}`)).toBeInTheDocument();
    // progressive disclosure: no hours input until asked
    expect(screen.queryByLabelText(`wait-input-${keyOf(0)}`)).toBeNull();
    expect(screen.getByLabelText(`save-work-plan-${S}`)).toBeDisabled();
  });

  it('renders in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderEditor();
    await screen.findByLabelText(`planned-works-${S}`);
    expect(screen.getByLabelText(`occurrence-wait-${keyOf(0)}`)).toHaveTextContent('Технологическая пауза после этой работы: 24 ч · 1 день');
    expect(screen.getByLabelText(`occurrence-wait-${keyOf(1)}`)).toHaveTextContent('48 ч · 2 дня');
    fireEvent.click(screen.getByLabelText(`edit-wait-${keyOf(2)}`));
    expect(cards()[2]).toHaveTextContent('Количество часов');
    expect(screen.getByLabelText(`wait-input-${keyOf(2)}`)).toHaveAttribute('placeholder', 'Пауза не задана');
  });
});

describe('editing (13G)', () => {
  it('edits one occurrence, clears another; siblings with the same PriceItem are independent; save keeps keys and coefficients', async () => {
    renderEditor();
    await screen.findByLabelText(`planned-works-${S}`);
    fireEvent.click(screen.getByLabelText(`edit-wait-${keyOf(2)}`));
    const input = screen.getByLabelText(`wait-input-${keyOf(2)}`);
    expect(input).toHaveAttribute('inputMode', 'numeric');
    fireEvent.change(input, { target: { value: '72' } });
    expect(screen.getByLabelText(`occurrence-wait-${keyOf(2)}`)).toHaveTextContent('72 h · 3 dni');
    expect(screen.getByLabelText(`occurrence-wait-${keyOf(0)}`)).toHaveTextContent('24 h'); // same PriceItem, untouched
    fireEvent.click(screen.getByLabelText(`edit-wait-${keyOf(1)}`));
    fireEvent.change(screen.getByLabelText(`wait-input-${keyOf(1)}`), { target: { value: '' } });
    expect(screen.queryByLabelText(`occurrence-wait-${keyOf(1)}`)).toBeNull();
    fireEvent.click(screen.getByLabelText(`save-work-plan-${S}`));
    await waitFor(() => expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(1));
    expect(savedPayload().planned_works).toEqual([
      { price_item_id: 'p1', occurrence_key: 'key-1', wait_after_hours: 24, coefficient_option_ids: ['opt-1'] },
      { price_item_id: 'p2', occurrence_key: 'key-2', wait_after_hours: null, coefficient_option_ids: [] },
      { price_item_id: 'p1', occurrence_key: 'key-3', wait_after_hours: 72, coefficient_option_ids: [] },
      { price_item_id: 'p2', occurrence_key: 'key-4', wait_after_hours: 12, coefficient_option_ids: [] },
    ]);
  });

  it('rejects 0, fractions and text inline and never submits them', async () => {
    renderEditor();
    await screen.findByLabelText(`planned-works-${S}`);
    fireEvent.click(screen.getByLabelText(`edit-wait-${keyOf(0)}`));
    for (const bad of ['0', '1.5', '2,5', 'abc', '-3']) {
      fireEvent.change(screen.getByLabelText(`wait-input-${keyOf(0)}`), { target: { value: bad } });
      expect(within(cards()[0]).getByRole('alert')).toHaveTextContent('Podaj pełną liczbę godzin');
      expect(screen.getByLabelText(`save-work-plan-${S}`)).toBeDisabled();
    }
    fireEvent.change(screen.getByLabelText(`wait-input-${keyOf(0)}`), { target: { value: '24' } });
    expect(screen.getByLabelText(`save-work-plan-${S}`)).toBeDisabled(); // back to the loaded value: not dirty
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
  });

  it('an unrelated edit (quality target) preserves every wait, key and coefficient', async () => {
    renderEditor();
    await screen.findByLabelText(`planned-works-${S}`);
    fireEvent.change(screen.getByLabelText(`work-plan-quality-${S}`), { target: { value: 'S3' } });
    fireEvent.click(screen.getByLabelText(`save-work-plan-${S}`));
    await waitFor(() => expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(1));
    expect(savedPayload().quality_target).toBe('S3');
    expect(savedPayload().planned_works!.map((w) => [w.occurrence_key, w.wait_after_hours, w.coefficient_option_ids])).toEqual([
      ['key-1', 24, ['opt-1']], ['key-2', 48, []], ['key-3', null, []], ['key-4', 12, []],
    ]);
  });

  it('reorder moves the break with its occurrence', async () => {
    renderEditor();
    await screen.findByLabelText(`planned-works-${S}`);
    fireEvent.click(screen.getByLabelText(`move-down-occurrence-${keyOf(0)}`));
    expect(cards()[1]).toHaveTextContent('2. Gruntowanie');
    expect(within(cards()[1]).getByText(/24 h/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(`save-work-plan-${S}`));
    await waitFor(() => expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(1));
    expect(savedPayload().planned_works!.map((w) => [w.occurrence_key, w.wait_after_hours])).toEqual([
      ['key-2', 48], ['key-1', 24], ['key-3', null], ['key-4', 12],
    ]);
  });

  it('a long work name and the break both wrap (no fixed-width layout)', async () => {
    renderEditor();
    await screen.findByLabelText(`planned-works-${S}`);
    expect(cards()[1].querySelector('span.break-words')).not.toBeNull();
    expect(screen.getByLabelText(`occurrence-wait-${keyOf(1)}`).className).toContain('break-words');
    expect(screen.getByLabelText(`edit-wait-${keyOf(1)}`).className).toContain('min-h-[44px]');
  });
});
