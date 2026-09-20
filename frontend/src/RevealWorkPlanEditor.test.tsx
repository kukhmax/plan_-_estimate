import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as revealWorksApi from './api/revealWorks';
import * as priceItemsApi from './api/priceItems';
import * as surfacesApi from './api/surfaces';
import * as openingsApi from './api/openings';
import { RevealWorkPlanEditor } from './components/RevealWorkPlanEditor';
import { I18nProvider } from './hooks/useI18n';
import { OpeningListResponse, OpeningType } from './types/opening';
import { PriceItem, PriceItemListResponse } from './types/priceItem';
import { RevealWorkApplyResult, RevealWorkItemRead, RevealWorkListResponse } from './types/revealWork';
import { SurfaceListResponse, SurfaceType } from './types/surface';

vi.mock('./api/revealWorks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/revealWorks')>();
  return {
    ...actual,
    fetchRevealWorks: vi.fn(),
    putRevealWorks: vi.fn(),
    applyRevealWorksToRoom: vi.fn(),
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

vi.mock('./api/surfaces', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/surfaces')>();
  return {
    ...actual,
    fetchSurfaces: vi.fn(),
  };
});

vi.mock('./api/openings', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/openings')>();
  return {
    ...actual,
    fetchOpenings: vi.fn(),
  };
});

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const surfaceId = '33333333-3333-3333-3333-333333333333';
const openingId = '66666666-6666-6666-6666-666666666666';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const revealItems: RevealWorkItemRead[] = [
  {
    id: 'rw-1',
    position: 0,
    price_item_id: 'price-shared',
    price_item: {
      id: 'price-shared',
      code: 'REVEAL_GROUNT',
      name_key: null,
      display_name: 'Gruntowanie ościeży',
      category: 'REVEAL',
      unit: 'M2',
      price_scope: 'LABOR',
      price: '30.00',
      currency: 'PLN',
      is_archived: false,
      quality_level: null,
    },
  },
  {
    id: 'rw-2',
    position: 1,
    price_item_id: 'price-localized',
    price_item: {
      id: 'price-localized',
      code: 'REVEAL_CORNER',
      name_key: 'pricebook.seed.paint_2k',
      display_name: null,
      category: 'REVEAL',
      unit: 'LM',
      price_scope: 'MATERIAL',
      price: '15.00',
      currency: 'PLN',
      is_archived: false,
      quality_level: null,
    },
  },
  {
    id: 'rw-3',
    position: 2,
    price_item_id: 'price-shared',
    price_item: {
      id: 'price-shared',
      code: 'REVEAL_GROUNT',
      name_key: null,
      display_name: 'Gruntowanie ościeży',
      category: 'REVEAL',
      unit: 'M2',
      price_scope: 'LABOR',
      price: null,
      currency: 'PLN',
      is_archived: true,
      quality_level: null,
    },
  },
];

function makeList(items: RevealWorkItemRead[] = revealItems): RevealWorkListResponse {
  return { opening_id: openingId, items };
}

