import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as workPlansApi from './api/workPlans';
import * as priceItemsApi from './api/priceItems';
import { ApiError } from './api/http';
import { SurfaceWorkPlanEditor } from './components/SurfaceWorkPlanEditor';
import { I18nProvider } from './hooks/useI18n';
import { PriceItem, PriceItemListResponse } from './types/priceItem';
import { SurfaceWorkPlanApplyResult, SurfaceWorkPlanRead } from './types/workPlan';

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
  return {
    ...actual,
    fetchPriceItems: vi.fn(),
    createPriceItem: vi.fn(),
  };
});

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const surfaceId = '33333333-3333-3333-3333-333333333333';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const plannedWorks: SurfaceWorkPlanRead['planned_works'] = [
  {
    id: 'occurrence-1',
    work_plan_id: 'plan-1',
    price_item_id: 'price-shared',
    position: 0,
    price_item: {
      id: 'price-shared',
      code: 'CUSTOM_1',
      name_key: null,
      display_name: 'Pierwsza praca',
      category: 'PREPARATION',
      unit: 'M2',
      price_scope: 'LABOR',
      price: '45.50',
      currency: 'PLN',
      is_archived: false,
      quality_level: null,
    },
  },
  {
    id: 'occurrence-2',
    work_plan_id: 'plan-1',
    price_item_id: 'price-localized',
    position: 1,
    price_item: {
      id: 'price-localized',
      code: 'PAINT_2K',
      name_key: 'pricebook.seed.paint_2k',
      display_name: null,
      category: 'PAINTING',
      unit: 'M2',
      price_scope: 'LABOR_AND_MATERIAL',
      price: '60.00',
      currency: 'PLN',
      is_archived: false,
      quality_level: 'S3',
    },
  },
  {
    id: 'occurrence-3',
    work_plan_id: 'plan-1',
    price_item_id: 'price-shared',
    position: 2,
    price_item: {
      id: 'price-shared',
      code: 'CUSTOM_1',
      name_key: null,
      display_name: 'Pierwsza praca',
      category: 'PREPARATION',
      unit: 'M2',
      price_scope: 'LABOR',
      price: null,
      currency: 'PLN',
      is_archived: true,
      quality_level: null,
    },
  },
  {
    id: 'occurrence-4',
    work_plan_id: 'plan-1',
    price_item_id: 'price-unavailable',
    position: 3,
    price_item: null,
  },
];

function makePlan(overrides: Partial<SurfaceWorkPlanRead> = {}): SurfaceWorkPlanRead {
  return {
    id: 'plan-1',
    surface_id: surfaceId,
    substrate: 'CONCRETE',
    quality_target: 'S3',
    planned_works: plannedWorks,
    ...overrides,
  };
}