function makePriceItem(overrides: Partial<PriceItem> = {}): PriceItem {
  return {
    id: 'pi-default',
    code: 'REVEAL_X',
    name_key: null,
    display_name: 'Ościeżowa praca testowa',
    category: 'REVEAL',
    unit: 'M2',
    price_scope: 'LABOR',
    price: '20.00',
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

function makeSurface(overrides: Partial<SurfaceType> = {}): SurfaceType {
  return {
    id: surfaceId,
    room_id: roomId,
    name: 'Ściana 1',
    surface_type: 'WALL',
    description: null,
    is_archived: false,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

function makeSurfacesResponse(items: SurfaceType[]): SurfaceListResponse {
  return { items, total: items.length };
}

function makeOpening(overrides: Partial<OpeningType> = {}): OpeningType {
  return {
    id: 'other-opening',
    surface_id: surfaceId,
    opening_type: 'WINDOW',
    name: null,
    width: '1.200',
    height: '1.400',
    quantity: 1,
    single_area: '1.680',
    total_area: '1.680',
    description: null,
    reveal_enabled: true,
    reveal_depth: '0.250',
    reveal_left: true,
    reveal_right: true,
    reveal_top: true,
    reveal_bottom: false,
    reveal_single_length: '4.300',
    reveal_single_area: '1.290',
    reveal_total_length: '4.300',
    reveal_total_area: '1.290',
    is_archived: false,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

function makeOpeningsResponse(items: OpeningType[]): OpeningListResponse {
  return { items, total: items.length };
}

function makeApplyResult(overrides: Partial<RevealWorkApplyResult> = {}): RevealWorkApplyResult {
  return {
    source_opening_id: openingId,
    target_count: 1,
    target_opening_ids: ['other-opening'],
    ...overrides,
  };
}

function renderEditor(overrides: Partial<{
  revealTotalLength: string | number | null;
  revealTotalArea: string | number | null;
  onClose: () => void;
}> = {}) {
  return render(
    <I18nProvider>
      <RevealWorkPlanEditor
        projectId={projectId}
        roomId={roomId}
        surfaceId={surfaceId}
        openingId={openingId}
        openingLabel="Okno (Okno łazienkowe)"
        revealTotalLength={overrides.revealTotalLength ?? '4.300'}
        revealTotalArea={overrides.revealTotalArea ?? '1.290'}
        onClose={overrides.onClose ?? vi.fn()}
      />
    </I18nProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RevealWorkPlanEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(revealWorksApi.fetchRevealWorks).mockResolvedValue(makeList());
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(makePriceItemListResponse([]));
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue(makeSurfacesResponse([makeSurface()]));
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue(
      makeOpeningsResponse([makeOpening({ id: 'other-opening' })]),
    );
    vi.mocked(revealWorksApi.applyRevealWorksToRoom).mockResolvedValue(makeApplyResult());
  });

  it('shows the backend-authoritative reveal geometry without recalculating it', async () => {
    renderEditor({ revealTotalLength: '4.300', revealTotalArea: '1.290' });
    const geometry = await screen.findByLabelText(`reveal-geometry-${openingId}`);
    expect(geometry.textContent).toContain('4.30');
    expect(geometry.textContent).toContain('1.29');
  });

  it('renders a bottom close action that reuses the exact same onClose handler as the top action (Stage 10H.1)', async () => {
    const onClose = vi.fn();
    renderEditor({ onClose });

    const bottomClose = await screen.findByLabelText(`close-reveal-work-bottom-${openingId}`);
    expect(bottomClose).toHaveTextContent('Zamknij');
    expect(bottomClose.className).toContain('w-full');

    fireEvent.click(bottomClose);
    expect(onClose).toHaveBeenCalledTimes(1);
    // No save is triggered merely by closing — dirty-change contract preserved.
    expect(revealWorksApi.putRevealWorks).not.toHaveBeenCalled();
  });

  it('localizes the reveal length as "mb", never raw "LM" (Stage 10G.4 follow-up)', async () => {
    renderEditor({ revealTotalLength: '4.300', revealTotalArea: '1.290' });
    const geometry = await screen.findByLabelText(`reveal-geometry-${openingId}`);
    expect(geometry.textContent).toContain('mb');
    expect(geometry.textContent).not.toMatch(/\bLM\b/);
  });

  it('loads and renders the existing ordered reveal works, resolved names, unit/scope, price, and archived badge', async () => {
    let resolveList!: (list: RevealWorkListResponse) => void;
    vi.mocked(revealWorksApi.fetchRevealWorks).mockReturnValue(
      new Promise((resolve) => { resolveList = resolve; }),
    );

    renderEditor();
    expect(screen.getByText('Ładowanie prac na ościeżu...')).toBeInTheDocument();

    await act(async () => resolveList(makeList()));

    const rows = within(await screen.findByLabelText(`reveal-works-${openingId}`)).getAllByRole('listitem');
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent('Gruntowanie ościeży');
    expect(rows[0]).toHaveTextContent('30,00');
    expect(rows[1]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)'); // resolved name_key
    // Stage 10G.4 — LM occurrence renders localized "mb", never raw "LM".
    expect(rows[1]).toHaveTextContent('mb');
    expect(rows[1].textContent).not.toMatch(/\bLM\b/);
    expect(rows[2]).toHaveTextContent('Do ustalenia');
    expect(rows[2]).toHaveTextContent('Zarchiwizowana');
    expect(screen.getByLabelText(`save-reveal-work-${openingId}`)).toBeDisabled();
    expect(revealWorksApi.putRevealWorks).not.toHaveBeenCalled();
  });

  it('never renders raw name_key or item_code as the primary label', async () => {
    renderEditor();
    const rows = within(await screen.findByLabelText(`reveal-works-${openingId}`)).getAllByRole('listitem');
    expect(rows[1].textContent).not.toContain('pricebook.seed.paint_2k');
    expect(rows[0].textContent).not.toContain('REVEAL_GROUNT');
  });

  it('shows "Brak prac na tym ościeżu." when the opening has no reveal works yet', async () => {
    vi.mocked(revealWorksApi.fetchRevealWorks).mockResolvedValue(makeList([]));
    renderEditor();
    expect(await screen.findByText('Brak prac na tym ościeżu.')).toBeInTheDocument();
  });

  it('the picker requests only PriceCategory.REVEAL items', async () => {
    renderEditor();
    await screen.findByLabelText(`reveal-works-${openingId}`);
    fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));
    await waitFor(() => {
      expect(priceItemsApi.fetchPriceItems).toHaveBeenCalledWith({ category: 'REVEAL', archived: 'active' });
    });
  });

  it('shows M2 and LM candidates in the picker with resolved name, unit, scope, and price', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([
        makePriceItem({ id: 'pm2', unit: 'M2', display_name: 'Gruntowanie', price: '20.00' }),
        makePriceItem({ id: 'plm', unit: 'LM', display_name: 'Narożniki', price: '12.00' }),
      ]),
    );
    renderEditor();
    await screen.findByLabelText(`reveal-works-${openingId}`);
    fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));

    const list = await screen.findByLabelText(`reveal-picker-list-${openingId}`);
    expect(within(list).getByLabelText('reveal-picker-item-pm2')).toHaveTextContent('m²');
    expect(within(list).getByLabelText('reveal-picker-item-plm')).toHaveTextContent('mb');
  });

  it('a candidate with a NULL owner price shows "Do ustalenia" in the picker, never a substitute value', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([makePriceItem({ id: 'pnull', price: null })]),
    );
    renderEditor();
    await screen.findByLabelText(`reveal-works-${openingId}`);
    fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));
    const item = await screen.findByLabelText('reveal-picker-item-pnull');
    expect(item.textContent).toContain('Do ustalenia');
  });

  it('adding a work appends it to the draft list without persisting yet', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([makePriceItem({ id: 'new-item', display_name: 'Nowa praca' })]),
    );
    renderEditor();
    await screen.findByLabelText(`reveal-works-${openingId}`);
    fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));
    fireEvent.click(await screen.findByLabelText('reveal-picker-item-new-item'));

    const rows = within(screen.getByLabelText(`reveal-works-${openingId}`)).getAllByRole('listitem');
    expect(rows).toHaveLength(4);
    expect(rows[3]).toHaveTextContent('Nowa praca');
    expect(revealWorksApi.putRevealWorks).not.toHaveBeenCalled();
  });

  it('adding the same item twice keeps both occurrences (duplicates allowed per backend contract)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([makePriceItem({ id: 'dup-item', display_name: 'Powtarzalna praca' })]),
    );
    renderEditor();
    await screen.findByLabelText(`reveal-works-${openingId}`);

    fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));
    fireEvent.click(await screen.findByLabelText('reveal-picker-item-dup-item'));
    fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));
    fireEvent.click(await screen.findByLabelText('reveal-picker-item-dup-item'));

    const rows = within(screen.getByLabelText(`reveal-works-${openingId}`)).getAllByRole('listitem');
    expect(rows.filter((r) => r.textContent?.includes('Powtarzalna praca'))).toHaveLength(2);
  });

  it('reordering moves an occurrence and preserves the exact new order on save', async () => {
    renderEditor();
    const list = await screen.findByLabelText(`reveal-works-${openingId}`);
    const firstRow = within(list).getAllByRole('listitem')[0];
    const draftKeyMatch = firstRow.getAttribute('aria-label')?.match(/reveal-work-occurrence-(.+)/);
    expect(draftKeyMatch).toBeTruthy();

    fireEvent.click(screen.getByLabelText(`reveal-move-down-${draftKeyMatch![1]}`));

    const rows = within(list).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');
    expect(rows[1]).toHaveTextContent('Gruntowanie ościeży');

    vi.mocked(revealWorksApi.putRevealWorks).mockResolvedValue(makeList());
    fireEvent.click(screen.getByLabelText(`save-reveal-work-${openingId}`));

    await waitFor(() => {
      expect(revealWorksApi.putRevealWorks).toHaveBeenCalledWith(
        projectId, roomId, surfaceId, openingId,
        { price_item_ids: ['price-localized', 'price-shared', 'price-shared'] },
      );
    });
  });

  it('removing an occurrence excludes it from the saved order', async () => {
    renderEditor();
    const list = await screen.findByLabelText(`reveal-works-${openingId}`);
    const secondRow = within(list).getAllByRole('listitem')[1];
    const draftKey = secondRow.getAttribute('aria-label')!.replace('reveal-work-occurrence-', '');

    fireEvent.click(screen.getByLabelText(`reveal-remove-${draftKey}`));
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);

    vi.mocked(revealWorksApi.putRevealWorks).mockResolvedValue(makeList());
    fireEvent.click(screen.getByLabelText(`save-reveal-work-${openingId}`));

    await waitFor(() => {
      expect(revealWorksApi.putRevealWorks).toHaveBeenCalledWith(
        projectId, roomId, surfaceId, openingId,
        { price_item_ids: ['price-shared', 'price-shared'] },
      );
    });
  });

  it('a successful save hydrates from the authoritative PUT response and shows the saved confirmation', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([makePriceItem()]),
    );
    renderEditor();
    await screen.findByLabelText(`reveal-works-${openingId}`);
    fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));
    fireEvent.click(await screen.findByLabelText('reveal-picker-item-pi-default'));

    vi.mocked(revealWorksApi.putRevealWorks).mockResolvedValue(makeList());
    fireEvent.click(screen.getByLabelText(`save-reveal-work-${openingId}`));

    await waitFor(() => expect(screen.getByText('Prace na ościeżu zostały zapisane.')).toBeInTheDocument());
    // Hydrated back to the 3 authoritative items from the mocked PUT response.
    expect(within(screen.getByLabelText(`reveal-works-${openingId}`)).getAllByRole('listitem')).toHaveLength(3);
  });

  it('a save failure keeps the draft and shows a recoverable inline error', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
      makePriceItemListResponse([makePriceItem()]),
    );
    renderEditor();
    await screen.findByLabelText(`reveal-works-${openingId}`);
    fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));
    fireEvent.click(await screen.findByLabelText('reveal-picker-item-pi-default'));

    vi.mocked(revealWorksApi.putRevealWorks).mockRejectedValue(new Error('network down'));
    fireEvent.click(screen.getByLabelText(`save-reveal-work-${openingId}`));

    await waitFor(() => expect(screen.getByText('Nie udało się zapisać prac na ościeżu.')).toBeInTheDocument());
    // Draft (4 items) preserved — no optimistic mutation, no silent data loss.
    expect(within(screen.getByLabelText(`reveal-works-${openingId}`)).getAllByRole('listitem')).toHaveLength(4);
  });

  it('a load failure shows a recoverable error with retry', async () => {
    vi.mocked(revealWorksApi.fetchRevealWorks).mockRejectedValueOnce(new Error('boom'));
    renderEditor();
    await screen.findByText('Nie udało się załadować prac na ościeżu.');

    vi.mocked(revealWorksApi.fetchRevealWorks).mockResolvedValueOnce(makeList());
    fireEvent.click(screen.getByLabelText(`retry-reveal-work-${openingId}`));
    await screen.findByLabelText(`reveal-works-${openingId}`);
  });

  it('all interactive controls meet the 44px minimum touch target', async () => {
    renderEditor();
    const list = await screen.findByLabelText(`reveal-works-${openingId}`);
    const firstDraftKey = within(list).getAllByRole('listitem')[0]
      .getAttribute('aria-label')!.replace('reveal-work-occurrence-', '');
    expect(screen.getByLabelText(`reveal-move-up-${firstDraftKey}`).className).toContain('min-h-[44px]');
    expect(screen.getByLabelText(`reveal-remove-${firstDraftKey}`).className).toContain('min-h-[44px]');
    expect(screen.getByLabelText(`open-reveal-picker-${openingId}`).className).toContain('min-h-[44px]');
    expect(screen.getByLabelText(`save-reveal-work-${openingId}`).className).toContain('min-h-[44px]');
  });

  it('long PL work names wrap instead of overflowing (break-words)', async () => {
    vi.mocked(revealWorksApi.fetchRevealWorks).mockResolvedValue(makeList([
      {
        id: 'rw-long',
        position: 0,
        price_item_id: 'long-item',
        price_item: {
          id: 'long-item',
          code: 'LONG',
          name_key: null,
          display_name: 'Bardzo długa nazwa pracy ościeżowej opisująca cały zakres przygotowania i wykończenia powierzchni ościeży',
          category: 'REVEAL',
          unit: 'M2',
          price_scope: 'LABOR',
          price: '10.00',
          currency: 'PLN',
          is_archived: false,
          quality_level: null,
        },
      },
    ]));
    renderEditor();
    const list = await screen.findByLabelText(`reveal-works-${openingId}`);
    const label = within(list).getByText(/Bardzo długa nazwa/);
    expect(label.className).toContain('break-words');
  });

  it('no frontend quantity/financial arithmetic is introduced — only WHAT work applies is selected here', async () => {
    renderEditor();
    await screen.findByLabelText(`reveal-works-${openingId}`);
    // No quantity input/control exists anywhere in this editor.
    expect(screen.queryByLabelText(/quantity/i)).toBeNull();
  });

  // ---------------------------------------------------------------------------
  // Apply to all reveal-enabled openings in the room (Stage 10G.4 bulk apply)
  // ---------------------------------------------------------------------------

  describe('apply to room openings', () => {
    it('is hidden while the draft has unsaved changes', async () => {
      vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue(
        makePriceItemListResponse([makePriceItem()]),
      );
      renderEditor();
      await screen.findByLabelText(`reveal-works-${openingId}`);
      expect(screen.getByLabelText(`apply-to-room-openings-${openingId}`)).toBeInTheDocument();

      fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));
      fireEvent.click(await screen.findByLabelText('reveal-picker-item-pi-default'));

      expect(screen.queryByLabelText(`apply-to-room-openings-${openingId}`)).toBeNull();
    });

    it('fetches every room surface and opening to compute an accurate eligible target count, excluding the source itself', async () => {
      vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue(
        makeSurfacesResponse([makeSurface({ id: surfaceId }), makeSurface({ id: 'surface-2' })]),
      );
      vi.mocked(openingsApi.fetchOpenings).mockImplementation((_p, _r, sId) =>
        Promise.resolve(
          sId === surfaceId
            ? makeOpeningsResponse([makeOpening({ id: openingId }), makeOpening({ id: 'target-a' })])
            : makeOpeningsResponse([makeOpening({ id: 'target-b', surface_id: 'surface-2' })]),
        ),
      );
      renderEditor();
      await screen.findByLabelText(`reveal-works-${openingId}`);

      fireEvent.click(screen.getByLabelText(`apply-to-room-openings-${openingId}`));

      const panel = await screen.findByLabelText(`apply-confirm-panel-${openingId}`);
      // 2 eligible targets (target-a, target-b) — source opening excluded.
      expect(panel.textContent).toContain('2 otworów');
      expect(surfacesApi.fetchSurfaces).toHaveBeenCalledWith(projectId, roomId);
    });

    it('cancelling the confirmation performs no mutation', async () => {
      renderEditor();
      await screen.findByLabelText(`reveal-works-${openingId}`);
      fireEvent.click(screen.getByLabelText(`apply-to-room-openings-${openingId}`));
      await screen.findByLabelText(`apply-confirm-panel-${openingId}`);

      fireEvent.click(screen.getByLabelText(`apply-cancel-${openingId}`));

      expect(screen.queryByLabelText(`apply-confirm-panel-${openingId}`)).toBeNull();
      expect(revealWorksApi.applyRevealWorksToRoom).not.toHaveBeenCalled();
      expect(screen.getByLabelText(`apply-to-room-openings-${openingId}`)).toBeInTheDocument();
    });

    it('confirming applies to the room, then authoritatively refetches this opening\'s own plan and shows localized success', async () => {
      vi.mocked(revealWorksApi.applyRevealWorksToRoom).mockResolvedValue(
        makeApplyResult({ target_count: 2, target_opening_ids: ['a', 'b'] }),
      );
      renderEditor();
      await screen.findByLabelText(`reveal-works-${openingId}`);
      fireEvent.click(screen.getByLabelText(`apply-to-room-openings-${openingId}`));
      await screen.findByLabelText(`apply-confirm-panel-${openingId}`);

      vi.mocked(revealWorksApi.fetchRevealWorks).mockClear();
      fireEvent.click(screen.getByLabelText(`apply-confirm-yes-${openingId}`));

      await waitFor(() => {
        expect(revealWorksApi.applyRevealWorksToRoom).toHaveBeenCalledWith(
          projectId, roomId, surfaceId, openingId,
        );
      });
      await waitFor(() => {
        expect(screen.getByText('Prace zastosowano do 2 otworów.')).toBeInTheDocument();
      });
      // Authoritative refetch of the source opening's own plan.
      expect(revealWorksApi.fetchRevealWorks).toHaveBeenCalledWith(
        projectId, roomId, surfaceId, openingId,
      );
    });

    it('a failed apply shows a recoverable inline error and performs no partial UI mutation', async () => {
      vi.mocked(revealWorksApi.applyRevealWorksToRoom).mockRejectedValue(new Error('boom'));
      renderEditor();
      await screen.findByLabelText(`reveal-works-${openingId}`);
      fireEvent.click(screen.getByLabelText(`apply-to-room-openings-${openingId}`));
      await screen.findByLabelText(`apply-confirm-panel-${openingId}`);

      fireEvent.click(screen.getByLabelText(`apply-confirm-yes-${openingId}`));

      await waitFor(() => {
        expect(screen.getByText('Nie udało się zastosować prac do innych otworów.')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByLabelText(`apply-error-dismiss-${openingId}`));
      expect(screen.getByLabelText(`apply-to-room-openings-${openingId}`)).toBeInTheDocument();
    });

    it('uses a distinct destructive-clearing confirmation wording when the source has no reveal works', async () => {
      vi.mocked(revealWorksApi.fetchRevealWorks).mockResolvedValue(makeList([]));
      renderEditor();
      await screen.findByText('Brak prac na tym ościeżu.');

      fireEvent.click(screen.getByLabelText(`apply-to-room-openings-${openingId}`));

      const panel = await screen.findByLabelText(`apply-confirm-panel-${openingId}`);
      expect(panel.textContent).toContain('Lista prac jest pusta');
      expect(panel.textContent).toContain('wyczyści');
    });

    it('a target-count fetch failure shows a recoverable error instead of a fabricated count', async () => {
      vi.mocked(surfacesApi.fetchSurfaces).mockRejectedValue(new Error('network down'));
      renderEditor();
      await screen.findByLabelText(`reveal-works-${openingId}`);

      fireEvent.click(screen.getByLabelText(`apply-to-room-openings-${openingId}`));

      await waitFor(() => {
        expect(screen.getByText('Nie udało się zastosować prac do innych otworów.')).toBeInTheDocument();
      });
      expect(screen.queryByLabelText(`apply-confirm-panel-${openingId}`)).toBeNull();
    });

    it('the apply and confirmation controls meet the 44px minimum touch target', async () => {
      renderEditor();
      await screen.findByLabelText(`reveal-works-${openingId}`);
      const applyButton = screen.getByLabelText(`apply-to-room-openings-${openingId}`);
      expect(applyButton.className).toContain('min-h-[44px]');

      fireEvent.click(applyButton);
      await screen.findByLabelText(`apply-confirm-panel-${openingId}`);
      expect(screen.getByLabelText(`apply-confirm-yes-${openingId}`).className).toContain('min-h-[44px]');
      expect(screen.getByLabelText(`apply-cancel-${openingId}`).className).toContain('min-h-[44px]');
    });

    it('long PL/RU confirmation text wraps instead of overflowing (break-words)', async () => {
      renderEditor();
      await screen.findByLabelText(`reveal-works-${openingId}`);
      fireEvent.click(screen.getByLabelText(`apply-to-room-openings-${openingId}`));
      const panel = await screen.findByLabelText(`apply-confirm-panel-${openingId}`);
      const text = within(panel).getByText(/Zastosować te prace/);
      expect(text.className).toContain('break-words');
    });
  });

  // ---------------------------------------------------------------------------
  // Inline Price Book creation from the picker (Stage 10G.4 follow-up)
  // ---------------------------------------------------------------------------

  describe('inline Price Book item creation', () => {
    async function openPickerPanel() {
      renderEditor();
      await screen.findByLabelText(`reveal-works-${openingId}`);
      fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));
      return screen.findByLabelText(`reveal-picker-panel-${openingId}`);
    }

    it('shows "+ Dodaj nową pracę do cennika" at the bottom of the picker', async () => {
      const panel = await openPickerPanel();
      expect(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`)).toHaveTextContent(
        'Dodaj nową pracę do cennika',
      );
    });

    it('opens the inline creation form and hides the search/list', async () => {
      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));

      expect(
        await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`),
      ).toBeInTheDocument();
      expect(screen.queryByLabelText(`reveal-picker-search-${openingId}`)).toBeNull();
    });

    it('locks the category to REVEAL — no category selector is rendered', async () => {
      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      const form = await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`);

      expect(within(form).queryByRole('combobox', { name: /reveal-new-price-item.*category/ })).toBeNull();
      expect(within(form).getByLabelText(`reveal-new-price-item-${openingId}-category`).tagName).toBe('P');
      expect(within(form).getByLabelText(`reveal-new-price-item-${openingId}-category`)).toHaveTextContent(
        'Ościeża / obróbki',
      );
    });

    it('creating an M2 item persists it via the Price Book API and immediately adds it to the draft, closing the picker', async () => {
      const created = makePriceItem({
        id: 'created-m2',
        display_name: 'Gruntowanie ościeży',
        category: 'REVEAL',
        unit: 'M2',
        price: '18.00',
      });
      vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(created);

      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      const form = await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`);

      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-display-name`), {
        target: { value: 'Gruntowanie ościeży' },
      });
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-unit`), {
        target: { value: 'M2' },
      });
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-price`), {
        target: { value: '18.00' },
      });
      fireEvent.submit(form);

      await waitFor(() =>
        expect(priceItemsApi.createPriceItem).toHaveBeenCalledWith(
          expect.objectContaining({
            display_name: 'Gruntowanie ościeży',
            category: 'REVEAL',
            unit: 'M2',
            price: '18.00',
          }),
        ),
      );

      // Picker closed, new item present in the draft.
      expect(screen.queryByLabelText(`reveal-picker-panel-${openingId}`)).toBeNull();
      const rows = within(screen.getByLabelText(`reveal-works-${openingId}`)).getAllByRole('listitem');
      expect(rows[rows.length - 1]).toHaveTextContent('Gruntowanie ościeży');
    });

    it('creating an LM item works the same way', async () => {
      const created = makePriceItem({
        id: 'created-lm',
        display_name: 'Obróbka narożników ościeży',
        category: 'REVEAL',
        unit: 'LM',
        price: '9.50',
      });
      vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(created);

      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      const form = await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`);

      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-display-name`), {
        target: { value: 'Obróbka narożników ościeży' },
      });
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-unit`), {
        target: { value: 'LM' },
      });
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-price`), {
        target: { value: '9.50' },
      });
      fireEvent.submit(form);

      await waitFor(() =>
        expect(priceItemsApi.createPriceItem).toHaveBeenCalledWith(
          expect.objectContaining({ unit: 'LM' }),
        ),
      );
      const rows = within(screen.getByLabelText(`reveal-works-${openingId}`)).getAllByRole('listitem');
      expect(rows[rows.length - 1]).toHaveTextContent('Obróbka narożników ościeży');
    });

    it('an explicit 0.00 price is preserved, never converted to empty', async () => {
      const created = makePriceItem({ id: 'created-zero', display_name: 'Praca bez narzutu', price: '0.00' });
      vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(created);

      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      const form = await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`);
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-display-name`), {
        target: { value: 'Praca bez narzutu' },
      });
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-price`), {
        target: { value: '0.00' },
      });
      fireEvent.submit(form);

      await waitFor(() =>
        expect(priceItemsApi.createPriceItem).toHaveBeenCalledWith(
          expect.objectContaining({ price: '0.00' }),
        ),
      );
    });

    it('creating a REVEAL M2 item with "Cena do ustalenia" sends price: null, immediately enters the draft, and requires no auto-save', async () => {
      const created = makePriceItem({
        id: 'created-null',
        display_name: 'Szpachlowanie ościeży',
        category: 'REVEAL',
        unit: 'M2',
        price: null,
      });
      vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(created);

      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      const form = await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`);
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-display-name`), {
        target: { value: 'Szpachlowanie ościeży' },
      });
      fireEvent.click(within(form).getByLabelText(`reveal-new-price-item-${openingId}-price-unresolved`));
      expect(within(form).queryByLabelText(`reveal-new-price-item-${openingId}-price`)).toBeNull();
      fireEvent.submit(form);

      await waitFor(() =>
        expect(priceItemsApi.createPriceItem).toHaveBeenCalledWith(
          expect.objectContaining({ price: null }),
        ),
      );
      expect(revealWorksApi.putRevealWorks).not.toHaveBeenCalled();
      const rows = within(screen.getByLabelText(`reveal-works-${openingId}`)).getAllByRole('listitem');
      expect(rows[rows.length - 1]).toHaveTextContent('Szpachlowanie ościeży');
      expect(rows[rows.length - 1]).toHaveTextContent('Do ustalenia');

      // After the owner presses the existing Save button it becomes a normal
      // persisted reveal planned work, same as any other selection.
      vi.mocked(revealWorksApi.putRevealWorks).mockResolvedValue(
        makeList([...revealItems, { id: 'rw-new', position: 3, price_item_id: 'created-null', price_item: created }]),
      );
      fireEvent.click(screen.getByLabelText(`save-reveal-work-${openingId}`));
      await waitFor(() => expect(revealWorksApi.putRevealWorks).toHaveBeenCalled());
    });

    it('shows the literal owner-entered name, never running it through resolveKey', async () => {
      const created = makePriceItem({
        id: 'created-literal',
        display_name: 'Zupełnie nowa, niestandardowa praca ościeżowa',
      });
      vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(created);

      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      const form = await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`);
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-display-name`), {
        target: { value: 'Zupełnie nowa, niestandardowa praca ościeżowa' },
      });
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-price`), {
        target: { value: '5' },
      });
      fireEvent.submit(form);

      expect(
        await screen.findByText('Zupełnie nowa, niestandardowa praca ościeżowa'),
      ).toBeInTheDocument();
    });

    it('never sends a Reveal Work Plan PUT merely because a Price Book item was created', async () => {
      const created = makePriceItem({ id: 'created-nosave', display_name: 'Nowa praca' });
      vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(created);

      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      const form = await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`);
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-display-name`), {
        target: { value: 'Nowa praca' },
      });
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-price`), {
        target: { value: '5' },
      });
      fireEvent.submit(form);

      await waitFor(() => expect(priceItemsApi.createPriceItem).toHaveBeenCalled());
      expect(revealWorksApi.putRevealWorks).not.toHaveBeenCalled();
      // The owner must still press the existing Save button.
      expect(screen.getByLabelText(`save-reveal-work-${openingId}`)).not.toBeDisabled();
    });

    it('cancelling the creation form persists nothing and returns to the picker list', async () => {
      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      const form = await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`);
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-display-name`), {
        target: { value: 'Nigdy nie zapisane' },
      });

      fireEvent.click(within(form).getByRole('button', { name: 'Anuluj' }));

      expect(priceItemsApi.createPriceItem).not.toHaveBeenCalled();
      expect(screen.queryByLabelText(`reveal-new-price-item-${openingId}-form`)).toBeNull();
      expect(await screen.findByLabelText(`reveal-picker-search-${openingId}`)).toBeInTheDocument();
      expect(screen.queryByText('Nigdy nie zapisane')).toBeNull();
    });

    it('a creation failure preserves the entered values and shows a recoverable error without mutating the draft', async () => {
      vi.mocked(priceItemsApi.createPriceItem).mockRejectedValue(new Error('server down'));
      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      const form = await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`);
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-display-name`), {
        target: { value: 'Praca z błędem' },
      });
      fireEvent.change(within(form).getByLabelText(`reveal-new-price-item-${openingId}-price`), {
        target: { value: '7' },
      });
      fireEvent.submit(form);

      expect(await screen.findByText('Nie udało się zapisać pozycji.')).toBeInTheDocument();
      // Entered values are preserved — the form did not reset or close.
      expect(within(form).getByLabelText(`reveal-new-price-item-${openingId}-display-name`)).toHaveValue(
        'Praca z błędem',
      );
      expect(screen.queryByText('Praca z błędem', { selector: 'span, div.font-semibold' })).toBeNull();
    });

    it('reopening the picker after a create refetches the catalog, so a normal reopen already includes the new item', async () => {
      const panel = await openPickerPanel();
      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      fireEvent.click(screen.getByLabelText(`close-reveal-picker-${openingId}`));

      vi.mocked(priceItemsApi.fetchPriceItems).mockClear();
      fireEvent.click(screen.getByLabelText(`open-reveal-picker-${openingId}`));

      await waitFor(() => {
        expect(priceItemsApi.fetchPriceItems).toHaveBeenCalledWith({ category: 'REVEAL', archived: 'active' });
      });
    });

    it('the create action and its form controls meet the 44px minimum touch target', async () => {
      const panel = await openPickerPanel();
      expect(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`).className).toContain('min-h-[44px]');

      fireEvent.click(within(panel).getByLabelText(`reveal-create-price-item-${openingId}`));
      const form = await screen.findByLabelText(`reveal-new-price-item-${openingId}-form`);
      expect(within(form).getByRole('button', { name: 'Zapisz' }).className).toContain('min-h-11');
    });
  });
});