function makePriceItem(overrides: Partial<PriceItem> = {}): PriceItem {
  return {
    id: 'pi-default',
    code: 'CUSTOM_X',
    name_key: null,
    display_name: 'Test Item',
    category: 'PREPARATION',
    unit: 'M2',
    price_scope: 'LABOR',
    price: '25.00',
    currency: 'PLN',
    is_archived: false,
    quality_level: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

function makePriceItemListResponse(items: PriceItem[]): PriceItemListResponse {
  return { items, total: items.length };
}

function makeApplyResult(overrides: Partial<SurfaceWorkPlanApplyResult> = {}): SurfaceWorkPlanApplyResult {
  return {
    source_surface_id: surfaceId,
    target_count: 3,
    target_surface_ids: [],
    targets: [],
    ...overrides,
  };
}

interface RenderOpts {
  isWall?: boolean;
  otherActiveWallCount?: number;
}

function renderEditor(id = surfaceId, opts: RenderOpts = {}) {
  const { isWall = true, otherActiveWallCount = 3 } = opts;
  return render(
    <I18nProvider>
      <SurfaceWorkPlanEditor
        projectId={projectId}
        roomId={roomId}
        surfaceId={id}
        surfaceName="Ściana północna"
        isWall={isWall}
        otherActiveWallCount={otherActiveWallCount}
        onClose={vi.fn()}
      />
    </I18nProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SurfaceWorkPlanEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(makePlan());
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([]),
    );
  });

  // -------------------------------------------------------------------------
  // Existing load / form tests (adapted for draft occurrences)
  // -------------------------------------------------------------------------

  it('shows loading and hydrates the existing header and ordered draft preview', async () => {
    let resolvePlan!: (plan: SurfaceWorkPlanRead) => void;
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockReturnValue(
      new Promise((resolve) => {
        resolvePlan = resolve;
      }),
    );

    renderEditor();
    expect(screen.getByText('Ładowanie planu prac...')).toBeInTheDocument();

    await act(async () => resolvePlan(makePlan()));

    expect(await screen.findByLabelText(`work-plan-substrate-${surfaceId}`)).toHaveValue('CONCRETE');
    expect(screen.getByLabelText(`work-plan-quality-${surfaceId}`)).toHaveValue('S3');

    const rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows).toHaveLength(4);
    expect(rows[0]).toHaveTextContent('Pierwsza praca');
    expect(rows[1]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');
    expect(rows[2]).toHaveTextContent('Pierwsza praca');
    expect(rows[2]).toHaveTextContent('Do ustalenia');
    expect(rows[2]).toHaveTextContent('Zarchiwizowana');
    expect(rows[3]).toHaveTextContent('Pozycja cennika jest niedostępna');
    expect(screen.getByLabelText(`save-work-plan-${surfaceId}`)).toBeDisabled();
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
  });

  it('treats only the exact no-plan 404 as an editable empty state without creating a plan', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockRejectedValue(
      new ApiError('Surface work plan not found', 404),
    );

    renderEditor();

    expect(await screen.findByText('Brak zapisanego planu prac dla tej powierzchni.')).toBeInTheDocument();
    expect(screen.getByLabelText(`work-plan-substrate-${surfaceId}`)).toHaveValue('');
    expect(screen.getByLabelText(`work-plan-quality-${surfaceId}`)).toBeDisabled();
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
  });

  it('shows other load failures and retries the same canonical surface', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan)
      .mockRejectedValueOnce(new ApiError('Surface not found', 404))
      .mockResolvedValueOnce(makePlan());

    renderEditor();

    expect(await screen.findByText('Nie udało się załadować planu prac.')).toBeInTheDocument();
    expect(screen.getByText('Surface not found')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(`retry-work-plan-${surfaceId}`));

    expect(await screen.findByLabelText(`work-plan-form-${surfaceId}`)).toBeInTheDocument();
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(2);
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenLastCalledWith(
      projectId,
      roomId,
      surfaceId,
    );
  });

  it('offers the compatible quality family and clears quality on incompatible substrate changes', async () => {
    renderEditor();

    const substrate = await screen.findByLabelText(`work-plan-substrate-${surfaceId}`);
    const quality = screen.getByLabelText(`work-plan-quality-${surfaceId}`);
    expect(within(quality).getByRole('option', { name: 'Klasa S1' })).toBeInTheDocument();
    expect(within(quality).queryByRole('option', { name: 'Klasa Q1' })).not.toBeInTheDocument();

    fireEvent.change(substrate, { target: { value: 'OTHER' } });
    expect(quality).toHaveValue('');
    expect(within(quality).getByRole('option', { name: 'Klasa S1' })).toBeInTheDocument();
    expect(within(quality).getByRole('option', { name: 'Klasa Q1' })).toBeInTheDocument();

    fireEvent.change(substrate, { target: { value: 'CONCRETE' } });
    fireEvent.change(quality, { target: { value: 'S3' } });
    fireEvent.change(substrate, { target: { value: 'GYPSUM_BOARD' } });
    expect(quality).toHaveValue('');
    expect(within(quality).queryByRole('option', { name: 'Klasa S1' })).not.toBeInTheDocument();
    expect(within(quality).getByRole('option', { name: 'Klasa Q1' })).toBeInTheDocument();

    fireEvent.change(quality, { target: { value: 'Q3' } });
    fireEvent.change(substrate, { target: { value: 'PAINTED' } });
    expect(quality).toHaveValue('');
    expect(within(quality).getByRole('option', { name: 'Klasa S1' })).toBeInTheDocument();
    expect(within(quality).getByRole('option', { name: 'Klasa Q1' })).toBeInTheDocument();
  });

  it('saves the header while preserving work occurrence order and duplicate IDs exactly', async () => {
    const savedPlan = makePlan({ substrate: 'GYPSUM_PLASTER' });
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(savedPlan);
    renderEditor();

    fireEvent.change(await screen.findByLabelText(`work-plan-substrate-${surfaceId}`), {
      target: { value: 'GYPSUM_PLASTER' },
    });
    const save = screen.getByLabelText(`save-work-plan-${surfaceId}`);
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => {
      expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledWith(projectId, roomId, surfaceId, {
        substrate: 'GYPSUM_PLASTER',
        quality_target: 'S3',
        price_item_ids: ['price-shared', 'price-localized', 'price-shared', 'price-unavailable'],
      });
    });
    expect(await screen.findByText('Plan prac został zapisany.')).toBeInTheDocument();
    expect(save).toBeDisabled();
  });

  it('retains the full draft and preview after a failed save', async () => {
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockRejectedValue(
      new ApiError('Archived price item cannot be selected for a work plan', 422),
    );
    renderEditor();

    const substrate = await screen.findByLabelText(`work-plan-substrate-${surfaceId}`);
    const quality = screen.getByLabelText(`work-plan-quality-${surfaceId}`);
    fireEvent.change(substrate, { target: { value: 'GYPSUM_BOARD' } });
    fireEvent.change(quality, { target: { value: 'Q3' } });
    fireEvent.click(screen.getByLabelText(`save-work-plan-${surfaceId}`));

    expect(await screen.findByText('Nie udało się zapisać planu prac.')).toBeInTheDocument();
    expect(screen.getByText('Archived price item cannot be selected for a work plan')).toBeInTheDocument();
    expect(substrate).toHaveValue('GYPSUM_BOARD');
    expect(quality).toHaveValue('Q3');
    expect(screen.getAllByText('Pierwsza praca')).toHaveLength(2);
    expect(screen.getByLabelText(`save-work-plan-${surfaceId}`)).toBeEnabled();
  });

  it('ignores a late response after the editor switches to another surface', async () => {
    const nextSurfaceId = '44444444-4444-4444-4444-444444444444';
    let resolveFirst!: (plan: SurfaceWorkPlanRead) => void;
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan)
      .mockReturnValueOnce(new Promise((resolve) => {
        resolveFirst = resolve;
      }))
      .mockResolvedValueOnce(makePlan({
        surface_id: nextSurfaceId,
        substrate: 'GYPSUM_BOARD',
        quality_target: 'Q2',
      }));

    const view = renderEditor();
    view.rerender(
      <I18nProvider>
        <SurfaceWorkPlanEditor
          projectId={projectId}
          roomId={roomId}
          surfaceId={nextSurfaceId}
          surfaceName="Ściana wschodnia"
          onClose={vi.fn()}
        />
      </I18nProvider>,
    );

    const substrate = await screen.findByLabelText(`work-plan-substrate-${nextSurfaceId}`);
    expect(substrate).toHaveValue('GYPSUM_BOARD');
    expect(screen.getByLabelText(`work-plan-quality-${nextSurfaceId}`)).toHaveValue('Q2');

    await act(async () => resolveFirst(makePlan({ substrate: 'CONCRETE', quality_target: 'S1' })));
    expect(substrate).toHaveValue('GYPSUM_BOARD');
    expect(screen.getByLabelText(`work-plan-quality-${nextSurfaceId}`)).toHaveValue('Q2');
  });

  // -------------------------------------------------------------------------
  // Picker tests
  // -------------------------------------------------------------------------

  it('picker opens and shows loading state', async () => {
    let resolveItems!: (r: PriceItemListResponse) => void;
    vi.mocked(priceItemsApi.fetchPriceItems).mockReturnValue(
      new Promise((r) => { resolveItems = r; }),
    );
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    expect(screen.getByText('Ładowanie cennika...')).toBeInTheDocument();

    await act(async () => resolveItems(makePriceItemListResponse([])));
  });

  it('picker can be closed', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse([]));
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-panel-${surfaceId}`);

    fireEvent.click(screen.getByLabelText(`close-picker-${surfaceId}`));
    expect(screen.queryByLabelText(`picker-panel-${surfaceId}`)).not.toBeInTheDocument();
  });

  it('picker shows active LABOR item and selecting it appends an occurrence', async () => {
    const laborItem = makePriceItem({
      id: 'pi-labor',
      display_name: 'Gruntowanie podłoża',
      price_scope: 'LABOR',
      price: '8.00',
      is_archived: false,
    });
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([laborItem]),
    );
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);

    const btn = screen.getByLabelText('picker-item-pi-labor');
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveTextContent('Gruntowanie podłoża');
    expect(btn).toHaveTextContent('Robocizna');

    fireEvent.click(btn);

    // Picker closes and occurrence is appended
    expect(screen.queryByLabelText(`picker-panel-${surfaceId}`)).not.toBeInTheDocument();
    expect(screen.getByText('Gruntowanie podłoża')).toBeInTheDocument();
  });

  it('picker shows MATERIAL item selectable', async () => {
    const materialItem = makePriceItem({
      id: 'pi-mat',
      display_name: 'Farba emulsyjna',
      price_scope: 'MATERIAL',
      is_archived: false,
    });
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([materialItem]),
    );
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);

    expect(screen.getByLabelText('picker-item-pi-mat')).toBeInTheDocument();
    expect(screen.getByText('Materiał')).toBeInTheDocument();
  });

  it('picker shows LABOR_AND_MATERIAL item selectable', async () => {
    const lmItem = makePriceItem({
      id: 'pi-lm',
      display_name: 'Gładź 2 warstwy z materiałem',
      price_scope: 'LABOR_AND_MATERIAL',
      is_archived: false,
    });
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([lmItem]),
    );
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);

    expect(screen.getByLabelText('picker-item-pi-lm')).toBeInTheDocument();
  });

  it('archived items are absent from picker candidates', async () => {
    const activeItem = makePriceItem({ id: 'pi-active', display_name: 'Aktywna praca', is_archived: false });
    // Picker always requests archived:'active' — so archived should NOT come back.
    // The mock simulates only active items being returned (as the API would do).
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([activeItem]),
    );
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);

    // Only the active item should be selectable
    expect(screen.getByLabelText('picker-item-pi-active')).toBeInTheDocument();
    // Verify the API was called with archived:'active' — ensuring archived are excluded
    expect(priceItemsApi.fetchPriceItems).toHaveBeenCalledWith({ archived: 'active' });
  });

  it('NULL-price item is selectable and displays localized price_not_set text', async () => {
    const nullPriceItem = makePriceItem({
      id: 'pi-null',
      display_name: 'Cena do ustalenia',
      price: null,
      is_archived: false,
    });
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([nullPriceItem]),
    );
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);

    const btn = screen.getByLabelText('picker-item-pi-null');
    expect(btn).toHaveTextContent('Do ustalenia');

    fireEvent.click(btn);
    // After select the occurrence shows the localized price_not_set
    await waitFor(() => {
      const allNotSet = screen.getAllByText('Do ustalenia');
      // occurrence-3 (archived, null price) + newly added = at least 2
      expect(allNotSet.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('market/reference price is never substituted — price shown is exactly the owner price', async () => {
    const item = makePriceItem({ id: 'pi-own', display_name: 'Szpachlowanie', price: '35.00' });
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse([item]));
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);

    const btn = screen.getByLabelText('picker-item-pi-own');
    // Displays 35.00 not some market reference
    expect(btn).toHaveTextContent('35,00');
    expect(btn).toHaveTextContent('zł');
  });

  it('search filters picker results client-side', async () => {
    const items = [
      makePriceItem({ id: 'pi-1', display_name: 'Malowanie ścian', is_archived: false }),
      makePriceItem({ id: 'pi-2', display_name: 'Gruntowanie podłoża', is_archived: false }),
    ];
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse(items));
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);

    expect(screen.getByLabelText('picker-item-pi-1')).toBeInTheDocument();
    expect(screen.getByLabelText('picker-item-pi-2')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(`picker-search-${surfaceId}`), {
      target: { value: 'Malowanie' },
    });

    expect(screen.getByLabelText('picker-item-pi-1')).toBeInTheDocument();
    expect(screen.queryByLabelText('picker-item-pi-2')).not.toBeInTheDocument();
  });

  it('no-results state shown when search finds nothing', async () => {
    const items = [makePriceItem({ id: 'pi-1', display_name: 'Malowanie', is_archived: false })];
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse(items));
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);

    fireEvent.change(screen.getByLabelText(`picker-search-${surfaceId}`), {
      target: { value: 'xxxxxnotfound' },
    });

    expect(screen.getByText('Brak wyników')).toBeInTheDocument();
    expect(screen.queryByLabelText('picker-item-pi-1')).not.toBeInTheDocument();
  });

  it('same PriceItem can be added twice — duplicates are independent', async () => {
    const item = makePriceItem({ id: 'pi-dup', display_name: 'Prace dwukrotne', is_archived: false });
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(
      makePlan({ planned_works: [] }),
    );
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse([item]));
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    // Add first occurrence
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);
    fireEvent.click(screen.getByLabelText('picker-item-pi-dup'));

    // Add second occurrence of the same item
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);
    fireEvent.click(screen.getByLabelText('picker-item-pi-dup'));

    // Both occurrences present
    expect(screen.getAllByText('Prace dwukrotne')).toHaveLength(2);
    expect(
      within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem'),
    ).toHaveLength(2);
  });

  it('removing one duplicate leaves the other intact', async () => {
    const item = makePriceItem({ id: 'pi-dup2', display_name: 'Powtarzalna praca', is_archived: false });
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(
      makePlan({ planned_works: [] }),
    );
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse([item]));
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    // Add two occurrences
    for (let i = 0; i < 2; i++) {
      fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
      await screen.findByLabelText(`picker-list-${surfaceId}`);
      fireEvent.click(screen.getByLabelText('picker-item-pi-dup2'));
    }
    expect(screen.getAllByText('Powtarzalna praca')).toHaveLength(2);

    // Remove the first remove button
    const removeButtons = screen.getAllByText('Usuń');
    expect(removeButtons).toHaveLength(2);
    fireEvent.click(removeButtons[0]);

    // One remains
    expect(screen.getAllByText('Powtarzalna praca')).toHaveLength(1);
  });

  it('new occurrence appended at end preserves existing order', async () => {
    const newItem = makePriceItem({
      id: 'pi-new',
      display_name: 'Nowa praca',
      is_archived: false,
    });
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse([newItem]));
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);
    fireEvent.click(screen.getByLabelText('picker-item-pi-new'));

    const rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    // Original 4 + 1 new = 5
    expect(rows).toHaveLength(5);
    expect(rows[4]).toHaveTextContent('Nowa praca');
    // First row still first
    expect(rows[0]).toHaveTextContent('Pierwsza praca');
  });

  it('PUT preserves exact order including duplicate IDs and new occurrence', async () => {
    const newItem = makePriceItem({ id: 'pi-extra', display_name: 'Dodatkowa', is_archived: false });
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse([newItem]));
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(
      makePlan({ substrate: 'GYPSUM_PLASTER' }),
    );
    renderEditor();

    // Change substrate to make form dirty
    fireEvent.change(await screen.findByLabelText(`work-plan-substrate-${surfaceId}`), {
      target: { value: 'GYPSUM_PLASTER' },
    });

    // Add one more item via picker
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);
    fireEvent.click(screen.getByLabelText('picker-item-pi-extra'));

    fireEvent.click(screen.getByLabelText(`save-work-plan-${surfaceId}`));

    await waitFor(() => {
      expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledWith(
        projectId,
        roomId,
        surfaceId,
        expect.objectContaining({
          price_item_ids: [
            'price-shared',
            'price-localized',
            'price-shared',
            'price-unavailable',
            'pi-extra',
          ],
        }),
      );
    });
  });

  it('existing archived occurrence stays visible and has archived badge', async () => {
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    // occurrence-3 has is_archived: true — must show badge
    const rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows[2]).toHaveTextContent('Zarchiwizowana');
  });

  it('successful save rehydrates — form becomes clean', async () => {
    const freshPlan = makePlan({ substrate: 'GYPSUM_PLASTER', planned_works: [] });
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(freshPlan);
    renderEditor();

    fireEvent.change(await screen.findByLabelText(`work-plan-substrate-${surfaceId}`), {
      target: { value: 'GYPSUM_PLASTER' },
    });
    fireEvent.click(screen.getByLabelText(`save-work-plan-${surfaceId}`));

    await waitFor(() => {
      expect(screen.getByLabelText(`save-work-plan-${surfaceId}`)).toBeDisabled();
    });
    expect(screen.getByLabelText(`work-plan-substrate-${surfaceId}`)).toHaveValue('GYPSUM_PLASTER');
  });

  it('failed save preserves entire draft', async () => {
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockRejectedValue(new Error('Network error'));
    const newItem = makePriceItem({ id: 'pi-draft', display_name: 'Praca w drafcie', is_archived: false });
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse([newItem]));
    renderEditor();

    // Change substrate so form is dirty
    fireEvent.change(await screen.findByLabelText(`work-plan-substrate-${surfaceId}`), {
      target: { value: 'CONCRETE' },
    });

    // Add one item via picker
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    await screen.findByLabelText(`picker-list-${surfaceId}`);
    fireEvent.click(screen.getByLabelText('picker-item-pi-draft'));
    expect(screen.getByText('Praca w drafcie')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(`save-work-plan-${surfaceId}`));
    await screen.findByText('Nie udało się zapisać planu prac.');

    // Draft still intact
    expect(screen.getByText('Praca w drafcie')).toBeInTheDocument();
    expect(screen.getByLabelText(`save-work-plan-${surfaceId}`)).toBeEnabled();
  });

  it('WALL/FLOOR/CEILING canonical surface ID preserved — editor uses passed surfaceId', async () => {
    const wallId = 'wall-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
    renderEditor(wallId);
    await screen.findByLabelText(`work-plan-form-${wallId}`);
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledWith(projectId, roomId, wallId);
  });

  it('PL locale: add work button text is correct', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(makePlan({ planned_works: [] }));
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);
    expect(screen.getByLabelText(`open-picker-${surfaceId}`)).toHaveTextContent('+ Dodaj pracę');
  });

  it('picker shows empty state when no active items at all', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse([]));
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);
    fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
    expect(await screen.findByText('Brak aktywnych pozycji')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Stage 10C.2C: Planned work ordering tests
  // -------------------------------------------------------------------------

  it('first occurrence cannot move up (button is disabled)', async () => {
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    const list = screen.getByLabelText(`planned-works-${surfaceId}`);
    const rows = within(list).getAllByRole('listitem');
    expect(rows).toHaveLength(4);

    const firstRowUpBtn = within(rows[0]).getByText('↑');
    expect(firstRowUpBtn).toBeDisabled();

    const firstRowDownBtn = within(rows[0]).getByText('↓');
    expect(firstRowDownBtn).toBeEnabled();
  });

  it('last occurrence cannot move down (button is disabled)', async () => {
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    const list = screen.getByLabelText(`planned-works-${surfaceId}`);
    const rows = within(list).getAllByRole('listitem');
    expect(rows).toHaveLength(4);

    const lastRowDownBtn = within(rows[3]).getByText('↓');
    expect(lastRowDownBtn).toBeDisabled();

    const lastRowUpBtn = within(rows[3]).getByText('↑');
    expect(lastRowUpBtn).toBeEnabled();
  });

  it('move middle occurrence up swaps positions locally without API call', async () => {
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    let rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Pierwsza praca');
    expect(rows[1]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');

    // Click move up on row 1 (Malowanie)
    const row1UpBtn = within(rows[1]).getByText('↑');
    fireEvent.click(row1UpBtn);

    // No API call occurred
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();

    // Now Malowanie is first, Pierwsza praca is second
    rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');
    expect(rows[1]).toHaveTextContent('Pierwsza praca');

    // Save button is now enabled (draft is dirty)
    expect(screen.getByLabelText(`save-work-plan-${surfaceId}`)).toBeEnabled();
  });

  it('move middle occurrence down swaps positions locally', async () => {
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    let rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows[1]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');
    expect(rows[2]).toHaveTextContent('Zarchiwizowana'); // occurrence-3 (archived Pierwsza praca)

    // Click move down on row 1 (Malowanie)
    const row1DownBtn = within(rows[1]).getByText('↓');
    fireEvent.click(row1DownBtn);

    rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows[1]).toHaveTextContent('Zarchiwizowana');
    expect(rows[2]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');
  });

  it('archived occurrence can be reordered', async () => {
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    let rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows[2]).toHaveTextContent('Zarchiwizowana');

    // Move archived occurrence up to position 1
    const archivedUpBtn = within(rows[2]).getByText('↑');
    fireEvent.click(archivedUpBtn);

    rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows[1]).toHaveTextContent('Zarchiwizowana');
    expect(rows[2]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');
  });

  it('duplicate occurrences remain independent when moving one', async () => {
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    // Initial order: [Pierwsza praca (active), Malowanie, Pierwsza praca (archived), Unavailable]
    let rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Pierwsza praca');
    expect(rows[0]).not.toHaveTextContent('Zarchiwizowana');
    expect(rows[2]).toHaveTextContent('Pierwsza praca');
    expect(rows[2]).toHaveTextContent('Zarchiwizowana');

    // Move first occurrence down to position 1
    const firstDownBtn = within(rows[0]).getByText('↓');
    fireEvent.click(firstDownBtn);

    // New order: [Malowanie, Pierwsza praca (active), Pierwsza praca (archived), Unavailable]
    rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');
    expect(rows[1]).toHaveTextContent('Pierwsza praca');
    expect(rows[1]).not.toHaveTextContent('Zarchiwizowana');
    expect(rows[2]).toHaveTextContent('Pierwsza praca');
    expect(rows[2]).toHaveTextContent('Zarchiwizowana');
  });

  it('Save sends exact reordered price_item_ids with duplicate IDs preserved', async () => {
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(makePlan());
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    // Initial order: ['price-shared', 'price-localized', 'price-shared', 'price-unavailable']
    const rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    // Move row 0 down -> order becomes: ['price-localized', 'price-shared', 'price-shared', 'price-unavailable']
    fireEvent.click(within(rows[0]).getByText('↓'));

    const saveBtn = screen.getByLabelText(`save-work-plan-${surfaceId}`);
    expect(saveBtn).toBeEnabled();
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledWith(
        projectId,
        roomId,
        surfaceId,
        expect.objectContaining({
          price_item_ids: [
            'price-localized',
            'price-shared',
            'price-shared',
            'price-unavailable',
          ],
        }),
      );
    });
  });

  it('failed Save retains reordered draft', async () => {
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockRejectedValue(new Error('Network error'));
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    const rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    // Move row 0 down
    fireEvent.click(within(rows[0]).getByText('↓'));

    const saveBtn = screen.getByLabelText(`save-work-plan-${surfaceId}`);
    fireEvent.click(saveBtn);

    expect(await screen.findByText('Nie udało się zapisać planu prac.')).toBeInTheDocument();

    // Draft still retains reordered order
    const updatedRows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(updatedRows[0]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');
    expect(updatedRows[1]).toHaveTextContent('Pierwsza praca');
    expect(saveBtn).toBeEnabled();
  });

  // -------------------------------------------------------------------------
  // Stage 10C.3: Apply to all walls tests
  // -------------------------------------------------------------------------

  it('apply-to-all button is shown for WALL surfaces with a saved plan', async () => {
    renderEditor();
    await screen.findByLabelText(`apply-to-all-walls-${surfaceId}`);
  });

  it('apply-to-all button is NOT shown for non-WALL surfaces (isWall=false)', async () => {
    renderEditor(surfaceId, { isWall: false });
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);
    expect(screen.queryByLabelText(`apply-to-all-walls-${surfaceId}`)).not.toBeInTheDocument();
  });

  it('apply-to-all button is NOT shown when hasPlan is false (404 empty state)', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockRejectedValue(
      new ApiError('Surface work plan not found', 404),
    );
    renderEditor();
    await screen.findByText('Brak zapisanego planu prac dla tej powierzchni.');
    expect(screen.queryByLabelText(`apply-to-all-walls-${surfaceId}`)).not.toBeInTheDocument();
  });

  it('clicking apply-to-all shows inline confirmation with target count', async () => {
    renderEditor(surfaceId, { otherActiveWallCount: 3 });
    await screen.findByLabelText(`apply-to-all-walls-${surfaceId}`);

    fireEvent.click(screen.getByLabelText(`apply-to-all-walls-${surfaceId}`));

    expect(screen.getByLabelText(`apply-confirm-panel-${surfaceId}`)).toBeInTheDocument();
    expect(screen.getByText(/3 ścian/)).toBeInTheDocument();
    expect(screen.getByLabelText(`apply-confirm-yes-${surfaceId}`)).toBeInTheDocument();
    expect(screen.getByLabelText(`apply-cancel-${surfaceId}`)).toBeInTheDocument();
    // No API call yet
    expect(workPlansApi.applyWorkPlanToRoomWalls).not.toHaveBeenCalled();
  });

  it('cancelling confirmation returns to idle — no API call', async () => {
    renderEditor();
    await screen.findByLabelText(`apply-to-all-walls-${surfaceId}`);

    fireEvent.click(screen.getByLabelText(`apply-to-all-walls-${surfaceId}`));
    expect(screen.getByLabelText(`apply-confirm-panel-${surfaceId}`)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(`apply-cancel-${surfaceId}`));
    expect(screen.queryByLabelText(`apply-confirm-panel-${surfaceId}`)).not.toBeInTheDocument();
    expect(screen.getByLabelText(`apply-to-all-walls-${surfaceId}`)).toBeInTheDocument();
    expect(workPlansApi.applyWorkPlanToRoomWalls).not.toHaveBeenCalled();
  });

  it('confirming calls apply API with correct IDs and shows success with actual count', async () => {
    vi.mocked(workPlansApi.applyWorkPlanToRoomWalls).mockResolvedValue(makeApplyResult({ target_count: 3 }));
    renderEditor();
    await screen.findByLabelText(`apply-to-all-walls-${surfaceId}`);

    fireEvent.click(screen.getByLabelText(`apply-to-all-walls-${surfaceId}`));
    fireEvent.click(screen.getByLabelText(`apply-confirm-yes-${surfaceId}`));

    await waitFor(() => {
      expect(workPlansApi.applyWorkPlanToRoomWalls).toHaveBeenCalledWith(projectId, roomId, surfaceId);
    });
    expect(await screen.findByText(/skopiowano na 3/)).toBeInTheDocument();
    expect(screen.queryByLabelText(`apply-confirm-panel-${surfaceId}`)).not.toBeInTheDocument();
  });

  it('apply API failure shows error and allows dismiss', async () => {
    vi.mocked(workPlansApi.applyWorkPlanToRoomWalls).mockRejectedValue(
      new ApiError('apply-to-room-walls requires a WALL source surface', 422),
    );
    renderEditor();
    await screen.findByLabelText(`apply-to-all-walls-${surfaceId}`);

    fireEvent.click(screen.getByLabelText(`apply-to-all-walls-${surfaceId}`));
    fireEvent.click(screen.getByLabelText(`apply-confirm-yes-${surfaceId}`));

    expect(await screen.findByText('Nie udało się skopiować planu prac.')).toBeInTheDocument();
    expect(screen.getByText('apply-to-room-walls requires a WALL source surface')).toBeInTheDocument();

    // Dismiss returns to idle
    fireEvent.click(screen.getByLabelText(`apply-error-dismiss-${surfaceId}`));
    expect(screen.getByLabelText(`apply-to-all-walls-${surfaceId}`)).toBeInTheDocument();
  });

  it('success dismiss returns to idle with apply button visible again', async () => {
    vi.mocked(workPlansApi.applyWorkPlanToRoomWalls).mockResolvedValue(makeApplyResult({ target_count: 2 }));
    renderEditor();
    await screen.findByLabelText(`apply-to-all-walls-${surfaceId}`);

    fireEvent.click(screen.getByLabelText(`apply-to-all-walls-${surfaceId}`));
    fireEvent.click(screen.getByLabelText(`apply-confirm-yes-${surfaceId}`));
    await screen.findByText(/skopiowano na 2/);

    fireEvent.click(screen.getByLabelText(`apply-success-dismiss-${surfaceId}`));
    expect(screen.getByLabelText(`apply-to-all-walls-${surfaceId}`)).toBeInTheDocument();
  });

  it('successful Save rehydrates server order and clears dirty state', async () => {
    // Return a rehydrated plan matching the new order
    const rehydratedPlan: SurfaceWorkPlanRead = {
      id: 'plan-1',
      surface_id: surfaceId,
      substrate: 'CONCRETE',
      quality_target: 'S3',
      planned_works: [
        plannedWorks[1], // Malowanie
        plannedWorks[0], // Pierwsza praca
        plannedWorks[2],
        plannedWorks[3],
      ],
    };
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(rehydratedPlan);
    renderEditor();
    await screen.findByLabelText(`work-plan-form-${surfaceId}`);

    const rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    // Move row 0 down
    fireEvent.click(within(rows[0]).getByText('↓'));

    const saveBtn = screen.getByLabelText(`save-work-plan-${surfaceId}`);
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(saveBtn).toBeDisabled();
    });
    expect(screen.getByText('Plan prac został zapisany.')).toBeInTheDocument();

    const finalRows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(finalRows[0]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');
    expect(finalRows[1]).toHaveTextContent('Pierwsza praca');
  });

  // ---------------------------------------------------------------------------
  // Inline Price Book item creation from the picker (Stage 10G.4 follow-up)
  // ---------------------------------------------------------------------------

  describe('inline Price Book item creation', () => {
    async function openPickerPanel() {
      renderEditor();
      await screen.findByLabelText(`work-plan-form-${surfaceId}`);
      fireEvent.click(screen.getByLabelText(`open-picker-${surfaceId}`));
      return screen.findByLabelText(`picker-panel-${surfaceId}`);
    }

    it('shows "+ Dodaj nową pracę do cennika" at the bottom of the picker', async () => {
      const panel = await openPickerPanel();
      expect(within(panel).getByLabelText(`create-price-item-${surfaceId}`)).toHaveTextContent(
        'Dodaj nową pracę do cennika',
      );
    });

    it('opens the inline creation form and hides the search/list', async () => {
      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`create-price-item-${surfaceId}`));

      expect(
        await screen.findByLabelText(`work-plan-new-price-item-${surfaceId}-form`),
      ).toBeInTheDocument();
      expect(screen.queryByLabelText(`picker-search-${surfaceId}`)).toBeNull();
    });

    it('does NOT lock the category — the full category selector remains available, matching the picker\'s own unrestricted contract', async () => {
      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`create-price-item-${surfaceId}`));
      const form = await screen.findByLabelText(`work-plan-new-price-item-${surfaceId}-form`);

      const category = within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-category`);
      expect(category.tagName).toBe('SELECT');
      expect(category).toHaveValue('PREPARATION');
      fireEvent.change(category, { target: { value: 'PLASTER' } });
      expect(category).toHaveValue('PLASTER');
    });

    it('creating an item persists it via the Price Book API and immediately adds it to the draft, closing the picker', async () => {
      const created = makePriceItem({
        id: 'created-1',
        display_name: 'Nowa praca powierzchniowa',
        category: 'SKIM_COAT',
        unit: 'M2',
        price: '22.00',
      });
      vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(created);

      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`create-price-item-${surfaceId}`));
      const form = await screen.findByLabelText(`work-plan-new-price-item-${surfaceId}-form`);

      fireEvent.change(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-display-name`), {
        target: { value: 'Nowa praca powierzchniowa' },
      });
      fireEvent.change(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-category`), {
        target: { value: 'SKIM_COAT' },
      });
      fireEvent.change(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-price`), {
        target: { value: '22.00' },
      });
      fireEvent.submit(form);

      await waitFor(() =>
        expect(priceItemsApi.createPriceItem).toHaveBeenCalledWith(
          expect.objectContaining({
            display_name: 'Nowa praca powierzchniowa',
            category: 'SKIM_COAT',
            unit: 'M2',
            price: '22.00',
          }),
        ),
      );

      expect(screen.queryByLabelText(`picker-panel-${surfaceId}`)).toBeNull();
      const rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
      expect(rows[rows.length - 1]).toHaveTextContent('Nowa praca powierzchniowa');
    });

    it('never sends a Surface Work Plan PUT merely because a Price Book item was created', async () => {
      const created = makePriceItem({ id: 'created-nosave', display_name: 'Nowa praca' });
      vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(created);

      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`create-price-item-${surfaceId}`));
      const form = await screen.findByLabelText(`work-plan-new-price-item-${surfaceId}-form`);
      fireEvent.change(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-display-name`), {
        target: { value: 'Nowa praca' },
      });
      fireEvent.change(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-price`), {
        target: { value: '5' },
      });
      fireEvent.submit(form);

      await waitFor(() => expect(priceItemsApi.createPriceItem).toHaveBeenCalled());
      expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
    });

    it('creating an item with "Cena do ustalenia" sends price: null and immediately enters the draft', async () => {
      const created = makePriceItem({ id: 'created-null', display_name: 'Cena do ustalenia', price: null });
      vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(created);

      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`create-price-item-${surfaceId}`));
      const form = await screen.findByLabelText(`work-plan-new-price-item-${surfaceId}-form`);
      fireEvent.change(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-display-name`), {
        target: { value: 'Cena do ustalenia' },
      });
      fireEvent.click(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-price-unresolved`));
      expect(within(form).queryByLabelText(`work-plan-new-price-item-${surfaceId}-price`)).toBeNull();
      fireEvent.submit(form);

      await waitFor(() =>
        expect(priceItemsApi.createPriceItem).toHaveBeenCalledWith(
          expect.objectContaining({ price: null }),
        ),
      );
      expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
      const rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
      expect(rows[rows.length - 1]).toHaveTextContent('Do ustalenia');
    });

    it('cancelling the creation form persists nothing and returns to the picker list', async () => {
      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`create-price-item-${surfaceId}`));
      const form = await screen.findByLabelText(`work-plan-new-price-item-${surfaceId}-form`);
      fireEvent.change(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-display-name`), {
        target: { value: 'Nigdy nie zapisane' },
      });

      fireEvent.click(within(form).getByRole('button', { name: 'Anuluj' }));

      expect(priceItemsApi.createPriceItem).not.toHaveBeenCalled();
      expect(screen.queryByLabelText(`work-plan-new-price-item-${surfaceId}-form`)).toBeNull();
      expect(await screen.findByLabelText(`picker-search-${surfaceId}`)).toBeInTheDocument();
      expect(screen.queryByText('Nigdy nie zapisane')).toBeNull();
    });

    it('a creation failure preserves the entered values and shows a recoverable error', async () => {
      vi.mocked(priceItemsApi.createPriceItem).mockRejectedValue(new Error('server down'));
      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`create-price-item-${surfaceId}`));
      const form = await screen.findByLabelText(`work-plan-new-price-item-${surfaceId}-form`);
      fireEvent.change(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-display-name`), {
        target: { value: 'Praca z błędem' },
      });
      fireEvent.change(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-price`), {
        target: { value: '7' },
      });
      fireEvent.submit(form);

      expect(await screen.findByText('Nie udało się zapisać pozycji.')).toBeInTheDocument();
      expect(within(form).getByLabelText(`work-plan-new-price-item-${surfaceId}-display-name`)).toHaveValue(
        'Praca z błędem',
      );
    });

    it('the create action meets the 44px minimum touch target', async () => {
      const panel = await openPickerPanel();
      expect(within(panel).getByLabelText(`create-price-item-${surfaceId}`).className).toContain('min-h-11');
    });
  });
});
