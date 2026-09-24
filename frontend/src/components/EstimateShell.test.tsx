/**
 * Stage 10G.2 — EstimateShell read-only line detail tests.
 *
 * The shell loads EstimateRead via getEstimate and renders:
 * - estimate header (version, status, name, total)
 * - grouped summary view (selectedGroupKey === null)
 * - detail line cards (selectedGroupKey set to a group key)
 * - loading / error / empty states
 */
import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as estimatesApi from '../api/estimates';
import { I18nProvider } from '../hooks/useI18n';
import type { EstimateLineRead, EstimateRead, EstimateSummaryRead, LineChangeEntry, RegenerationPreviewResponse } from '../types/estimate';
import { surfaceCardTint } from '../utils/surfaceColorTint';
import { EstimateShell } from './EstimateShell';

vi.mock('../api/estimates', () => ({
  listEstimates: vi.fn(),
  generateEstimate: vi.fn(),
  getEstimate: vi.fn(),
  patchEstimateLine: vi.fn(),
  previewEstimateRegeneration: vi.fn(),
  regenerateEstimate: vi.fn(),
  addManualEstimateLine: vi.fn(),
  deleteEstimateLine: vi.fn(),
  finalizeEstimate: vi.fn(),
}));

const PROJECT_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const ESTIMATE_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';

// Group key for the default makeLine() (PLANNED_WORK, price_item_id=pi-1, scope=LABOR, unit=M2, no opening_id)
const PLANNED_SURFACE_KEY = 'planned::pi-1::LABOR::M2::surface';
const PLANNED_REVEAL_KEY = 'planned::pi-1::LABOR::M2::reveal';
const MANUAL_KEY = 'manual::line-1';
const PLANNED_SURFACE_LM_KEY = 'planned::pi-1::LABOR::LM::surface';

function makeSummary(overrides: Partial<EstimateSummaryRead> = {}): EstimateSummaryRead {
  return {
    id: ESTIMATE_ID,
    project_id: PROJECT_ID,
    version: 1,
    status: 'DRAFT',
    name: null,
    total: '4375.00',
    currency: 'PLN',
    created_at: '2026-09-17T10:00:00Z',
    updated_at: '2026-09-17T10:00:00Z',
    ...overrides,
  };
}

function makeLine(overrides: Partial<EstimateLineRead> = {}): EstimateLineRead {
  return {
    id: 'line-1',
    estimate_id: ESTIMATE_ID,
    origin: 'PLANNED_WORK',
    position: 1,
    description: 'Szpachlowanie Q3',
    item_code: 'SKIM_Q3_M2',
    unit: 'M2',
    scope: 'LABOR',
    currency: 'PLN',
    source_quantity: '12.500',
    quantity: '12.500',
    quantity_source: 'SURFACE_NET_AREA',
    quantity_overridden: false,
    unit_price: '35.00',
    price_override: false,
    amount: '437.50',
    price_item_id: 'pi-1',
    plan_id: 'plan-1',
    planned_work_id: 'pw-1',
    surface_id: 'surf-1',
    room_id: 'room-1',
    opening_id: null,
    room_name: 'Salon',
    surface_name: 'Wall 1',
    surface_type_value: 'WALL',
    opening_name: null,
    opening_type_value: null,
    ...overrides,
  };
}

function makeDetail(lines: EstimateLineRead[] = [makeLine()], overrides: Partial<EstimateRead> = {}): EstimateRead {
  return {
    ...makeSummary(),
    lines,
    ...overrides,
  };
}

function makeChange(overrides: Partial<LineChangeEntry> = {}): LineChangeEntry {
  return {
    change_type: 'ADDED',
    estimate_line_id: null,
    planned_work_id: 'pw-new-1',
    surface_id: 'surf-new-1',
    opening_id: null,
    item_code: 'SKIM_Q3_M2',
    description: 'pricebook.seed.skim_2l',
    unit: 'M2',
    old_source_quantity: null,
    new_source_quantity: '12.400',
    old_unit_price: null,
    new_unit_price: '35.00',
    quantity_overridden: false,
    price_override: false,
    ...overrides,
  };
}

function makePreview(overrides: Partial<RegenerationPreviewResponse> = {}): RegenerationPreviewResponse {
  return {
    added: 0,
    removed: 0,
    updated: 0,
    preserved_manual: 0,
    changes: [],
    ...overrides,
  };
}

// Default: shows detail view for the standard single-line group
function renderShell(
  summary: EstimateSummaryRead = makeSummary(),
  selectedGroupKey: string | null = PLANNED_SURFACE_KEY,
) {
  const onGroupKeyChange = vi.fn();
  return render(
    <I18nProvider>
      <EstimateShell
        estimate={summary}
        onBack={vi.fn()}
        selectedGroupKey={selectedGroupKey}
        onGroupKeyChange={onGroupKeyChange}
      />
    </I18nProvider>,
  );
}

beforeEach(() => {
  localStorage.removeItem('locale');
  vi.mocked(estimatesApi.getEstimate).mockReset();
  vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail());
  vi.mocked(estimatesApi.patchEstimateLine).mockReset();
  vi.mocked(estimatesApi.previewEstimateRegeneration).mockReset();
  vi.mocked(estimatesApi.regenerateEstimate).mockReset();
  vi.mocked(estimatesApi.addManualEstimateLine).mockReset();
  vi.mocked(estimatesApi.deleteEstimateLine).mockReset();
  vi.mocked(estimatesApi.finalizeEstimate).mockReset();
});

describe('API call', () => {
  it('calls getEstimate with project_id and estimate_id on mount', async () => {
    renderShell();
    await waitFor(() => {
      expect(vi.mocked(estimatesApi.getEstimate)).toHaveBeenCalledWith(PROJECT_ID, ESTIMATE_ID);
    });
  });

  it('calls getEstimate only for the correct estimate (no other project or estimate)', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    for (const call of vi.mocked(estimatesApi.getEstimate).mock.calls) {
      expect(call[0]).toBe(PROJECT_ID);
      expect(call[1]).toBe(ESTIMATE_ID);
    }
  });
});

describe('loading state', () => {
  it('shows loading indicator before data arrives', () => {
    vi.mocked(estimatesApi.getEstimate).mockReturnValue(new Promise(() => undefined));
    renderShell();
    expect(screen.getByLabelText('estimate-lines-loading')).toBeTruthy();
  });

  it('loading state still shows the estimate header', () => {
    vi.mocked(estimatesApi.getEstimate).mockReturnValue(new Promise(() => undefined));
    renderShell(makeSummary({ version: 2 }));
    expect(screen.getByLabelText('estimate-shell').textContent).toContain('2');
  });
});

describe('error state', () => {
  it('shows error message when getEstimate rejects', async () => {
    vi.mocked(estimatesApi.getEstimate).mockRejectedValue(new Error('Network error'));
    renderShell();
    await waitFor(() => expect(screen.getByLabelText('estimate-lines-error')).toBeTruthy());
    expect(screen.getByLabelText('estimate-lines-error').textContent).toContain('Network error');
  });

  it('retry button calls getEstimate again', async () => {
    vi.mocked(estimatesApi.getEstimate).mockRejectedValueOnce(new Error('fail'));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines-error'));
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail());
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /ponów/i })); });
    await waitFor(() => expect(screen.getByLabelText('estimate-lines')).toBeTruthy());
  });
});

describe('estimate header', () => {
  it('renders the estimate shell container', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell')).toBeTruthy();
  });

  it('shows version number in header', async () => {
    renderShell(makeSummary({ version: 3 }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell').textContent).toContain('3');
  });

  it('shows DRAFT status badge (PL)', async () => {
    renderShell(makeSummary({ status: 'DRAFT' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Szkic');
  });

  it('shows FINAL status badge (PL)', async () => {
    const summary = makeSummary({ status: 'FINAL' });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], summary));
    renderShell(summary);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Finalny');
  });

  it('shows ACCEPTED status badge (PL)', async () => {
    const summary = makeSummary({ status: 'ACCEPTED' });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], summary));
    renderShell(summary);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Zaakceptowany');
  });

  it('shows ARCHIVED status badge (PL)', async () => {
    const summary = makeSummary({ status: 'ARCHIVED' });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], summary));
    renderShell(summary);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Archiwalny');
  });

  it('shows total and currency from summary', async () => {
    renderShell(makeSummary({ total: '4375.00', currency: 'PLN' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const shell = screen.getByLabelText('estimate-shell').textContent ?? '';
    expect(shell).toContain('4375.00');
    expect(shell).toContain('PLN');
  });

  it('shows — for null total', async () => {
    renderShell(makeSummary({ total: null }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell').textContent).toContain('—');
  });

  it('shows estimate name when present', async () => {
    const summary = makeSummary({ name: 'Kosztorys bazowy' });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], summary));
    renderShell(summary);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByText('Kosztorys bazowy')).toBeTruthy();
  });

  it('reflects the freshly-fetched total, not the stale summary prop, once detail has loaded (regression: header must never show a stale total after a mutation)', async () => {
    // The `estimate` prop simulates a parent that fetched the estimate list
    // BEFORE some total-changing mutation (e.g. regeneration); the freshly
    // fetched `detail` must win.
    const staleSummary = makeSummary({ total: '1731.92', currency: 'PLN' });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine()], { ...staleSummary, total: '3819.80' }),
    );
    renderShell(staleSummary, null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('3819.80 PLN');
  });
});

describe('empty estimate', () => {
  it('shows empty state when lines array is empty', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([]));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines-empty'));
    expect(screen.getByLabelText('estimate-lines-empty').textContent).toContain('Brak pozycji');
  });

  it('shows empty state description (PL)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([]));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines-empty'));
    expect(screen.getByLabelText('estimate-lines-empty').textContent).toContain('zaplanowane prace');
  });
});

// ─── Stage 10G.4 — empty DRAFT recovery correction ───────────────────────────
//
// An Estimate is a snapshot: generating it before any Work Plans exist is a
// legitimate outcome, not corruption. The bug was purely that the empty-state
// branch previously short-circuited BEFORE regenerationSection / manualLineSection
// / finalizeSection were reached, so an empty DRAFT had no way to reach the
// exact same "Sprawdź zmiany" workflow a non-empty DRAFT already has. No new
// preview/regeneration flow is introduced here — these tests exercise the
// SAME shared sections and the SAME existing API functions.

describe('Stage 10G.4 — empty DRAFT reaches the shared regeneration/manual/finalize actions', () => {
  it('an empty DRAFT shows the empty message together with Sprawdź zmiany (grouped view)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-lines-empty'));
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();
  });

  it('an empty DRAFT shows Sprawdź zmiany even when selectedGroupKey is stale (detail view default)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([]));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines-empty'));
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();
  });

  it('clicking Sprawdź zmiany on an empty DRAFT calls the existing preview endpoint and renders ADDED entries', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([]));
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 2, changes: [
        makeChange({ change_type: 'ADDED', description: 'pricebook.seed.skim_2l' }),
        makeChange({ change_type: 'ADDED', planned_work_id: 'pw-new-2', description: 'pricebook.seed.paint_2k' }),
      ] }),
    );
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-lines-empty'));

    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));

    await waitFor(() => {
      expect(estimatesApi.previewEstimateRegeneration).toHaveBeenCalledWith(PROJECT_ID, ESTIMATE_ID);
    });
    await waitFor(() => screen.getByLabelText('estimate-regeneration-category-ADDED'));
    expect(screen.getByLabelText('estimate-regeneration-change-ADDED-0')).toBeTruthy();
    expect(screen.getByLabelText('estimate-regeneration-change-ADDED-1')).toBeTruthy();
  });

  it('confirming regeneration on an empty DRAFT calls the existing regenerate endpoint, refetches authoritatively, and the newly returned lines + total render', async () => {
    const summary = makeSummary({ total: null });
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([], summary))
      .mockResolvedValueOnce(makeDetail([makeLine()], { ...summary, total: '4375.00' }));
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    vi.mocked(estimatesApi.regenerateEstimate).mockResolvedValue(makePreview({ added: 1 }));

    renderShell(summary, null);
    await waitFor(() => screen.getByLabelText('estimate-lines-empty'));
    expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('—');
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-confirm'));

    await waitFor(() => {
      expect(estimatesApi.regenerateEstimate).toHaveBeenCalledWith(PROJECT_ID, ESTIMATE_ID);
    });
    await waitFor(() => expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(2));
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('4375.00 PLN');
  });

  it('"+ Dodaj pozycję" remains reachable on an empty DRAFT', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-lines-empty'));
    expect(screen.getByLabelText('estimate-add-manual-line-action')).toBeTruthy();
  });

  it('"Finalizuj kosztorys" remains reachable on an empty DRAFT (backend already permits finalizing zero lines)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-lines-empty'));
    expect(screen.getByLabelText('estimate-finalize-action')).toBeTruthy();
  });

  it('gives the three DRAFT actions distinct subtle backgrounds and a compact collapsed height (Stage 10H.1)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-lines-empty'));

    const checkChanges = screen.getByLabelText('estimate-check-changes-action');
    const addManualLine = screen.getByLabelText('estimate-add-manual-line-action');
    const finalize = screen.getByLabelText('estimate-finalize-action');

    // Distinct semantic backgrounds — never the same class for all three.
    expect(checkChanges.className).toContain('bg-blue-50');
    expect(addManualLine.className).toContain('bg-violet-50');
    expect(finalize.className).toContain('bg-emerald-50');

    // Still a full ~44px touch target...
    for (const action of [checkChanges, addManualLine, finalize]) {
      expect(action.className).toContain('min-h-[44px]');
      expect(action.className).toContain('w-full');
    }

    // ...but the collapsed wrapper carries no extra card padding, so three
    // stacked actions don't each cost a full white-card's worth of height.
    expect(checkChanges.parentElement?.className).not.toContain('p-3');
    expect(addManualLine.parentElement?.className).not.toContain('p-3');
    expect(finalize.parentElement?.className).not.toContain('p-3');
  });

  it.each(['FINAL', 'ACCEPTED', 'ARCHIVED'] as const)(
    'an empty %s estimate exposes no regeneration/manual-line/finalize controls',
    async (status) => {
      vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([], { status }));
      renderShell(makeSummary({ status }), null);
      await waitFor(() => screen.getByLabelText('estimate-lines-empty'));
      expect(screen.queryByLabelText('estimate-check-changes-action')).toBeNull();
      expect(screen.queryByLabelText('estimate-add-manual-line-action')).toBeNull();
      expect(screen.queryByLabelText('estimate-finalize-action')).toBeNull();
    },
  );

  it('a non-empty DRAFT is unaffected — grouped view still renders groups, not the empty message', async () => {
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('estimate-lines-empty')).toBeNull();
  });
});

describe('line card basics (detail view)', () => {
  it('renders estimate-lines container with lines', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-line-1')).toBeTruthy();
  });

  it('renders owner literal description unchanged', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ description: 'Szpachlowanie Q3' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-description-1').textContent).toBe('Szpachlowanie Q3');
  });

  it('does NOT render item_code even when present in EstimateLine data', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-item-code-1')).toBeNull();
    expect(screen.getByLabelText('estimate-line-1').textContent).not.toContain('SKIM_Q3_M2');
  });

  it('does NOT render item_code when null (no element, no CENNIK code shown)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine({ item_code: null })]));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-item-code-1')).toBeNull();
  });

  it('renders quantity and unit', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-quantity-1').textContent).toContain('12.500');
    expect(screen.getByLabelText('line-quantity-1').textContent).toContain('m²');
  });

  it('renders unit_price with currency', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-unit-price-1').textContent).toContain('35.00');
    expect(screen.getByLabelText('line-unit-price-1').textContent).toContain('PLN');
  });

  it('renders amount with currency', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-amount-1').textContent).toContain('437.50');
    expect(screen.getByLabelText('line-amount-1').textContent).toContain('PLN');
  });
});

describe('description key resolution', () => {
  it('resolves seeded pricebook.seed.prim_adh key in PL', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ description: 'pricebook.seed.prim_adh' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-description-1').textContent).toBe(
      'Gruntowanie gruntem kontaktowym adhezyjnym',
    );
  });

  it('resolves a different seeded key pricebook.seed.skim_2l in PL', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ description: 'pricebook.seed.skim_2l' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-description-1').textContent).toBe(
      'Gładź szpachlowa — 2 warstwy (pakiet)',
    );
  });

  it('resolves pricebook.seed.paint_2k in PL', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ description: 'pricebook.seed.paint_2k' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-description-1').textContent).toBe(
      'Malowanie ścian — 2 warstwy (standard)',
    );
  });

  it('resolves pricebook.seed.prim_adh in RU', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ description: 'pricebook.seed.prim_adh' })]),
    );
    render(
      <I18nProvider>
        <EstimateShell
          estimate={makeSummary()}
          onBack={vi.fn()}
          selectedGroupKey={PLANNED_SURFACE_KEY}
          onGroupKeyChange={vi.fn()}
        />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const text = screen.getByLabelText('line-description-1').textContent ?? '';
    expect(text).not.toBe('pricebook.seed.prim_adh');
    expect(text.length).toBeGreaterThan(10);
  });

  it('resolves pricebook.seed.skim_2l in RU', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ description: 'pricebook.seed.skim_2l' })]),
    );
    render(
      <I18nProvider>
        <EstimateShell
          estimate={makeSummary()}
          onBack={vi.fn()}
          selectedGroupKey={PLANNED_SURFACE_KEY}
          onGroupKeyChange={vi.fn()}
        />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const text = screen.getByLabelText('line-description-1').textContent ?? '';
    expect(text).not.toBe('pricebook.seed.skim_2l');
    expect(text.length).toBeGreaterThan(5);
  });

  it('passes through owner literal description unchanged', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ description: 'Moje szpachlowanie premium' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-description-1').textContent).toBe(
      'Moje szpachlowanie premium',
    );
  });

  it('passes through manual line description unchanged', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ origin: 'MANUAL', description: 'Robocizna dodatkowa' })]),
    );
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-description-1').textContent).toBe('Robocizna dodatkowa');
  });

  it('passes through unknown dotted string unchanged', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ description: 'some.unknown.key.that.does.not.exist' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-description-1').textContent).toBe(
      'some.unknown.key.that.does.not.exist',
    );
  });

  it('does not introduce any additional API calls for key resolution', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([
        makeLine({ id: 'l1', position: 1, description: 'pricebook.seed.prim_adh' }),
        makeLine({ id: 'l2', position: 2, description: 'pricebook.seed.skim_2l' }),
        makeLine({ id: 'l3', position: 3, description: 'pricebook.seed.paint_2k' }),
      ]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(vi.mocked(estimatesApi.getEstimate).mock.calls.length).toBeGreaterThanOrEqual(1);
    const listCalls = vi.mocked(estimatesApi.listEstimates).mock?.calls ?? [];
    expect(listCalls.length).toBe(0);
  });
});

describe('NULL vs zero price', () => {
  it('shows "Do ustalenia" for NULL unit_price (PL)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: null, amount: null })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-unit-price-1').textContent).toBe('Do ustalenia');
  });

  it('shows — for NULL amount', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: null, amount: null })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-amount-1').textContent).toBe('—');
  });

  it('shows 0.00 PLN for zero unit_price (not null)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: '0.00', amount: '0.00' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-unit-price-1').textContent).toContain('0.00');
    expect(screen.getByLabelText('line-unit-price-1').textContent).not.toBe('Do ustalenia');
  });

  it('shows 0.00 PLN for zero amount (not null)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: '0.00', amount: '0.00' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-amount-1').textContent).toContain('0.00');
    expect(screen.getByLabelText('line-amount-1').textContent).not.toBe('—');
  });

  it('NULL unit_price never shows 0.00', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: null, amount: null })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-unit-price-1').textContent).not.toContain('0.00');
  });
});

describe('override indicators', () => {
  it('shows quantity override label when quantity_overridden is true', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ quantity_overridden: true, source_quantity: '10.000' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-qty-override-1').textContent).toContain('Ilość zmieniona ręcznie');
  });

  it('shows source_quantity when quantity_overridden and source_quantity present', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ quantity_overridden: true, source_quantity: '10.000' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-qty-override-1').textContent).toContain('10.000');
    expect(screen.getByLabelText('line-qty-override-1').textContent).toContain('m²');
  });

  it('does not show qty override indicator when quantity_overridden is false', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-qty-override-1')).toBeNull();
  });

  it('shows price override label when price_override is true', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ price_override: true })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-price-override-1').textContent).toContain('Cena zmieniona ręcznie');
  });

  it('does not show price override indicator when price_override is false', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-price-override-1')).toBeNull();
  });

  it('shows price override for NULL price with price_override true', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: null, amount: null, price_override: true })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-price-override-1')).toBeTruthy();
    expect(screen.getByLabelText('line-unit-price-1').textContent).toBe('Do ustalenia');
  });
});

describe('provenance classification', () => {
  it('shows "Zaplanowana praca" for PLANNED_WORK with no opening_id', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-origin-1').textContent).toBe('Zaplanowana praca');
  });

  it('shows "Praca na ościeżu" for PLANNED_WORK with opening_id set', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ origin: 'PLANNED_WORK', opening_id: 'opening-uuid' })]),
    );
    renderShell(makeSummary(), PLANNED_REVEAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-origin-1').textContent).toBe('Praca na ościeżu');
  });

  it('shows "Pozycja ręczna" for MANUAL origin', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ origin: 'MANUAL', opening_id: null })]),
    );
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-origin-1').textContent).toBe('Pozycja ręczna');
  });

  it('does not render raw UUIDs in line card', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const lineText = screen.getByLabelText('estimate-line-1').textContent ?? '';
    expect(lineText).not.toContain('surf-1');
    expect(lineText).not.toContain('room-1');
    expect(lineText).not.toContain('plan-1');
    expect(lineText).not.toContain('pw-1');
    expect(lineText).not.toContain('pi-1');
  });
});

describe('scope display', () => {
  it('shows "Robocizna" for LABOR scope', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-scope-1').textContent).toBe('Robocizna');
  });

  it('shows "Materiał" for MATERIAL scope', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ scope: 'MATERIAL' })]),
    );
    renderShell(makeSummary(), 'planned::pi-1::MATERIAL::M2::surface');
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-scope-1').textContent).toBe('Materiał');
  });

  it('shows "Robocizna + materiał" for LABOR_AND_MATERIAL scope', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ scope: 'LABOR_AND_MATERIAL' })]),
    );
    renderShell(makeSummary(), 'planned::pi-1::LABOR_AND_MATERIAL::M2::surface');
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-scope-1').textContent).toBe('Robocizna + materiał');
  });
});

describe('backend order preservation', () => {
  it('renders multiple lines in the backend position order', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, description: 'Pierwsza' }),
      makeLine({ id: 'l2', position: 2, description: 'Druga' }),
      makeLine({ id: 'l3', position: 3, description: 'Trzecia' }),
    ];
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail(lines));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const all = screen.getAllByLabelText(/^estimate-line-/);
    expect(all[0].textContent).toContain('Pierwsza');
    expect(all[1].textContent).toContain('Druga');
    expect(all[2].textContent).toContain('Trzecia');
  });
});

describe('immutable history versions', () => {
  it('renders line cards for FINAL version', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine()], { status: 'FINAL' }),
    );
    renderShell(makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-line-1')).toBeTruthy();
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Finalny');
  });

  it('renders line cards for ACCEPTED version', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine()], { status: 'ACCEPTED' }),
    );
    renderShell(makeSummary({ status: 'ACCEPTED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-line-1')).toBeTruthy();
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Zaakceptowany');
  });

  it('renders line cards for ARCHIVED version', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine()], { status: 'ARCHIVED' }),
    );
    renderShell(makeSummary({ status: 'ARCHIVED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-line-1')).toBeTruthy();
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Archiwalny');
  });
});

describe('Russian localization', () => {
  function renderShellRu(
    summary: EstimateSummaryRead = makeSummary(),
    selectedGroupKey: string | null = PLANNED_SURFACE_KEY,
  ) {
    localStorage.setItem('locale', 'ru');
    return render(
      <I18nProvider>
        <EstimateShell
          estimate={summary}
          onBack={vi.fn()}
          selectedGroupKey={selectedGroupKey}
          onGroupKeyChange={vi.fn()}
        />
      </I18nProvider>,
    );
  }

  it('shows "Черновик" for DRAFT status (RU)', async () => {
    renderShellRu();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Черновик');
  });

  it('shows "Уточняется" for NULL unit_price (RU)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: null, amount: null })]),
    );
    renderShellRu();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-unit-price-1').textContent).toBe('Уточняется');
  });

  it('shows "Запланированная работа" for surface planned work (RU)', async () => {
    renderShellRu();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-origin-1').textContent).toBe('Запланированная работа');
  });

  it('shows "Работа по откосу" for reveal work (RU)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ opening_id: 'opening-uuid' })]),
    );
    renderShellRu(makeSummary(), PLANNED_REVEAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-origin-1').textContent).toBe('Работа по откосу');
  });

  it('shows "Ручная позиция" for manual line (RU)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ origin: 'MANUAL' })]),
    );
    renderShellRu(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-origin-1').textContent).toBe('Ручная позиция');
  });
});

describe('mobile safety / long content', () => {
  it('line card has min-w-0 and break-words on description', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ description: 'A'.repeat(120) })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const desc = screen.getByLabelText('line-description-1');
    expect(desc.className).toContain('break-words');
    expect(desc.className).toContain('min-w-0');
  });

  it('item_code is not rendered in mobile card (hidden per owner decision)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ item_code: 'CENNIK_PRIM_ADH-01' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-line-1').textContent).not.toContain('CENNIK_PRIM_ADH-01');
  });
});

describe('no frontend business recalculation', () => {
  it('does not compute amount from quantity × unit_price', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ quantity: '12.500', unit_price: '35.00', amount: '999.99' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-amount-1').textContent).toContain('999.99');
    expect(screen.getByLabelText('line-amount-1').textContent).not.toContain('437.50');
  });
});

// ─── Grouped view tests ────────────────────────────────────────────────────────

describe('grouped view (selectedGroupKey === null)', () => {
  function renderGrouped(lines: EstimateLineRead[] = [makeLine()]) {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail(lines));
    const onGroupKeyChange = vi.fn();
    render(
      <I18nProvider>
        <EstimateShell
          estimate={makeSummary()}
          onBack={vi.fn()}
          selectedGroupKey={null}
          onGroupKeyChange={onGroupKeyChange}
        />
      </I18nProvider>,
    );
    return { onGroupKeyChange };
  }

  it('gives each group card a deterministic tint keyed by group identity, not array position (Stage 10H.1)', async () => {
    const surfaceLine = makeLine();
    const manualLine = makeLine({
      id: 'line-2',
      origin: 'MANUAL',
      description: 'Robocizna dodatkowa',
      price_item_id: null,
      plan_id: null,
      planned_work_id: null,
    });
    renderGrouped([surfaceLine, manualLine]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));

    const surfaceTint = surfaceCardTint(PLANNED_SURFACE_KEY);
    const manualTint = surfaceCardTint('manual::line-2');
    // Guard: the fixture's two group identities must actually hash to
    // different palette entries for this assertion to be meaningful.
    expect(surfaceTint.bg).not.toBe(manualTint.bg);

    const card0 = screen.getByLabelText('estimate-group-0').parentElement?.parentElement;
    const card1 = screen.getByLabelText('estimate-group-1').parentElement?.parentElement;
    expect(card0?.className).toContain(surfaceTint.bg);
    expect(card0?.className).toContain(surfaceTint.border);
    expect(card1?.className).toContain(manualTint.bg);
    expect(card1?.className).toContain(manualTint.border);

    // Preserved: scope badges remain rendered on the tinted cards.
    expect(screen.getByLabelText('group-scope-0')).toBeInTheDocument();
    expect(screen.getByLabelText('group-scope-1')).toBeInTheDocument();
  });

  it('renders estimate-groups container when selectedGroupKey is null', async () => {
    renderGrouped();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-groups')).toBeTruthy();
  });

  it('does not render estimate-lines when showing grouped view', async () => {
    renderGrouped();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('estimate-lines')).toBeNull();
  });

  it('two PLANNED_WORK lines with same price_item_id and surface are merged into one group', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, price_item_id: 'pi-1', opening_id: null }),
      makeLine({ id: 'l2', position: 2, price_item_id: 'pi-1', opening_id: null }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getAllByLabelText(/^estimate-group-/).length).toBe(1);
  });

  it('two lines with different price_item_ids are separate groups', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, price_item_id: 'pi-1' }),
      makeLine({ id: 'l2', position: 2, price_item_id: 'pi-2' }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getAllByLabelText(/^estimate-group-/).length).toBe(2);
  });

  it('MANUAL lines are each their own group regardless of description', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, origin: 'MANUAL', price_item_id: null, description: 'Same' }),
      makeLine({ id: 'l2', position: 2, origin: 'MANUAL', price_item_id: null, description: 'Same' }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getAllByLabelText(/^estimate-group-/).length).toBe(2);
  });

  it('reveal lines are a separate group from surface lines with same price_item_id', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, price_item_id: 'pi-1', opening_id: null }),
      makeLine({ id: 'l2', position: 2, price_item_id: 'pi-1', opening_id: 'opening-uuid' }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getAllByLabelText(/^estimate-group-/).length).toBe(2);
  });

  it('group description resolves seeded key via resolveKey', async () => {
    renderGrouped([makeLine({ description: 'pricebook.seed.prim_adh' })]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-description-0').textContent).toBe(
      'Gruntowanie gruntem kontaktowym adhezyjnym',
    );
  });

  it('group shows scope badge', async () => {
    renderGrouped();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-scope-0').textContent).toBe('Robocizna');
  });

  it('group shows origin badge: planned surface work', async () => {
    renderGrouped();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-origin-0').textContent).toBe('Zaplanowana praca');
  });

  it('group shows origin badge: reveal work', async () => {
    renderGrouped([makeLine({ opening_id: 'opening-uuid' })]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-origin-0').textContent).toBe('Praca na ościeżu');
  });

  it('group shows origin badge: manual line', async () => {
    renderGrouped([makeLine({ origin: 'MANUAL', price_item_id: null })]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-origin-0').textContent).toBe('Pozycja ręczna');
  });

  it('group shows line count badge when lineCount > 1', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1 }),
      makeLine({ id: 'l2', position: 2 }),
      makeLine({ id: 'l3', position: 3 }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-line-count-0').textContent).toContain('3');
    expect(screen.getByLabelText('group-line-count-0').textContent).toContain('pozycji');
  });

  it('group does not show line count badge for single-line group', async () => {
    renderGrouped();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('group-line-count-0')).toBeNull();
  });

  it('group quantity aggregated when all lines have same unit', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, quantity: '10.500', unit: 'M2' }),
      makeLine({ id: 'l2', position: 2, quantity: '5.250', unit: 'M2' }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-quantity-0').textContent).toContain('15.750');
    expect(screen.getByLabelText('group-quantity-0').textContent).toContain('m²');
  });

  it('group quantity not shown when lines have mixed units', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, quantity: '10.000', unit: 'M2' }),
      makeLine({ id: 'l2', position: 2, quantity: '3.000', unit: 'LM', price_item_id: 'pi-2' }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    // Two separate groups (different price_item_ids), each with its own quantity
    const groups = screen.getAllByLabelText(/^estimate-group-/);
    expect(groups.length).toBe(2);
    expect(screen.getByLabelText('group-quantity-0').textContent).toContain('10.000');
    expect(screen.getByLabelText('group-quantity-1').textContent).toContain('3.000');
  });

  it('group amount is exact sum when all lines have amounts (no float drift)', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, quantity: '319.41', unit: 'M2', amount: '319.41' }),
      makeLine({ id: 'l2', position: 2, quantity: '319.41', unit: 'M2', amount: '319.41' }),
      makeLine({ id: 'l3', position: 3, quantity: '319.41', unit: 'M2', amount: '319.41' }),
      makeLine({ id: 'l4', position: 4, quantity: '319.41', unit: 'M2', amount: '319.41' }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-amount-0').textContent).toContain('1277.64');
  });

  it('group amount shows "—" when any line has null amount', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, amount: '437.50' }),
      makeLine({ id: 'l2', position: 2, amount: null, unit_price: null }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-amount-0').textContent).toBe('—');
  });

  it('uniform unit_price shown in group card when all lines share same price and no override', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, unit_price: '35.00', price_override: false }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00', price_override: false }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-unit-price-0').textContent).toContain('35.00');
  });

  it('unit_price not shown in group card when any line has price_override', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, unit_price: '35.00', price_override: false }),
      makeLine({ id: 'l2', position: 2, unit_price: '40.00', price_override: true }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('group-unit-price-0')).toBeNull();
  });

  it('group shows "Zawiera zmiany ręczne" when any line has quantity_overridden', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, quantity_overridden: false }),
      makeLine({ id: 'l2', position: 2, quantity_overridden: true }),
    ];
    renderGrouped(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-has-overrides-0').textContent).toBe('Zawiera zmiany ręczne');
  });

  it('group shows "Zawiera zmiany ręczne" when any line has price_override', async () => {
    renderGrouped([makeLine({ price_override: true })]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-has-overrides-0').textContent).toBe('Zawiera zmiany ręczne');
  });

  it('group does not show override indicator when no overrides', async () => {
    renderGrouped();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('group-has-overrides-0')).toBeNull();
  });

  it('tapping a group card calls onGroupKeyChange with the group key', async () => {
    const { onGroupKeyChange } = renderGrouped();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('estimate-group-0'));
    expect(onGroupKeyChange).toHaveBeenCalledWith(PLANNED_SURFACE_KEY);
  });

  it('group card has min-h-[44px] for touch target', async () => {
    renderGrouped();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-group-0').className).toContain('min-h-[44px]');
  });
});

describe('grouped view Russian localization', () => {
  function renderGroupedRu(lines: EstimateLineRead[] = [makeLine()]) {
    localStorage.setItem('locale', 'ru');
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail(lines));
    render(
      <I18nProvider>
        <EstimateShell
          estimate={makeSummary()}
          onBack={vi.fn()}
          selectedGroupKey={null}
          onGroupKeyChange={vi.fn()}
        />
      </I18nProvider>,
    );
  }

  it('shows "позиций" for line count in RU', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1 }),
      makeLine({ id: 'l2', position: 2 }),
    ];
    renderGroupedRu(lines);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-line-count-0').textContent).toContain('позиций');
  });

  it('shows "Содержит ручные изменения" for group overrides in RU', async () => {
    renderGroupedRu([makeLine({ price_override: true })]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-has-overrides-0').textContent).toBe('Содержит ручные изменения');
  });

  it('group description resolves seeded key in RU', async () => {
    renderGroupedRu([makeLine({ description: 'pricebook.seed.prim_adh' })]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const text = screen.getByLabelText('group-description-0').textContent ?? '';
    expect(text).not.toBe('pricebook.seed.prim_adh');
    expect(text.length).toBeGreaterThan(10);
  });
});

describe('detail view: shows only lines of the selected group', () => {
  it('detail view shows only lines from the selected group', async () => {
    const lines = [
      makeLine({ id: 'l1', position: 1, price_item_id: 'pi-1', description: 'Praca pi-1' }),
      makeLine({ id: 'l2', position: 2, price_item_id: 'pi-2', description: 'Praca pi-2' }),
    ];
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail(lines));
    render(
      <I18nProvider>
        <EstimateShell
          estimate={makeSummary()}
          onBack={vi.fn()}
          selectedGroupKey="planned::pi-1::LABOR::M2::surface"
          onGroupKeyChange={vi.fn()}
        />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-line-1')).toBeTruthy();
    expect(screen.queryByLabelText('estimate-line-2')).toBeNull();
  });

  it('detail view shows empty estimate-lines when group key does not match any group', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()]));
    render(
      <I18nProvider>
        <EstimateShell
          estimate={makeSummary()}
          onBack={vi.fn()}
          selectedGroupKey="planned::nonexistent-id::LABOR::M2::surface"
          onGroupKeyChange={vi.fn()}
        />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-lines').children.length).toBe(0);
  });
});

describe('Back button in detail view', () => {
  it('renders a back button with aria-label estimate-detail-back in detail view', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail());
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('estimate-detail-back'));
    expect(screen.getByLabelText('estimate-detail-back')).toBeTruthy();
  });

  it('calls onGroupKeyChange(null) when back button is clicked', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail());
    const onGroupKeyChange = vi.fn();
    render(
      <I18nProvider>
        <EstimateShell
          estimate={makeSummary()}
          onBack={vi.fn()}
          selectedGroupKey={PLANNED_SURFACE_KEY}
          onGroupKeyChange={onGroupKeyChange}
        />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-detail-back'));
    act(() => { fireEvent.click(screen.getByLabelText('estimate-detail-back')); });
    expect(onGroupKeyChange).toHaveBeenCalledWith(null);
  });

  it('shows Polish back label by default', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail());
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('estimate-detail-back'));
    expect(screen.getByLabelText('estimate-detail-back').textContent).toBe('← Wróć do kosztorysu');
  });

  it('shows Russian back label when locale is ru', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail());
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('estimate-detail-back'));
    expect(screen.getByLabelText('estimate-detail-back').textContent).toBe('← Назад к смете');
  });

  it('does NOT render back button in grouped summary view (selectedGroupKey=null)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail());
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('estimate-detail-back')).toBeNull();
  });

  it('back button has min-h-[44px] for touch target', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail());
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('estimate-detail-back'));
    expect(screen.getByLabelText('estimate-detail-back').className).toContain('min-h-[44px]');
  });
});

describe('Line provenance in detail view (compact header — Stage 10G.2 final polish)', () => {
  it('does not render the "Pomieszczenie:" label anywhere in the card', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-line-1').textContent).not.toContain('Pomieszczenie');
  });

  it('does not render the "Powierzchnia:" label anywhere in the card', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-line-1').textContent).not.toContain('Powierzchnia');
  });

  it('does not render the "Otwór:" label anywhere in the card', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([
      makeLine({ opening_id: 'op-1', opening_name: 'Okno 1', opening_type_value: 'WINDOW' }),
    ]));
    renderShell(makeSummary(), PLANNED_REVEAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-line-1').textContent).not.toContain('Otwór');
  });

  it('renders room + surface compactly joined with " — " (no labels)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([
      makeLine({ position: 0, room_name: 'Kuchnia', surface_name: 'Wall 3', surface_type_value: 'WALL' }),
    ]));
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('line-provenance-0'));
    expect(screen.getByLabelText('line-provenance-0').textContent).toBe('Kuchnia — Ściana 3');
  });

  it('renders room + surface + opening compactly for a reveal line', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([
      makeLine({
        position: 0,
        room_name: 'Łazienka',
        surface_name: 'Wall 2',
        surface_type_value: 'WALL',
        opening_id: 'op-1',
        opening_name: null,
        opening_type_value: 'WINDOW',
      }),
    ]));
    renderShell(makeSummary(), PLANNED_REVEAL_KEY);
    await waitFor(() => screen.getByLabelText('line-provenance-0'));
    expect(screen.getByLabelText('line-provenance-0').textContent).toBe('Łazienka — Ściana 2 — Okno');
  });

  it('uses the explicit opening_name instead of the type fallback when the opening has a name', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([
      makeLine({
        position: 0,
        room_name: 'Salon',
        surface_name: 'Wall 1',
        surface_type_value: 'WALL',
        opening_id: 'op-1',
        opening_name: 'Drzwi balkonowe',
        opening_type_value: 'DOOR',
      }),
    ]));
    renderShell(makeSummary(), PLANNED_REVEAL_KEY);
    await waitFor(() => screen.getByLabelText('line-provenance-0'));
    expect(screen.getByLabelText('line-provenance-0').textContent).toBe('Salon — Ściana 1 — Drzwi balkonowe');
  });

  it('omits missing pieces safely: room only, when surface/opening are unavailable', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([
      makeLine({ position: 0, room_name: 'pokoj 1', surface_name: null, surface_type_value: null }),
    ]));
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('line-provenance-0'));
    expect(screen.getByLabelText('line-provenance-0').textContent).toBe('pokoj 1');
  });

  it('renders the compact provenance in Polish', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([
      makeLine({ position: 0, room_name: 'pokoj 1', surface_name: 'Wall 1', surface_type_value: 'WALL' }),
    ]));
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('line-provenance-0'));
    expect(screen.getByLabelText('line-provenance-0').textContent).toBe('pokoj 1 — Ściana 1');
  });

  it('renders the compact provenance in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([
      makeLine({ position: 0, room_name: 'комната 1', surface_name: 'Wall 1', surface_type_value: 'WALL' }),
    ]));
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('line-provenance-0'));
    expect(screen.getByLabelText('line-provenance-0').textContent).toBe('комната 1 — Стена 1');
  });

  it('omits the provenance span entirely for MANUAL lines (no room/surface/opening)', async () => {
    const manualLine = makeLine({
      id: 'line-1',
      origin: 'MANUAL',
      price_item_id: null,
      surface_id: null,
      room_id: null,
      room_name: null,
      surface_name: null,
      surface_type_value: null,
      opening_name: null,
      opening_type_value: null,
    });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([manualLine]));
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-provenance-1')).toBeNull();
  });

  it('the compact provenance span uses mobile-safe wrapping classes (break-words, min-w-0) and lives in the wrapping badge row', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([
      makeLine({
        position: 0,
        room_name: 'Bardzo długa nazwa pomieszczenia testowego na urządzeniu mobilnym',
        surface_name: 'Wall 1',
        surface_type_value: 'WALL',
      }),
    ]));
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('line-provenance-0'));
    const provenanceEl = screen.getByLabelText('line-provenance-0');
    expect(provenanceEl.className).toContain('break-words');
    expect(provenanceEl.className).toContain('min-w-0');
    expect(provenanceEl.parentElement?.className).toContain('flex-wrap');
  });
});

describe('Surface card tint (stable, surface_id-based — Stage 10G.2 final polish)', () => {
  function getCardBgClass(labelText: string): string | undefined {
    return screen.getByLabelText(labelText).className.split(' ').find((c) => c.startsWith('bg-'));
  }

  it('gives two lines with the SAME surface_id the SAME tint background class', async () => {
    const lines = [
      makeLine({ id: 'line-1', position: 0, surface_id: 'a76775d3-8320-42f2-819f-7a9bb16147d1' }),
      makeLine({ id: 'line-2', position: 1, surface_id: 'a76775d3-8320-42f2-819f-7a9bb16147d1' }),
    ];
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail(lines));
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(getCardBgClass('estimate-line-0')).toBe(getCardBgClass('estimate-line-1'));
  });

  it('maps two different real surface_ids to different tint classes deterministically', async () => {
    // Real captured surface_ids (Wall 1 / Wall 2 from the "office" seed project) —
    // not order-dependent, not array-index-derived, computed purely from the id string.
    const lines = [
      makeLine({ id: 'line-1', position: 0, surface_id: 'a76775d3-8320-42f2-819f-7a9bb16147d1' }),
      makeLine({ id: 'line-2', position: 1, surface_id: '89ce93e6-0a2e-4c0b-a13f-094587573b75' }),
    ];
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail(lines));
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(getCardBgClass('estimate-line-0')).toBe('bg-teal-50');
    expect(getCardBgClass('estimate-line-1')).toBe('bg-rose-50');
  });

  it('tint does not depend on line order (same surface_id keeps its tint regardless of position)', async () => {
    const forward = [
      makeLine({ id: 'line-1', position: 0, surface_id: 'a76775d3-8320-42f2-819f-7a9bb16147d1' }),
      makeLine({ id: 'line-2', position: 1, surface_id: '89ce93e6-0a2e-4c0b-a13f-094587573b75' }),
    ];
    vi.mocked(estimatesApi.getEstimate).mockResolvedValueOnce(makeDetail(forward));
    const { unmount } = renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const forwardBg = getCardBgClass('estimate-line-0');
    unmount();

    const reversed = [
      makeLine({ id: 'line-2', position: 0, surface_id: '89ce93e6-0a2e-4c0b-a13f-094587573b75' }),
      makeLine({ id: 'line-1', position: 1, surface_id: 'a76775d3-8320-42f2-819f-7a9bb16147d1' }),
    ];
    vi.mocked(estimatesApi.getEstimate).mockResolvedValueOnce(makeDetail(reversed));
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const sameSurfaceBgAtNewPosition = getCardBgClass('estimate-line-1');

    expect(sameSurfaceBgAtNewPosition).toBe(forwardBg);
  });

  it('MANUAL lines without surface_id use the normal neutral white card background', async () => {
    const manualLine = makeLine({
      id: 'line-1',
      origin: 'MANUAL',
      price_item_id: null,
      surface_id: null,
      position: 0,
    });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([manualLine]));
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(getCardBgClass('estimate-line-0')).toBe('bg-white');
  });
});

describe('Grouping key safety', () => {
  it('lines with same price_item_id but different scope go into separate groups', async () => {
    const line1 = makeLine({ id: 'line-1', scope: 'LABOR', unit: 'M2', position: 0 });
    const line2 = makeLine({ id: 'line-2', scope: 'MATERIAL', unit: 'M2', position: 1 });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([line1, line2]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const groups = screen.getAllByLabelText(/^estimate-group-\d+$/);
    expect(groups.length).toBe(2);
  });

  it('lines with same price_item_id but different unit go into separate groups', async () => {
    const line1 = makeLine({ id: 'line-1', scope: 'LABOR', unit: 'M2', position: 0 });
    const line2 = makeLine({ id: 'line-2', scope: 'LABOR', unit: 'LM', position: 1 });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([line1, line2]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const groups = screen.getAllByLabelText(/^estimate-group-\d+$/);
    expect(groups.length).toBe(2);
  });

  it('surface line and reveal line with same price_item_id go into separate groups', async () => {
    const surfaceLine = makeLine({ id: 'line-1', opening_id: null, position: 0 });
    const revealLine = makeLine({ id: 'line-2', opening_id: 'op-1', position: 1 });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([surfaceLine, revealLine]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const groups = screen.getAllByLabelText(/^estimate-group-\d+$/);
    expect(groups.length).toBe(2);
  });

  it('MANUAL lines each get their own group (no merging)', async () => {
    const m1 = makeLine({ id: 'line-1', origin: 'MANUAL', price_item_id: null, position: 0 });
    const m2 = makeLine({ id: 'line-2', origin: 'MANUAL', price_item_id: null, position: 1 });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([m1, m2]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const groups = screen.getAllByLabelText(/^estimate-group-\d+$/);
    expect(groups.length).toBe(2);
  });

  it('two lines with same price_item_id, scope, unit, and no opening_id merge into one group', async () => {
    const line1 = makeLine({ id: 'line-1', position: 0 });
    const line2 = makeLine({ id: 'line-2', position: 1 });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([line1, line2]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const groups = screen.getAllByLabelText(/^estimate-group-\d+$/);
    expect(groups.length).toBe(1);
  });
});

// ─── Stage 10G.2 owner-reported crash: real API payload, real click flow ──────
//
// The tests above render EstimateShell with selectedGroupKey passed in directly
// as a prop, so they never exercise the actual state transition a tap performs
// in production: ProjectWorkspace owns selectedEstimateGroupKey and re-renders
// EstimateShell with the new key after onGroupKeyChange fires. This harness
// mirrors that ownership so a tap-to-drilldown regression can't hide behind a
// mocked onGroupKeyChange. The fixture is a byte-accurate capture of a real
// GET /estimates/{id} response (2 walls sharing one PriceItem + 1 window reveal
// line whose Opening has no name — Opening.name is optional and most real
// openings are unnamed) produced by EstimateService.generate_estimate via the
// backend test suite, not hand-written.
describe('real API payload — full tap-to-drilldown flow (regression)', () => {
  const REAL_ESTIMATE: EstimateRead = {
    id: '812c1e0a-80c2-4a64-9a78-df825f450c83',
    project_id: PROJECT_ID,
    version: 1,
    status: 'DRAFT',
    name: null,
    total: '460850.00',
    currency: 'PLN',
    created_at: '2026-09-18T16:21:26.824207',
    updated_at: '2026-09-18T16:21:26.869577',
    lines: [
      {
        id: 'b7bd7b4f-fc8b-4828-b875-678c4b50342d',
        estimate_id: ESTIMATE_ID,
        origin: 'PLANNED_WORK',
        position: 0,
        description: 'SKIM_M2',
        item_code: 'SKIM_M2',
        unit: 'M2',
        scope: 'LABOR',
        currency: 'PLN',
        source_quantity: '10.382',
        quantity: '10.382',
        quantity_source: 'SURFACE_NET_AREA',
        quantity_overridden: false,
        unit_price: '25.00',
        price_override: false,
        amount: '259.55',
        price_item_id: '5fef7918-e4fa-4f50-b5a9-deb6ad6a2f06',
        plan_id: '4ecccd96-d0de-43a8-9d8f-f4a47f12300c',
        planned_work_id: 'c262c470-21dd-4170-8397-99d85f1c805a',
        surface_id: 'a977730e-3256-4c9c-8f18-a323d5f3fdad',
        room_id: '5965b01f-c3e5-4820-bc9f-51af508bc6ff',
        opening_id: null,
        room_name: 'Salon',
        surface_name: 'Ściana 1',
        surface_type_value: 'WALL',
        opening_name: null,
        opening_type_value: null,
      },
      {
        id: 'fe01ae29-14e0-4d38-99cc-fa9b8b348cca',
        estimate_id: ESTIMATE_ID,
        origin: 'PLANNED_WORK',
        position: 1,
        description: 'SKIM_M2',
        item_code: 'SKIM_M2',
        unit: 'M2',
        scope: 'LABOR',
        currency: 'PLN',
        source_quantity: '7.800',
        quantity: '7.800',
        quantity_source: 'SURFACE_NET_AREA',
        quantity_overridden: false,
        unit_price: '25.00',
        price_override: false,
        amount: '195.00',
        price_item_id: '5fef7918-e4fa-4f50-b5a9-deb6ad6a2f06',
        plan_id: 'fc61feda-33db-4dfa-b8c5-c38ae70e4dd1',
        planned_work_id: 'ebad57ac-72a4-4f37-aedd-eada0f70271c',
        surface_id: '50861018-f3aa-44a2-8746-9d4042d08a51',
        room_id: '5965b01f-c3e5-4820-bc9f-51af508bc6ff',
        opening_id: null,
        room_name: 'Salon',
        surface_name: 'Ściana 2',
        surface_type_value: 'WALL',
        opening_name: null,
        opening_type_value: null,
      },
      {
        id: '1135a081-c3a4-4ae1-9c86-a25f15573899',
        estimate_id: ESTIMATE_ID,
        origin: 'PLANNED_WORK',
        position: 2,
        description: 'REVEAL_LM',
        item_code: 'REVEAL_LM',
        unit: 'LM',
        scope: 'LABOR',
        currency: 'PLN',
        source_quantity: '4.200',
        quantity: '4.200',
        quantity_source: 'REVEAL_LENGTH',
        quantity_overridden: false,
        unit_price: '15.00',
        price_override: false,
        amount: '63.00',
        price_item_id: 'b3355745-b59f-4693-97db-76fff202d8a5',
        plan_id: null,
        planned_work_id: 'cb3d6594-7c56-40f0-bfc3-0f5059ddf50e',
        surface_id: 'a977730e-3256-4c9c-8f18-a323d5f3fdad',
        room_id: '5965b01f-c3e5-4820-bc9f-51af508bc6ff',
        opening_id: '2ea33940-9a35-4ba4-8405-a1f0965973f6',
        room_name: 'Salon',
        surface_name: 'Ściana 1',
        surface_type_value: 'WALL',
        opening_name: null,
        opening_type_value: 'WINDOW',
      },
    ],
  };

  function RealPayloadHarness() {
    const [key, setKey] = useState<string | null>(null);
    return (
      <EstimateShell
        estimate={makeSummary()}
        onBack={vi.fn()}
        selectedGroupKey={key}
        onGroupKeyChange={setKey}
      />
    );
  }

  it('tapping every group card (including a nameless-opening reveal group) opens drill-down and back without throwing', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(REAL_ESTIMATE);
    render(
      <I18nProvider>
        <RealPayloadHarness />
      </I18nProvider>,
    );

    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const groupCount = screen.getAllByLabelText(/^estimate-group-\d+$/).length;
    expect(groupCount).toBe(2); // merged surface group (2 walls) + reveal group

    for (let i = 0; i < groupCount; i++) {
      fireEvent.click(screen.getByLabelText(`estimate-group-${i}`));
      await waitFor(() => screen.getByLabelText('estimate-lines'));
      expect(screen.getByLabelText('estimate-detail-back')).toBeTruthy();
      fireEvent.click(screen.getByLabelText('estimate-detail-back'));
      await waitFor(() => screen.getByLabelText('estimate-groups'));
    }
  });

  it('reveal line with a nameless opening falls back to the type label in the real drill-down', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(REAL_ESTIMATE);
    render(
      <I18nProvider>
        <RealPayloadHarness />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const revealGroup = screen.getAllByLabelText(/^estimate-group-\d+$/)[1];
    fireEvent.click(revealGroup);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-provenance-2').textContent).toContain('Okno');
  });
});

// ─── Stage 10G.2 owner-reported crash: surface_name undefined, not null ─────
//
// Real browser stack trace: getSurfaceDisplayName (surfaceDisplayName.ts:17)
// threw "Cannot read properties of undefined (reading 'trim')" when called
// from provenanceSurfaceLabel during the grouped → drill-down rerender. The
// pre-fix guard was `line.surface_name === null`, which is false when the
// key is `undefined` (omitted) rather than explicit JSON `null` — so it fell
// through into getSurfaceDisplayName with an undefined `name`. This fixture
// reproduces that exact shape: `surface_id` is set (so the line is presented
// as surface-anchored) but the `surface_name` key itself is deleted from the
// object, matching a response that omits the field entirely.
describe('Stage 10G.2 confirmed crash — surface_name key omitted (undefined) while surface_type_value is present', () => {
  function UndefinedSurfaceNameHarness() {
    const [key, setKey] = useState<string | null>(null);
    return (
      <EstimateShell
        estimate={makeSummary()}
        onBack={vi.fn()}
        selectedGroupKey={key}
        onGroupKeyChange={setKey}
      />
    );
  }

  function makeLineWithOmittedSurfaceName(): EstimateLineRead {
    const line = makeLine({ position: 0, surface_id: 'surf-omitted-name', surface_type_value: 'WALL' });
    delete (line as { surface_name?: string | null }).surface_name;
    return line;
  }

  it('does not throw on click → drill-down rerender, and falls back to the canonical WALL label', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLineWithOmittedSurfaceName()]));

    render(
      <I18nProvider>
        <UndefinedSurfaceNameHarness />
      </I18nProvider>,
    );

    await waitFor(() => screen.getByLabelText('estimate-groups'));

    expect(() => {
      fireEvent.click(screen.getByLabelText('estimate-group-0'));
    }).not.toThrow();

    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-detail-back')).toBeTruthy();
    // room_name ('Salon') is still available from makeLine()'s defaults; only
    // surface_name is omitted, so it falls back to the canonical WALL label.
    expect(screen.getByLabelText('line-provenance-0').textContent).toBe('Salon — Ściana');
  });

  it('omits the surface provenance row entirely when surface_name is omitted AND surface_type_value is absent', async () => {
    const line = makeLine({ position: 0, surface_id: 'surf-omitted-name', surface_type_value: null, room_name: null });
    delete (line as { surface_name?: string | null }).surface_name;
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([line]));

    render(
      <I18nProvider>
        <UndefinedSurfaceNameHarness />
      </I18nProvider>,
    );

    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('estimate-group-0'));
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    expect(screen.queryByLabelText('line-provenance-0')).toBeNull();
  });
});

// ─── Stage 10G.3A — draft line editing and override resets ───────────────────

describe('Stage 10G.3A — draft-only editing gating', () => {
  it('shows the Edytuj action for a DRAFT estimate', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-edit-action-1')).toBeTruthy();
  });

  it('does not render any edit action for a FINAL estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'FINAL' }));
    renderShell(makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-edit-action-1')).toBeNull();
  });

  it('does not render any edit action for an ACCEPTED estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'ACCEPTED' }));
    renderShell(makeSummary({ status: 'ACCEPTED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-edit-action-1')).toBeNull();
  });

  it('does not render any edit action for an ARCHIVED estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'ARCHIVED' }));
    renderShell(makeSummary({ status: 'ARCHIVED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-edit-action-1')).toBeNull();
  });

  it('does not merely disable but omits reset actions too for an immutable estimate, even when override flags are set', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ quantity_overridden: true, price_override: true })], { status: 'FINAL' }),
    );
    renderShell(makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-reset-quantity-1')).toBeNull();
    expect(screen.queryByLabelText('line-reset-price-1')).toBeNull();
  });

  it('does not render edit actions in the grouped summary view', async () => {
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('line-edit-action-1')).toBeNull();
  });
});

describe('Stage 10G.3A — quantity edit', () => {
  it('pre-fills the exact quantity string and submits the exact decimal string typed (no Number/parseFloat)', async () => {
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(makeLine({ quantity: '13.750', quantity_overridden: true }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-quantity-1'))) as HTMLInputElement;
    expect(input.value).toBe('12.500');

    fireEvent.change(input, { target: { value: '13.750' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { quantity: '13.750' },
      );
    });
  });

  it('does not send a quantity field when the value is unchanged from the original', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    await waitFor(() => screen.getByLabelText('line-edit-quantity-1'));
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));
    await waitFor(() => expect(screen.queryByLabelText('line-edit-panel-1')).toBeNull());
    expect(estimatesApi.patchEstimateLine).not.toHaveBeenCalled();
  });

  it('rejects a non-numeric quantity locally, without any network call', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-quantity-1'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'abc' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => screen.getByLabelText('line-edit-error-1'));
    expect(estimatesApi.patchEstimateLine).not.toHaveBeenCalled();
  });
});

describe('Stage 10G.3A — quantity reset', () => {
  it('shows the reset action only when quantity_overridden is true', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-reset-quantity-1')).toBeNull();
  });

  it('tapping the quantity reset sends exactly { reset_quantity_override: true }', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine({ quantity_overridden: true })]));
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(makeLine({ quantity_overridden: false }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-reset-quantity-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { reset_quantity_override: true },
      );
    });
  });
});

describe('Stage 10G.3A — price edit', () => {
  it('pre-fills the exact unit_price string and submits the exact decimal string typed', async () => {
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(makeLine({ unit_price: '42.750', price_override: true }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-price-1'))) as HTMLInputElement;
    expect(input.value).toBe('35.00');

    fireEvent.change(input, { target: { value: '42.750' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { unit_price: '42.750' },
      );
    });
  });

  it('submits an explicit unit_price: null when the "Cena do ustalenia" toggle is checked', async () => {
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: null, price_override: true, amount: null }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    await waitFor(() => screen.getByLabelText('line-edit-price-unresolved-1'));
    fireEvent.click(screen.getByLabelText('line-edit-price-unresolved-1'));
    expect(screen.queryByLabelText('line-edit-price-1')).toBeNull();

    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { unit_price: null },
      );
    });
  });

  it('a typed "0.00" submits as the string "0.00", never as null', async () => {
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: '0.00', price_override: true, amount: '0.00' }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-price-1'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '0.00' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { unit_price: '0.00' },
      );
    });
  });

  it('opening the panel for a line whose unit_price is already "0.00" leaves the unresolved toggle unchecked (0.00 is distinct from null)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: '0.00', amount: '0.00' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const toggle = (await waitFor(() => screen.getByLabelText('line-edit-price-unresolved-1'))) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    expect((screen.getByLabelText('line-edit-price-1') as HTMLInputElement).value).toBe('0.00');
  });

  it('opening the panel for a line whose unit_price is null pre-checks the unresolved toggle and hides the numeric input', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: null, amount: null })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const toggle = (await waitFor(() => screen.getByLabelText('line-edit-price-unresolved-1'))) as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    expect(screen.queryByLabelText('line-edit-price-1')).toBeNull();
  });
});

describe('Stage 10G.3A — price reset', () => {
  it('tapping the price reset sends exactly { reset_price_override: true }', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine({ price_override: true })]));
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(makeLine({ price_override: false }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-reset-price-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { reset_price_override: true },
      );
    });
  });

  it('does not render the price-reset action for a MANUAL line, even when price_override is true (backend rejects it — no PriceBook source)', async () => {
    const manualLine = makeLine({
      origin: 'MANUAL',
      price_item_id: null,
      price_override: true,
      quantity_overridden: true,
    });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([manualLine]));
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    expect(screen.queryByLabelText('line-reset-price-1')).toBeNull();
    // Quantity reset has no such backend restriction and remains available.
    expect(screen.getByLabelText('line-reset-quantity-1')).toBeTruthy();
  });
});

describe('Stage 10G.3A — authoritative refetch after mutation', () => {
  it('a successful edit refetches the Estimate detail rather than mutating local state optimistically', async () => {
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(makeLine({ quantity: '20.000', quantity_overridden: true }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-quantity-1'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '20.000' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(2));
  });

  it('the drill-down and override indicators reflect the refetched authoritative data, not the submitted form values', async () => {
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ quantity: '20.000', quantity_overridden: true, amount: '700.00' }),
    );
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([makeLine()]))
      .mockResolvedValueOnce(
        makeDetail([makeLine({ quantity: '20.000', quantity_overridden: true, amount: '700.00' })]),
      );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-quantity-1'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '20.000' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => screen.getByLabelText('line-qty-override-1'));
    expect(screen.getByLabelText('line-quantity-1').textContent).toContain('20.000');
    expect(screen.getByLabelText('line-amount-1').textContent).toContain('700.00');
  });

  it('the grouped summary rebuilds from the refetched lines using the existing grouping engine (no second engine)', async () => {
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ quantity: '20.000', quantity_overridden: true, amount: '700.00' }),
    );
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([makeLine()]))
      .mockResolvedValueOnce(
        makeDetail([makeLine({ quantity: '20.000', quantity_overridden: true, amount: '700.00' })]),
      );

    function RefetchGroupedHarness() {
      const [key, setKey] = useState<string | null>(PLANNED_SURFACE_KEY);
      return (
        <EstimateShell
          estimate={makeSummary()}
          onBack={vi.fn()}
          selectedGroupKey={key}
          onGroupKeyChange={setKey}
        />
      );
    }

    render(
      <I18nProvider>
        <RefetchGroupedHarness />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-quantity-1'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '20.000' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));
    await waitFor(() => screen.getByLabelText('line-qty-override-1'));

    fireEvent.click(screen.getByLabelText('estimate-detail-back'));
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-quantity-0').textContent).toContain('20.000');
    expect(screen.getByLabelText('group-has-overrides-0')).toBeTruthy();
  });
});

describe('Stage 10G.3A — cancel and error handling', () => {
  it('Anuluj discards the edit without calling the API', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-quantity-1'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '999.000' } });
    fireEvent.click(screen.getByLabelText('line-edit-cancel-1'));

    expect(estimatesApi.patchEstimateLine).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('line-edit-panel-1')).toBeNull();
    expect(screen.getByLabelText('line-edit-action-1')).toBeTruthy();
  });

  it('a PATCH failure (422) shows an inline error, keeps the drill-down and edit panel rendered, and does not blank the page', async () => {
    vi.mocked(estimatesApi.patchEstimateLine).mockRejectedValue(new Error('quantity cannot be null'));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-quantity-1'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '20.000' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => screen.getByLabelText('line-edit-error-1'));
    expect(screen.getByLabelText('line-edit-error-1').textContent).toBe('quantity cannot be null');
    expect(screen.getByLabelText('line-edit-panel-1')).toBeTruthy();
    expect(screen.getByLabelText('estimate-lines')).toBeTruthy();
    // the previous authoritative quantity is preserved — no optimistic mutation
    expect((screen.getByLabelText('line-edit-quantity-1') as HTMLInputElement).value).toBe('20.000');
  });

  it('a reset failure shows an inline error near that line without discarding the previous authoritative line data', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine({ quantity_overridden: true })]));
    vi.mocked(estimatesApi.patchEstimateLine).mockRejectedValue(new Error('Estimate is not a DRAFT'));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-reset-quantity-1'));

    await waitFor(() => screen.getByLabelText('line-edit-error-1'));
    expect(screen.getByLabelText('line-edit-error-1').textContent).toBe('Estimate is not a DRAFT');
    expect(screen.getByLabelText('line-quantity-1').textContent).toContain('12.500');
  });
});

describe('Stage 10G.3A — mobile UX', () => {
  it('edit/save/cancel/reset controls all meet the 44px minimum touch target', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ quantity_overridden: true, price_override: true })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    expect(screen.getByLabelText('line-edit-action-1').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('line-reset-quantity-1').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('line-reset-price-1').className).toContain('min-h-[44px]');

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    await waitFor(() => screen.getByLabelText('line-edit-save-1'));
    expect(screen.getByLabelText('line-edit-save-1').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('line-edit-cancel-1').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('line-edit-quantity-1').className).toContain('min-h-[44px]');
  });

  it('quantity and price inputs use inputMode="decimal" for mobile numeric keyboards', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const qtyInput = await waitFor(() => screen.getByLabelText('line-edit-quantity-1'));
    const priceInput = screen.getByLabelText('line-edit-price-1');
    expect(qtyInput.getAttribute('inputmode')).toBe('decimal');
    expect(priceInput.getAttribute('inputmode')).toBe('decimal');
  });
});

describe('Stage 10G.3A regression — existing 10G.2 UI untouched', () => {
  it('the grouped summary view still renders groups with no edit controls leaking in', async () => {
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-group-0')).toBeTruthy();
    expect(screen.queryByLabelText('line-edit-action-1')).toBeNull();
  });

  it('an atomic line not being edited still renders quantity/price/amount exactly as in 10G.2, with Edytuj alongside (not replacing) them', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-quantity-1').textContent).toContain('12.500');
    expect(screen.getByLabelText('line-unit-price-1').textContent).toContain('35.00');
    expect(screen.getByLabelText('line-amount-1').textContent).toContain('437.50');
    expect(screen.getByLabelText('line-edit-action-1')).toBeTruthy();
    expect(screen.queryByLabelText('line-edit-panel-1')).toBeNull();
  });
});

// ─── Stage 10G.3A — group-level bulk price editing ────────────────────────────

function renderGroupedShell(
  lines: EstimateLineRead[] = [makeLine()],
  summary: EstimateSummaryRead = makeSummary(),
) {
  vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail(lines, { status: summary.status }));
  render(
    <I18nProvider>
      <EstimateShell estimate={summary} onBack={vi.fn()} selectedGroupKey={null} onGroupKeyChange={vi.fn()} />
    </I18nProvider>,
  );
}

describe('Stage 10G.3A — group price edit: visibility gating', () => {
  it('a DRAFT group exposes the Opcje control', async () => {
    renderGroupedShell();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-options-0')).toBeTruthy();
  });

  it('does not expose Opcje for a FINAL estimate', async () => {
    renderGroupedShell([makeLine()], makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('group-options-0')).toBeNull();
  });

  it('does not expose Opcje for an ACCEPTED estimate', async () => {
    renderGroupedShell([makeLine()], makeSummary({ status: 'ACCEPTED' }));
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('group-options-0')).toBeNull();
  });

  it('does not expose Opcje for an ARCHIVED estimate', async () => {
    renderGroupedShell([makeLine()], makeSummary({ status: 'ARCHIVED' }));
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('group-options-0')).toBeNull();
  });

  it('opening Opcje reveals the group price-edit action', async () => {
    renderGroupedShell();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    expect(screen.getByLabelText('group-price-edit-action-0')).toBeTruthy();
  });

  it('shows the reset-all action for a PLANNED_WORK group', async () => {
    renderGroupedShell();
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    expect(screen.getByLabelText('group-reset-price-action-0')).toBeTruthy();
  });

  it('does not offer the reset-all action for a MANUAL group (no PriceBook source to restore from)', async () => {
    renderGroupedShell([
      makeLine({ origin: 'MANUAL', price_item_id: null, price_override: true }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    expect(screen.queryByLabelText('group-reset-price-action-0')).toBeNull();
  });
});

describe('Stage 10G.3A — group price edit: exact targeting (group.lines only)', () => {
  it('applies the price to exactly the 4 lines in the group, never to a same-description line outside the group', async () => {
    const groupLines = [
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00' }),
      makeLine({ id: 'l3', position: 3, unit_price: '35.00' }),
      makeLine({ id: 'l4', position: 4, unit_price: '35.00' }),
    ];
    const outsideLine = makeLine({
      id: 'outside',
      position: 5,
      origin: 'MANUAL',
      price_item_id: null,
      description: groupLines[0].description,
      unit_price: '35.00',
    });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([...groupLines, outsideLine]));
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: '40.00', price_override: true }),
    );
    render(
      <I18nProvider>
        <EstimateShell estimate={makeSummary()} onBack={vi.fn()} selectedGroupKey={null} onGroupKeyChange={vi.fn()} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));

    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '40.00' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));

    await waitFor(() => expect(estimatesApi.patchEstimateLine).toHaveBeenCalledTimes(4));
    const patchedIds = vi.mocked(estimatesApi.patchEstimateLine).mock.calls.map((call) => call[2]);
    expect([...patchedIds].sort()).toEqual(['l1', 'l2', 'l3', 'l4']);
    expect(patchedIds).not.toContain('outside');
    for (const call of vi.mocked(estimatesApi.patchEstimateLine).mock.calls) {
      expect(call[3]).toEqual({ unit_price: '40.00' });
    }
  });
});

describe('Stage 10G.3A — group price edit: prefill states', () => {
  it('pre-fills the uniform unit_price when every line shares the same non-null price', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00' }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    expect(input.value).toBe('35.00');
    expect(screen.queryByLabelText('group-price-edit-mixed-0')).toBeNull();
  });

  it('starts in the unresolved state and hides the numeric input when every line has unit_price null', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: null, amount: null }),
      makeLine({ id: 'l2', position: 2, unit_price: null, amount: null }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const toggle = (await waitFor(() => screen.getByLabelText('group-price-edit-unresolved-0'))) as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    expect(screen.queryByLabelText('group-price-edit-value-0')).toBeNull();
  });

  it('shows an empty input and a "Różne ceny" indicator when group prices differ, without inventing a common value', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '40.00' }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    expect(input.value).toBe('');
    expect(screen.getByLabelText('group-price-edit-mixed-0').textContent).toBe('Różne ceny');
  });
});

describe('Stage 10G.3A — group price edit: numeric, zero, and NULL submission', () => {
  it('submits the exact decimal string typed to every line in the group (no Number/parseFloat)', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00' }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: '42.750', price_override: true }),
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '42.750' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));

    await waitFor(() => expect(estimatesApi.patchEstimateLine).toHaveBeenCalledTimes(2));
    for (const call of vi.mocked(estimatesApi.patchEstimateLine).mock.calls) {
      expect(call[3]).toEqual({ unit_price: '42.750' });
    }
  });

  it('sends unit_price "0.00" unchanged to every line, never as null', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00' }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: '0.00', amount: '0.00', price_override: true }),
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '0.00' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));

    await waitFor(() => expect(estimatesApi.patchEstimateLine).toHaveBeenCalledTimes(2));
    for (const call of vi.mocked(estimatesApi.patchEstimateLine).mock.calls) {
      expect(call[3]).toEqual({ unit_price: '0.00' });
    }
  });

  it('applies explicit unit_price: null to every line when the "Cena do ustalenia" toggle is used', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00' }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: null, amount: null, price_override: true }),
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const toggle = (await waitFor(() => screen.getByLabelText('group-price-edit-unresolved-0'))) as HTMLInputElement;
    fireEvent.click(toggle);
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));

    await waitFor(() => expect(estimatesApi.patchEstimateLine).toHaveBeenCalledTimes(2));
    for (const call of vi.mocked(estimatesApi.patchEstimateLine).mock.calls) {
      expect(call[3]).toEqual({ unit_price: null });
    }
  });

  it('rejects a non-numeric group price locally, without any network call', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00' }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'abc' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));

    await waitFor(() => screen.getByLabelText('group-price-edit-error-0'));
    expect(estimatesApi.patchEstimateLine).not.toHaveBeenCalled();
  });
});

describe('Stage 10G.3A — group reset-all prices', () => {
  it('sends { reset_price_override: true } to every line in the group', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, price_override: true, unit_price: '40.00' }),
      makeLine({ id: 'l2', position: 2, price_override: true, unit_price: '40.00' }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: '35.00', price_override: false }),
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-reset-price-action-0'));

    await waitFor(() => expect(estimatesApi.patchEstimateLine).toHaveBeenCalledTimes(2));
    for (const call of vi.mocked(estimatesApi.patchEstimateLine).mock.calls) {
      expect(call[3]).toEqual({ reset_price_override: true });
    }
  });
});

describe('Stage 10G.3A — group price edit refetch', () => {
  it('a successful group price edit refetches the Estimate detail rather than mutating local state', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1 }),
      makeLine({ id: 'l2', position: 2 }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: '40.00', price_override: true }),
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '40.00' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));

    await waitFor(() => expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(2));
  });

  it('a successful group price edit closes the editor panel', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1 }),
      makeLine({ id: 'l2', position: 2 }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: '40.00', price_override: true }),
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));

    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '40.00' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));

    await waitFor(() => expect(screen.queryByLabelText('group-price-edit-panel-0')).toBeNull());
  });
});

describe('Stage 10G.3A — group price edit partial failure safety', () => {
  it('stops after the first failed PATCH, never reports success, and refetches the authoritative Estimate', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1 }),
      makeLine({ id: 'l2', position: 2 }),
      makeLine({ id: 'l3', position: 3 }),
      makeLine({ id: 'l4', position: 4 }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine)
      .mockResolvedValueOnce(makeLine({ unit_price: '40.00', price_override: true }))
      .mockResolvedValueOnce(makeLine({ unit_price: '40.00', price_override: true }))
      .mockRejectedValueOnce(new Error('boom'));

    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '40.00' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));

    await waitFor(() => screen.getByLabelText('group-price-edit-error-0'));
    // exactly 3 PATCH calls: 2 succeeded, the 3rd failed, the 4th was never attempted
    expect(estimatesApi.patchEstimateLine).toHaveBeenCalledTimes(3);
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(2);
    expect(screen.getByLabelText('group-price-edit-error-0').textContent).toBe(
      'Nie wszystkie pozycje zostały zaktualizowane. Sprawdź grupę i spróbuj ponownie.',
    );
    // the editor stays open and recoverable — no silent frontend rollback, no false success
    expect(screen.getByLabelText('group-price-edit-panel-0')).toBeTruthy();
    expect((screen.getByLabelText('group-price-edit-value-0') as HTMLInputElement).value).toBe('40.00');
  });

  it('a reset-all partial failure also refetches and shows an inline error without closing the group options', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, price_override: true }),
      makeLine({ id: 'l2', position: 2, price_override: true }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine)
      .mockResolvedValueOnce(makeLine({ unit_price: '35.00', price_override: false }))
      .mockRejectedValueOnce(new Error('boom'));

    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-reset-price-action-0'));

    await waitFor(() => screen.getByLabelText('group-price-edit-error-0'));
    expect(estimatesApi.patchEstimateLine).toHaveBeenCalledTimes(2);
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(2);
    expect(screen.getByLabelText('group-reset-price-action-0')).toBeTruthy();
  });
});

describe('Stage 10G.3A — no group quantity editing', () => {
  it('the group options panel never exposes a quantity input or a quantity-edit action', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1 }),
      makeLine({ id: 'l2', position: 2 }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const panel = await waitFor(() => screen.getByLabelText('group-price-edit-panel-0'));
    expect(within(panel).queryByLabelText(/quantity/i)).toBeNull();
    expect(within(panel).queryAllByRole('textbox').length).toBe(1); // only the price value input
  });
});

describe('Stage 10G.3A — individual overrides remain possible after a group edit', () => {
  it('when the refetch shows one differing overridden line, the group summary is represented as mixed, not the old uniform price', async () => {
    const mixedLines = [
      makeLine({ id: 'l1', position: 1, unit_price: '35.00', price_override: false }),
      makeLine({ id: 'l2', position: 2, unit_price: '40.00', price_override: true }),
      makeLine({ id: 'l3', position: 3, unit_price: '35.00', price_override: false }),
      makeLine({ id: 'l4', position: 4, unit_price: '35.00', price_override: false }),
    ];
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail(mixedLines));
    const { unmount } = render(
      <I18nProvider>
        <EstimateShell estimate={makeSummary()} onBack={vi.fn()} selectedGroupKey={null} onGroupKeyChange={vi.fn()} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));

    expect(screen.queryByLabelText('group-unit-price-0')).toBeNull();
    expect(screen.getByLabelText('group-has-overrides-0')).toBeTruthy();
    unmount();

    // Drilling into the same group (selectedGroupKey preset, as the parent
    // screen would do after onGroupKeyChange) still allows an atomic edit.
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail(mixedLines));
    render(
      <I18nProvider>
        <EstimateShell
          estimate={makeSummary()}
          onBack={vi.fn()}
          selectedGroupKey={PLANNED_SURFACE_KEY}
          onGroupKeyChange={vi.fn()}
        />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-edit-action-2')).toBeTruthy();
  });
});

describe('Stage 10G.3A — group price edit mobile touch targets', () => {
  it('Opcje, set-price, reset, save, cancel, and the input all meet the 44px minimum', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1 }),
      makeLine({ id: 'l2', position: 2 }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));

    expect(screen.getByLabelText('group-options-0').className).toContain('min-h-[44px]');
    fireEvent.click(screen.getByLabelText('group-options-0'));
    expect(screen.getByLabelText('group-price-edit-action-0').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('group-reset-price-action-0').className).toContain('min-h-[44px]');

    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    await waitFor(() => screen.getByLabelText('group-price-edit-save-0'));
    expect(screen.getByLabelText('group-price-edit-save-0').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('group-price-edit-cancel-0').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('group-price-edit-value-0').className).toContain('min-h-[44px]');
  });
});

describe('Stage 10G.3A — group price edit Russian localization', () => {
  it('shows RU labels for Opcje, set-price, reset-all, and the mixed-price indicator', async () => {
    localStorage.setItem('locale', 'ru');
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '40.00' }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));

    expect(screen.getByLabelText('group-options-0').textContent).toBe('Опции');
    fireEvent.click(screen.getByLabelText('group-options-0'));
    expect(screen.getByLabelText('group-price-edit-action-0').textContent).toBe('Установить цену для всех');
    expect(screen.getByLabelText('group-reset-price-action-0').textContent).toBe('Восстановить цены из прайса');

    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    await waitFor(() => screen.getByLabelText('group-price-edit-mixed-0'));
    expect(screen.getByLabelText('group-price-edit-mixed-0').textContent).toBe('Разные цены');
  });
});

describe('Stage 10G.3A — group price edit cancel', () => {
  it('Anuluj discards the group edit without calling the API', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00' }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '999.00' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-cancel-0'));

    expect(estimatesApi.patchEstimateLine).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('group-price-edit-panel-0')).toBeNull();
  });
});

// ─── Stage 10G.3A final polish — header action placement ─────────────────────

describe('Stage 10G.3A polish — group Opcje placement (upper-right, beside header)', () => {
  it('Opcje remains available and sits as a sibling of the drill-down button in the same header row', async () => {
    renderGroupedShell([makeLine({ id: 'l1', position: 1 }), makeLine({ id: 'l2', position: 2 })]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));

    const opcje = screen.getByLabelText('group-options-0');
    const drilldown = screen.getByLabelText('estimate-group-0');
    expect(opcje.parentElement).toBe(drilldown.parentElement);
    expect(opcje.parentElement?.className).toContain('flex');
    expect(opcje.parentElement?.className).toContain('items-start');
  });

  it('Opcje still opens the existing group price-edit and reset-all actions unchanged', async () => {
    renderGroupedShell([makeLine({ id: 'l1', position: 1 }), makeLine({ id: 'l2', position: 2 })]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('group-options-0'));
    expect(screen.getByLabelText('group-price-edit-action-0')).toBeTruthy();
    expect(screen.getByLabelText('group-reset-price-action-0')).toBeTruthy();
    expect(screen.getByLabelText('group-options-close-0')).toBeTruthy();
  });

  it('does not render Opcje for a FINAL estimate (DRAFT-only gating preserved)', async () => {
    renderGroupedShell([makeLine()], makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('group-options-0')).toBeNull();
  });

  it('a long PL description wraps instead of forcing horizontal overflow, and Opcje stays beside it without overlapping', async () => {
    const longDescription =
      'Bardzo długa nazwa pracy renowacyjnej opisująca wiele szczegółów technicznych i wymagań podłoża '.repeat(2);
    renderGroupedShell([makeLine({ description: longDescription })]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));

    const desc = screen.getByLabelText('group-description-0');
    expect(desc.className).toContain('break-words');
    expect(desc.className).toContain('min-w-0');
    expect(screen.getByLabelText('estimate-group-0').className).toContain('min-w-0');
    expect(screen.getByLabelText('estimate-group-0').className).toContain('flex-1');
    expect(screen.getByLabelText('group-options-0').className).toContain('shrink-0');
  });
});

describe('Stage 10G.3A polish — atomic Edytuj placement (upper-right, beside header badges)', () => {
  it('Edytuj remains available and sits in the same header row as the badges, right-aligned via justify-between', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    const edit = screen.getByLabelText('line-edit-action-1');
    const origin = screen.getByLabelText('line-origin-1');
    const headerRow = edit.parentElement;
    expect(headerRow?.className).toContain('justify-between');
    expect(headerRow?.contains(origin)).toBe(true);
  });

  it('does not render Edytuj while the line is being edited (edit panel takes its place)', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    await waitFor(() => screen.getByLabelText('line-edit-panel-1'));
    expect(screen.queryByLabelText('line-edit-action-1')).toBeNull();
  });

  it('does not render Edytuj for a FINAL estimate (DRAFT-only gating preserved)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'FINAL' }));
    renderShell(makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-edit-action-1')).toBeNull();
  });

  it('a line with no overrides and not being edited renders no leftover footer controls', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-edit-panel-1')).toBeNull();
    expect(screen.queryByLabelText('line-reset-quantity-1')).toBeNull();
    expect(screen.queryByLabelText('line-reset-price-1')).toBeNull();
    expect(screen.getByLabelText('line-quantity-1').textContent).toContain('12.500');
  });

  it('a long PL description wraps and Edytuj stays available without overlapping the badges', async () => {
    const longDescription =
      'Bardzo długa nazwa pozycji kosztorysowej opisująca szczegółowo zakres prac i materiały '.repeat(2);
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine({ description: longDescription })]));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    const desc = screen.getByLabelText('line-description-1');
    expect(desc.className).toContain('break-words');
    expect(desc.className).toContain('min-w-0');
    expect(screen.getByLabelText('line-edit-action-1').className).toContain('shrink-0');
  });
});

describe('Stage 10G.3A polish — regression: all previously accepted behavior unchanged', () => {
  it('group price edit end-to-end flow still works from the relocated Opcje trigger', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00' }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: '40.00', price_override: true }),
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));

    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '40.00' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));

    await waitFor(() => expect(estimatesApi.patchEstimateLine).toHaveBeenCalledTimes(2));
    for (const call of vi.mocked(estimatesApi.patchEstimateLine).mock.calls) {
      expect(call[3]).toEqual({ unit_price: '40.00' });
    }
  });

  it('atomic edit end-to-end flow still works from the relocated Edytuj trigger', async () => {
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ quantity: '13.750', quantity_overridden: true }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-quantity-1'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '13.750' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { quantity: '13.750' },
      );
    });
  });
});

// ─── Stage 10G.3B — regeneration preview and explicit confirmation ───────────

function StatefulGroupedShell() {
  const [key, setKey] = useState<string | null>(null);
  return (
    <EstimateShell estimate={makeSummary()} onBack={vi.fn()} selectedGroupKey={key} onGroupKeyChange={setKey} />
  );
}

describe('Stage 10G.3B — Sprawdź zmiany visibility (DRAFT-only, whole-project)', () => {
  it('a DRAFT estimate shows Sprawdź zmiany in the detail view', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();
  });

  it('a DRAFT estimate shows Sprawdź zmiany in the grouped summary view (not scoped to a group)', async () => {
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();
  });

  it('does not expose Sprawdź zmiany for a FINAL estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'FINAL' }));
    renderShell(makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('estimate-check-changes-action')).toBeNull();
  });

  it('does not expose Sprawdź zmiany for an ACCEPTED estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'ACCEPTED' }));
    renderShell(makeSummary({ status: 'ACCEPTED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('estimate-check-changes-action')).toBeNull();
  });

  it('does not expose Sprawdź zmiany for an ARCHIVED estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'ARCHIVED' }));
    renderShell(makeSummary({ status: 'ARCHIVED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('estimate-check-changes-action')).toBeNull();
  });
});

describe('Stage 10G.3B — preview call is read-only from the frontend perspective', () => {
  it('calls previewEstimateRegeneration with the correct project and estimate ids', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(makePreview());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => {
      expect(estimatesApi.previewEstimateRegeneration).toHaveBeenCalledWith(PROJECT_ID, ESTIMATE_ID);
    });
  });

  it('opening preview never calls patchEstimateLine or regenerateEstimate', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-category-ADDED'));
    expect(estimatesApi.patchEstimateLine).not.toHaveBeenCalled();
    expect(estimatesApi.regenerateEstimate).not.toHaveBeenCalled();
  });

  it('opening preview does not itself trigger another authoritative Estimate refetch', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(makePreview());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-no-changes'));
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);
  });
});

describe('Stage 10G.3B — zero-change state', () => {
  it('shows the "Kosztorys jest aktualny" message and no confirm action when there are no changes', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(makePreview());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-no-changes'));
    const text = screen.getByLabelText('estimate-regeneration-no-changes').textContent ?? '';
    expect(text).toContain('Kosztorys jest aktualny.');
    expect(text).toContain('Brak zmian w zaplanowanych pracach.');
    expect(screen.queryByLabelText('estimate-regeneration-confirm')).toBeNull();
  });
});

describe('Stage 10G.3B — change category rendering', () => {
  it('renders an ADDED entry under Dodano with resolved description and new quantity/price', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        added: 1,
        changes: [makeChange({
          change_type: 'ADDED',
          description: 'pricebook.seed.skim_2l',
          new_source_quantity: '12.400',
          new_unit_price: '35.00',
        })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-category-ADDED'));

    expect(screen.getByLabelText('estimate-regeneration-category-ADDED').textContent).toContain('Dodano');
    expect(screen.getByLabelText('estimate-regeneration-change-description-ADDED-0').textContent).toBe(
      'Gładź szpachlowa — 2 warstwy (pakiet)',
    );
    expect(screen.getByLabelText('estimate-regeneration-change-quantity-ADDED-0').textContent).toContain('12.400 m²');
    expect(screen.getByLabelText('estimate-regeneration-change-price-ADDED-0').textContent).toContain('35.00 PLN');
  });

  it('renders a REMOVED entry under Usunięto using the old quantity/price', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        removed: 1,
        changes: [makeChange({
          change_type: 'REMOVED',
          old_source_quantity: '8.000',
          new_source_quantity: null,
          old_unit_price: '30.00',
          new_unit_price: null,
        })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-category-REMOVED'));

    expect(screen.getByLabelText('estimate-regeneration-category-REMOVED').textContent).toContain('Usunięto');
    expect(screen.getByLabelText('estimate-regeneration-change-quantity-REMOVED-0').textContent).toContain('8.000 m²');
    expect(screen.getByLabelText('estimate-regeneration-change-price-REMOVED-0').textContent).toContain('30.00 PLN');
  });

  it('renders an UPDATED entry under Zmieniono, showing old -> new only for the field that actually changed', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        updated: 1,
        changes: [makeChange({
          change_type: 'UPDATED',
          old_source_quantity: '10.000',
          new_source_quantity: '12.400',
          old_unit_price: '35.00',
          new_unit_price: '35.00',
        })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-category-UPDATED'));

    expect(screen.getByLabelText('estimate-regeneration-category-UPDATED').textContent).toContain('Zmieniono');
    const qty = screen.getByLabelText('estimate-regeneration-change-quantity-UPDATED-0').textContent ?? '';
    expect(qty).toContain('10.000 m²');
    expect(qty).toContain('12.400 m²');
    expect(qty).toContain('→');
    // price unchanged -> collapsed to a single value, never "35.00 PLN → 35.00 PLN"
    expect(screen.getByLabelText('estimate-regeneration-change-price-UPDATED-0').textContent).toBe('35.00 PLN');
  });
});

describe('Stage 10G.3B — human-readable description, no raw UUIDs or item codes', () => {
  it('resolves a seeded pricebook key instead of the raw key', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange({ description: 'pricebook.seed.prim_adh' })] }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-change-description-ADDED-0'));
    expect(screen.getByLabelText('estimate-regeneration-change-description-ADDED-0').textContent).toBe(
      'Gruntowanie gruntem kontaktowym adhezyjnym',
    );
  });

  it('never renders raw surface_id / opening_id / planned_work_id / estimate_line_id UUIDs', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        updated: 1,
        changes: [makeChange({
          change_type: 'UPDATED',
          estimate_line_id: 'line-uuid-zzz',
          planned_work_id: 'pw-uuid-zzz',
          surface_id: 'surf-uuid-zzz',
          opening_id: 'open-uuid-zzz',
        })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    const panel = await waitFor(() => screen.getByLabelText('estimate-regeneration-panel'));
    const text = panel.textContent ?? '';
    expect(text).not.toContain('line-uuid-zzz');
    expect(text).not.toContain('pw-uuid-zzz');
    expect(text).not.toContain('surf-uuid-zzz');
    expect(text).not.toContain('open-uuid-zzz');
  });

  it('never renders the raw item_code', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange({ item_code: 'CENNIK_PRIM_ADH-01' })] }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    const panel = await waitFor(() => screen.getByLabelText('estimate-regeneration-panel'));
    expect(panel.textContent).not.toContain('CENNIK_PRIM_ADH-01');
  });
});

describe('Stage 10G.3B follow-up — compact provenance in preview change entries', () => {
  it('renders "room — surface" for a surface (non-reveal) ADDED entry', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        added: 1,
        changes: [makeChange({
          change_type: 'ADDED',
          room_name: 'kuchnia',
          surface_name: 'Wall 1',
          surface_type_value: 'WALL',
          opening_id: null,
        })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-change-provenance-ADDED-0'));
    expect(screen.getByLabelText('estimate-regeneration-change-provenance-ADDED-0').textContent).toBe(
      'kuchnia — Ściana 1',
    );
  });

  it('renders "room — surface — opening" for a reveal UPDATED entry with all parts present', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        updated: 1,
        changes: [makeChange({
          change_type: 'UPDATED',
          room_name: 'Łazienka',
          surface_name: 'Wall 2',
          surface_type_value: 'WALL',
          opening_id: 'opening-uuid',
          opening_name: 'Okno',
          opening_type_value: 'WINDOW',
        })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-change-provenance-UPDATED-0'));
    expect(screen.getByLabelText('estimate-regeneration-change-provenance-UPDATED-0').textContent).toBe(
      'Łazienka — Ściana 2 — Okno',
    );
  });

  it('shows RU compact provenance for a reveal entry', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        added: 1,
        changes: [makeChange({
          change_type: 'ADDED',
          room_name: 'Кухня',
          surface_name: 'Wall 1',
          surface_type_value: 'WALL',
          opening_id: 'opening-uuid',
          opening_name: null,
          opening_type_value: 'WINDOW',
        })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-change-provenance-ADDED-0'));
    const text = screen.getByLabelText('estimate-regeneration-change-provenance-ADDED-0').textContent ?? '';
    expect(text).toContain('Кухня');
    expect(text).toContain('—');
  });

  it('omits the provenance line entirely when no provenance fields are available (never fabricates one)', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        added: 1,
        changes: [makeChange({
          change_type: 'ADDED',
          room_name: null,
          surface_name: null,
          surface_type_value: null,
          opening_id: null,
        })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-category-ADDED'));
    expect(screen.queryByLabelText('estimate-regeneration-change-provenance-ADDED-0')).toBeNull();
  });

  it('falls back to localized surface type when surface_name is empty, and to room only when surface is unavailable', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        added: 1,
        changes: [makeChange({
          change_type: 'ADDED',
          room_name: 'kuchnia',
          surface_name: null,
          surface_type_value: 'FLOOR',
          opening_id: null,
        })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-change-provenance-ADDED-0'));
    expect(screen.getByLabelText('estimate-regeneration-change-provenance-ADDED-0').textContent).toBe(
      `kuchnia — ${'Podłoga'}`,
    );
  });

  it('tolerates omitted (undefined) provenance fields without crashing (10G.2 crash-regression protection)', async () => {
    const bareChange = makeChange({ change_type: 'ADDED' });
    // Simulate a response-construction path that omits the keys entirely
    // rather than sending explicit null, exactly like the fixed 10G.2 crash.
    delete (bareChange as Partial<LineChangeEntry>).room_name;
    delete (bareChange as Partial<LineChangeEntry>).surface_name;
    delete (bareChange as Partial<LineChangeEntry>).surface_type_value;
    delete (bareChange as Partial<LineChangeEntry>).opening_name;
    delete (bareChange as Partial<LineChangeEntry>).opening_type_value;
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [bareChange] }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await expect(
      waitFor(() => screen.getByLabelText('estimate-regeneration-category-ADDED')),
    ).resolves.toBeTruthy();
    expect(screen.queryByLabelText('estimate-regeneration-change-provenance-ADDED-0')).toBeNull();
  });

  it('a long provenance string wraps instead of forcing horizontal overflow', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        added: 1,
        changes: [makeChange({
          change_type: 'ADDED',
          room_name: 'Bardzo długa nazwa pomieszczenia opisująca cały zakres remontu',
          surface_name: 'Wall 1',
          surface_type_value: 'WALL',
        })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-change-provenance-ADDED-0'));
    const el = screen.getByLabelText('estimate-regeneration-change-provenance-ADDED-0');
    expect(el.className).toContain('break-words');
    expect(el.className).toContain('min-w-0');
  });
});

describe('Stage 10G.3B — NULL vs 0.00 price preserved in preview', () => {
  it('shows "Do ustalenia" for a NULL new_unit_price on an ADDED entry', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange({ new_unit_price: null })] }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-change-price-ADDED-0'));
    expect(screen.getByLabelText('estimate-regeneration-change-price-ADDED-0').textContent).toBe('Do ustalenia');
  });

  it('shows "0.00 PLN" (never "Do ustalenia") for an explicit 0.00 new_unit_price', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange({ new_unit_price: '0.00' })] }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-change-price-ADDED-0'));
    const text = screen.getByLabelText('estimate-regeneration-change-price-ADDED-0').textContent ?? '';
    expect(text).toContain('0.00');
    expect(text).not.toBe('Do ustalenia');
  });
});

describe('Stage 10G.3B — override indicators in preview', () => {
  it('shows both override indicators when an UPDATED line has quantity_overridden and price_override', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        updated: 1,
        changes: [makeChange({ change_type: 'UPDATED', quantity_overridden: true, price_override: true })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-change-override-UPDATED-0'));
    const text = screen.getByLabelText('estimate-regeneration-change-override-UPDATED-0').textContent ?? '';
    expect(text).toContain('Ilość zmieniona ręcznie');
    expect(text).toContain('Cena zmieniona ręcznie');
  });

  it('shows no override indicator when neither flag is set', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-category-ADDED'));
    expect(screen.queryByLabelText('estimate-regeneration-change-override-ADDED-0')).toBeNull();
  });
});

describe('Stage 10G.3B — explicit confirmation gating', () => {
  it('opening and viewing a non-empty preview never calls regenerateEstimate on its own', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm'));
    expect(estimatesApi.regenerateEstimate).not.toHaveBeenCalled();
  });

  it('explicit "Aktualizuj kosztorys" calls regenerateEstimate with the correct ids', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    vi.mocked(estimatesApi.regenerateEstimate).mockResolvedValue(makePreview({ added: 1 }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-confirm'));
    await waitFor(() => {
      expect(estimatesApi.regenerateEstimate).toHaveBeenCalledWith(PROJECT_ID, ESTIMATE_ID);
    });
  });

  it('"Anuluj" closes the preview without calling regenerateEstimate', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-cancel'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-cancel'));
    expect(estimatesApi.regenerateEstimate).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('estimate-regeneration-panel')).toBeNull();
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();
  });
});

describe('Stage 10G.3B — regeneration success', () => {
  it('refetches the authoritative Estimate after a successful regeneration', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    vi.mocked(estimatesApi.regenerateEstimate).mockResolvedValue(makePreview({ added: 1 }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-confirm'));

    await waitFor(() => expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(2));
  });

  it('the header total reflects the newly-fetched authoritative total after a successful regeneration, replacing the pre-regeneration total (owner-reported real bug)', async () => {
    const summary = makeSummary({ total: '1731.92', currency: 'PLN' });
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([makeLine()], summary))
      .mockResolvedValueOnce(makeDetail([makeLine()], { ...summary, total: '3819.80' }));
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    vi.mocked(estimatesApi.regenerateEstimate).mockResolvedValue(makePreview({ added: 1 }));

    renderShell(summary, null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('1731.92 PLN');

    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-confirm'));

    await waitFor(() => {
      expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('3819.80 PLN');
    });
  });

  it('closes the preview panel after a successful regeneration', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    vi.mocked(estimatesApi.regenerateEstimate).mockResolvedValue(makePreview({ added: 1 }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-confirm'));

    await waitFor(() => expect(screen.queryByLabelText('estimate-regeneration-panel')).toBeNull());
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();
  });
});

describe('Stage 10G.3B — regeneration and preview failure safety', () => {
  it('keeps the preview context recoverable and shows an inline error on regenerate failure', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    vi.mocked(estimatesApi.regenerateEstimate).mockRejectedValue(new Error('Estimate is not a DRAFT'));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-confirm'));

    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm-error'));
    expect(screen.getByLabelText('estimate-regeneration-confirm-error').textContent).toBe('Estimate is not a DRAFT');
    expect(screen.getByLabelText('estimate-regeneration-category-ADDED')).toBeTruthy();
    expect(screen.getByLabelText('estimate-regeneration-confirm')).toBeTruthy();
    expect(screen.getByLabelText('estimate-lines')).toBeTruthy();
  });

  it('allows retrying confirmation after a regenerate failure', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange()] }),
    );
    vi.mocked(estimatesApi.regenerateEstimate)
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(makePreview({ added: 1 }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-confirm'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm-error'));

    fireEvent.click(screen.getByLabelText('estimate-regeneration-confirm'));
    await waitFor(() => expect(screen.queryByLabelText('estimate-regeneration-panel')).toBeNull());
    expect(estimatesApi.regenerateEstimate).toHaveBeenCalledTimes(2);
  });

  it('a preview fetch failure shows an inline error with retry and close, without blanking the page', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockRejectedValue(new Error('Network error'));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-error'));
    expect(screen.getByLabelText('estimate-regeneration-error').textContent).toBe('Network error');
    expect(screen.getByLabelText('estimate-regeneration-retry')).toBeTruthy();
    expect(screen.getByLabelText('estimate-regeneration-close')).toBeTruthy();
    expect(screen.getByLabelText('estimate-lines')).toBeTruthy();
  });

  it('retry after a preview failure calls previewEstimateRegeneration again', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration)
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(makePreview());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-error'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-retry'));

    await waitFor(() => screen.getByLabelText('estimate-regeneration-no-changes'));
    expect(estimatesApi.previewEstimateRegeneration).toHaveBeenCalledTimes(2);
  });

  it('closing after a preview failure returns to the plain Sprawdź zmiany action', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockRejectedValue(new Error('boom'));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-error'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-close'));
    expect(screen.queryByLabelText('estimate-regeneration-panel')).toBeNull();
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();
  });
});

describe('Stage 10G.3B — multi-room acceptance scenario', () => {
  it('preview reports a new room as ADDED while the Estimate stays unchanged, then confirmed regeneration merges both rooms into one aggregated group with distinguishable drill-down provenance', async () => {
    const roomALine = makeLine({
      id: 'la1',
      position: 1,
      price_item_id: 'pi-skim',
      scope: 'LABOR',
      unit: 'M2',
      opening_id: null,
      description: 'pricebook.seed.skim_2l',
      room_name: 'pokój 1',
      surface_name: 'Wall 1',
      surface_type_value: 'WALL',
      surface_id: 'surf-a1',
      quantity: '10.000',
      unit_price: '35.00',
      amount: '350.00',
    });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValueOnce(makeDetail([roomALine]));

    render(
      <I18nProvider>
        <StatefulGroupedShell />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));

    // Before regeneration: exactly one group, Room A quantity only.
    expect(screen.getAllByLabelText(/^estimate-group-/).length).toBe(1);
    expect(screen.getByLabelText('group-quantity-0').textContent).toContain('10.000');

    // The owner checks for changes — the new Kuchnia planned work reports as ADDED.
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        added: 1,
        changes: [makeChange({
          change_type: 'ADDED',
          description: 'pricebook.seed.skim_2l',
          surface_id: 'surf-b1',
          new_source_quantity: '6.000',
          new_unit_price: '35.00',
          room_name: 'kuchnia',
          surface_name: 'Wall 1',
          surface_type_value: 'WALL',
        })],
      }),
    );
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-category-ADDED'));

    // Preview visibly shows WHERE the new work comes from.
    expect(screen.getByLabelText('estimate-regeneration-change-provenance-ADDED-0').textContent).toBe(
      'kuchnia — Ściana 1',
    );

    // Still unchanged before confirmation.
    expect(screen.getByLabelText('group-quantity-0').textContent).toContain('10.000');

    const roomBLine = makeLine({
      id: 'lb1',
      position: 2,
      price_item_id: 'pi-skim',
      scope: 'LABOR',
      unit: 'M2',
      opening_id: null,
      description: 'pricebook.seed.skim_2l',
      room_name: 'kuchnia',
      surface_name: 'Wall 1',
      surface_type_value: 'WALL',
      surface_id: 'surf-b1',
      quantity: '6.000',
      unit_price: '35.00',
      amount: '210.00',
    });
    vi.mocked(estimatesApi.regenerateEstimate).mockResolvedValue(makePreview({ added: 1 }));
    vi.mocked(estimatesApi.getEstimate).mockResolvedValueOnce(makeDetail([roomALine, roomBLine]));

    fireEvent.click(screen.getByLabelText('estimate-regeneration-confirm'));
    await waitFor(() => expect(screen.queryByLabelText('estimate-regeneration-panel')).toBeNull());

    // Grouped summary aggregates matching work across BOTH rooms into one group.
    await waitFor(() => expect(screen.getAllByLabelText(/^estimate-group-/).length).toBe(1));
    expect(screen.getByLabelText('group-quantity-0').textContent).toContain('16.000');
    expect(screen.getByLabelText('group-line-count-0').textContent).toContain('2');

    // Drill-down still distinguishes each room's provenance.
    fireEvent.click(screen.getByLabelText('estimate-group-0'));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-provenance-1').textContent).toBe('pokój 1 — Ściana 1');
    expect(screen.getByLabelText('line-provenance-2').textContent).toBe('kuchnia — Ściana 1');
  });
});

describe('Stage 10G.3B regression — accepted 10G.2/10G.3A behavior untouched', () => {
  it('group price editing still works alongside the new Sprawdź zmiany action', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00' }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: '40.00', price_override: true }),
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();

    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '40.00' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));

    await waitFor(() => expect(estimatesApi.patchEstimateLine).toHaveBeenCalledTimes(2));
  });

  it('atomic line editing still works alongside the new Sprawdź zmiany action', async () => {
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ quantity: '13.750', quantity_overridden: true }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-quantity-1'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '13.750' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { quantity: '13.750' },
      );
    });
  });

  it('compact provenance and deterministic surface tint are preserved in the detail view', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-provenance-1').textContent).toBe('Salon — Ściana 1');
    expect(screen.getByLabelText('estimate-line-1').className).toMatch(/bg-\S+-50/);
  });

  it('Back navigation between grouped and detail views is preserved', async () => {
    renderShell(makeSummary(), PLANNED_SURFACE_KEY);
    await waitFor(() => screen.getByLabelText('estimate-detail-back'));
    expect(screen.getByLabelText('estimate-detail-back')).toBeTruthy();
  });

  it('the previously fixed undefined-provenance crash regression remains fixed', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([
      makeLine({ surface_name: undefined, surface_type_value: 'WALL' }),
    ]));
    renderShell();
    await expect(waitFor(() => screen.getByLabelText('estimate-lines'))).resolves.toBeTruthy();
  });

  it('no JS Number financial arithmetic is introduced by the preview panel', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        added: 1,
        changes: [makeChange({ new_source_quantity: '319.410', new_unit_price: '312.34' })],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-change-quantity-ADDED-0'));
    // Exact decimal strings pass through unrounded — 319.410, not 319.41 or 319.4100000001.
    expect(screen.getByLabelText('estimate-regeneration-change-quantity-ADDED-0').textContent).toContain('319.410');
    expect(screen.getByLabelText('estimate-regeneration-change-price-ADDED-0').textContent).toContain('312.34');
  });
});

// ─── Stage 10G.3C — manual estimate lines ─────────────────────────────────────

function makeManualLine(overrides: Partial<EstimateLineRead> = {}): EstimateLineRead {
  return makeLine({
    origin: 'MANUAL',
    price_item_id: null,
    plan_id: null,
    planned_work_id: null,
    surface_id: null,
    room_id: null,
    opening_id: null,
    room_name: null,
    surface_name: null,
    surface_type_value: null,
    opening_name: null,
    opening_type_value: null,
    quantity_source: 'MANUAL',
    price_override: true,
    ...overrides,
  });
}

describe('Stage 10G.3C — add-manual-line entry (DRAFT-only, whole-estimate)', () => {
  it('a DRAFT estimate shows + Dodaj pozycję in the detail view', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-add-manual-line-action')).toBeTruthy();
  });

  it('a DRAFT estimate shows + Dodaj pozycję in the grouped summary view', async () => {
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-add-manual-line-action')).toBeTruthy();
  });

  it('does not expose + Dodaj pozycję for a FINAL estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'FINAL' }));
    renderShell(makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('estimate-add-manual-line-action')).toBeNull();
  });

  it('does not expose + Dodaj pozycję for an ACCEPTED estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'ACCEPTED' }));
    renderShell(makeSummary({ status: 'ACCEPTED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('estimate-add-manual-line-action')).toBeNull();
  });

  it('does not expose + Dodaj pozycję for an ARCHIVED estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'ARCHIVED' }));
    renderShell(makeSummary({ status: 'ARCHIVED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('estimate-add-manual-line-action')).toBeNull();
  });
});

describe('Stage 10G.3C — manual line form', () => {
  it('opens and closes without calling the API', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    await waitFor(() => screen.getByLabelText('estimate-manual-line-form'));
    fireEvent.click(screen.getByLabelText('estimate-manual-line-cancel'));
    expect(screen.queryByLabelText('estimate-manual-line-form')).toBeNull();
    expect(screen.getByLabelText('estimate-add-manual-line-action')).toBeTruthy();
    expect(estimatesApi.addManualEstimateLine).not.toHaveBeenCalled();
  });

  it('offers only LABOR and MATERIAL scopes, never LABOR_AND_MATERIAL (backend rejects it for manual lines)', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    const select = (await waitFor(() => screen.getByLabelText('manual-line-scope'))) as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(['LABOR', 'MATERIAL']);
  });

  it('offers all six backend PriceUnit values in the unit selector', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    const select = (await waitFor(() => screen.getByLabelText('manual-line-unit'))) as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(['M2', 'LM', 'PCS', 'HOUR', 'DAY', 'FLAT']);
  });

  it('defaults to the unresolved-price state hidden and quantity "1"', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    await waitFor(() => screen.getByLabelText('manual-line-quantity'));
    expect((screen.getByLabelText('manual-line-quantity') as HTMLInputElement).value).toBe('1');
    expect((screen.getByLabelText('manual-line-price-unresolved') as HTMLInputElement).checked).toBe(false);
  });

  it('checking "Cena do ustalenia" hides the numeric price input', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    const toggle = await waitFor(() => screen.getByLabelText('manual-line-price-unresolved'));
    fireEvent.click(toggle);
    expect(screen.queryByLabelText('manual-line-price')).toBeNull();
  });

  it('rejects an empty description locally, without any network call', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));
    await waitFor(() => screen.getByLabelText('estimate-manual-line-error'));
    expect(screen.getByLabelText('estimate-manual-line-error').textContent).toBe('Podaj opis pozycji.');
    expect(estimatesApi.addManualEstimateLine).not.toHaveBeenCalled();
  });

  it('rejects a non-numeric quantity locally, without any network call', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Transport' } });
    fireEvent.change(screen.getByLabelText('manual-line-quantity'), { target: { value: 'abc' } });
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));
    await waitFor(() => screen.getByLabelText('estimate-manual-line-error'));
    expect(estimatesApi.addManualEstimateLine).not.toHaveBeenCalled();
  });

  it('rejects a non-numeric explicit price locally, without any network call', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Transport' } });
    fireEvent.change(screen.getByLabelText('manual-line-price'), { target: { value: 'xyz' } });
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));
    await waitFor(() => screen.getByLabelText('estimate-manual-line-error'));
    expect(estimatesApi.addManualEstimateLine).not.toHaveBeenCalled();
  });
});

describe('Stage 10G.3C — manual line create payload and currency', () => {
  it('sends the exact typed decimal quantity and numeric price, scope, unit, and the estimate currency', async () => {
    vi.mocked(estimatesApi.addManualEstimateLine).mockResolvedValue(makeManualLine());
    renderShell(makeSummary({ currency: 'PLN' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Transport materiałów' } });
    fireEvent.change(screen.getByLabelText('manual-line-scope'), { target: { value: 'MATERIAL' } });
    fireEvent.change(screen.getByLabelText('manual-line-unit'), { target: { value: 'FLAT' } });
    fireEvent.change(screen.getByLabelText('manual-line-quantity'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('manual-line-price'), { target: { value: '250.00' } });
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));

    await waitFor(() => {
      expect(estimatesApi.addManualEstimateLine).toHaveBeenCalledWith(PROJECT_ID, ESTIMATE_ID, {
        description: 'Transport materiałów',
        scope: 'MATERIAL',
        unit: 'FLAT',
        quantity: '1',
        unit_price: '250.00',
        currency: 'PLN',
      });
    });
  });

  it('sends a raw decimal quantity string unchanged (no Number/parseFloat rounding)', async () => {
    vi.mocked(estimatesApi.addManualEstimateLine).mockResolvedValue(makeManualLine());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Naprawa' } });
    fireEvent.change(screen.getByLabelText('manual-line-quantity'), { target: { value: '12.750' } });
    fireEvent.click(screen.getByLabelText('manual-line-price-unresolved'));
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));

    await waitFor(() => {
      const call = vi.mocked(estimatesApi.addManualEstimateLine).mock.calls[0];
      expect(call[2].quantity).toBe('12.750');
    });
  });

  it('sends explicit unit_price: null when "Cena do ustalenia" is checked', async () => {
    vi.mocked(estimatesApi.addManualEstimateLine).mockResolvedValue(makeManualLine({ unit_price: null, amount: null }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Dodatkowa naprawa' } });
    fireEvent.click(screen.getByLabelText('manual-line-price-unresolved'));
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));

    await waitFor(() => {
      const call = vi.mocked(estimatesApi.addManualEstimateLine).mock.calls[0];
      expect(call[2].unit_price).toBeNull();
    });
  });

  it('sends "0.00" as an explicit string price, never as null', async () => {
    vi.mocked(estimatesApi.addManualEstimateLine).mockResolvedValue(
      makeManualLine({ unit_price: '0.00', amount: '0.00' }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Gratis' } });
    fireEvent.change(screen.getByLabelText('manual-line-price'), { target: { value: '0.00' } });
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));

    await waitFor(() => {
      const call = vi.mocked(estimatesApi.addManualEstimateLine).mock.calls[0];
      expect(call[2].unit_price).toBe('0.00');
    });
  });

  it('never renders an editable currency control (currency always comes from the authoritative estimate)', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    await waitFor(() => screen.getByLabelText('estimate-manual-line-form'));
    expect(screen.queryByLabelText(/currency/i)).toBeNull();
  });
});

describe('Stage 10G.3C — manual line create success and failure', () => {
  it('refetches the authoritative Estimate after a successful create', async () => {
    vi.mocked(estimatesApi.addManualEstimateLine).mockResolvedValue(makeManualLine());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Transport' } });
    fireEvent.click(screen.getByLabelText('manual-line-price-unresolved'));
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));

    await waitFor(() => expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(2));
  });

  it('closes and resets the form after a successful create', async () => {
    vi.mocked(estimatesApi.addManualEstimateLine).mockResolvedValue(makeManualLine());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Transport' } });
    fireEvent.click(screen.getByLabelText('manual-line-price-unresolved'));
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));

    await waitFor(() => expect(screen.queryByLabelText('estimate-manual-line-form')).toBeNull());
    expect(screen.getByLabelText('estimate-add-manual-line-action')).toBeTruthy();
  });

  it('the header total reflects the authoritative refetched total after a successful create (no frontend arithmetic)', async () => {
    const summary = makeSummary({ total: '1731.92', currency: 'PLN' });
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([makeLine()], summary))
      .mockResolvedValueOnce(makeDetail([makeLine(), makeManualLine({ id: 'm1', position: 2 })], { ...summary, total: '1981.92' }));
    vi.mocked(estimatesApi.addManualEstimateLine).mockResolvedValue(makeManualLine({ id: 'm1', position: 2 }));

    renderShell(summary, null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('1731.92 PLN');

    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Transport' } });
    fireEvent.change(screen.getByLabelText('manual-line-price'), { target: { value: '250.00' } });
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));

    await waitFor(() => {
      expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('1981.92 PLN');
    });
  });

  it('a create failure keeps the form open with typed values preserved and shows an inline error', async () => {
    vi.mocked(estimatesApi.addManualEstimateLine).mockRejectedValue(new Error('Manual line currency does not match'));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Transport' } });
    fireEvent.click(screen.getByLabelText('manual-line-price-unresolved'));
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));

    await waitFor(() => screen.getByLabelText('estimate-manual-line-error'));
    expect(screen.getByLabelText('estimate-manual-line-error').textContent).toBe('Manual line currency does not match');
    expect(screen.getByLabelText('estimate-manual-line-form')).toBeTruthy();
    expect((screen.getByLabelText('manual-line-description') as HTMLTextAreaElement).value).toBe('Transport');
  });

  it('a 422 error does not blank the Estimate and does not claim success', async () => {
    vi.mocked(estimatesApi.addManualEstimateLine).mockRejectedValue(
      new (class extends Error {})('Lines can only be added to DRAFT estimates'),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Transport' } });
    fireEvent.click(screen.getByLabelText('manual-line-price-unresolved'));
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));

    await waitFor(() => screen.getByLabelText('estimate-manual-line-error'));
    expect(screen.getByLabelText('estimate-lines')).toBeTruthy();
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1); // no refetch on failure
  });
});

describe('Stage 10G.3C — MANUAL singleton grouping preserved', () => {
  it('two manual lines with identical description/scope/unit/price remain two separate groups', async () => {
    const lines = [
      makeManualLine({ id: 'm1', position: 1, description: 'Transport materiałów', unit_price: '250.00' }),
      makeManualLine({ id: 'm2', position: 2, description: 'Transport materiałów', unit_price: '250.00' }),
    ];
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail(lines));
    render(
      <I18nProvider>
        <EstimateShell estimate={makeSummary()} onBack={vi.fn()} selectedGroupKey={null} onGroupKeyChange={vi.fn()} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getAllByLabelText(/^estimate-group-/).length).toBe(2);
  });
});

describe('Stage 10G.3C — existing atomic edit compatibility for MANUAL lines', () => {
  it('a MANUAL line can still have its quantity edited via the existing atomic editor', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeManualLine()]));
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(makeManualLine({ quantity: '5.000', quantity_overridden: true }));
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(() => screen.getByLabelText('line-edit-quantity-1'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '5.000' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { quantity: '5.000' },
      );
    });
  });

  it('a MANUAL line never shows the reset-to-PriceBook price action (no PriceBook source)', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeManualLine({ price_override: true })]));
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-reset-price-1')).toBeNull();
  });
});

describe('Stage 10G.3C — delete manual line', () => {
  it('shows Usuń pozycję only for a MANUAL line, never for a PLANNED_WORK line', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeManualLine()]));
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-delete-action-1')).toBeTruthy();
  });

  it('does not show a delete action for a PLANNED_WORK line', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('line-delete-action-1')).toBeNull();
  });

  it('requires explicit confirmation before deleting', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeManualLine()]));
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('line-delete-action-1'));
    await waitFor(() => screen.getByLabelText('line-delete-confirm-1'));
    expect(screen.getByLabelText('line-delete-confirm-1').textContent).toContain(
      'Usunąć tę pozycję ze szkicu kosztorysu?',
    );
    expect(estimatesApi.deleteEstimateLine).not.toHaveBeenCalled();
  });

  it('Anuluj cancels without deleting', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeManualLine()]));
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('line-delete-action-1'));
    await waitFor(() => screen.getByLabelText('line-delete-cancel-1'));
    fireEvent.click(screen.getByLabelText('line-delete-cancel-1'));
    expect(screen.queryByLabelText('line-delete-confirm-1')).toBeNull();
    expect(estimatesApi.deleteEstimateLine).not.toHaveBeenCalled();
  });

  it('confirming calls the existing DELETE endpoint with the correct ids', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeManualLine()]));
    vi.mocked(estimatesApi.deleteEstimateLine).mockResolvedValue(undefined);
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('line-delete-action-1'));
    await waitFor(() => screen.getByLabelText('line-delete-confirm-yes-1'));
    fireEvent.click(screen.getByLabelText('line-delete-confirm-yes-1'));

    await waitFor(() => {
      expect(estimatesApi.deleteEstimateLine).toHaveBeenCalledWith(PROJECT_ID, ESTIMATE_ID, 'line-1');
    });
  });

  it('a successful delete refetches the authoritative Estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeManualLine()]));
    vi.mocked(estimatesApi.deleteEstimateLine).mockResolvedValue(undefined);
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText('line-delete-action-1'));
    await waitFor(() => screen.getByLabelText('line-delete-confirm-yes-1'));
    fireEvent.click(screen.getByLabelText('line-delete-confirm-yes-1'));

    await waitFor(() => expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(2));
  });

  it('a delete failure keeps the confirmation recoverable and shows an inline error, without optimistic removal', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeManualLine()]));
    vi.mocked(estimatesApi.deleteEstimateLine).mockRejectedValue(new Error('Only MANUAL lines can be deleted'));
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('line-delete-action-1'));
    await waitFor(() => screen.getByLabelText('line-delete-confirm-yes-1'));
    fireEvent.click(screen.getByLabelText('line-delete-confirm-yes-1'));

    await waitFor(() => screen.getByLabelText('line-delete-error-1'));
    expect(screen.getByLabelText('line-delete-error-1').textContent).toBe('Only MANUAL lines can be deleted');
    expect(screen.getByLabelText('estimate-line-1')).toBeTruthy(); // never optimistically removed
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);
  });
});

describe('Stage 10G.3C — manual line survives regeneration', () => {
  it('a manual line remains present and unchanged across a regeneration refetch, alongside updated planned work', async () => {
    const manual = makeManualLine({ id: 'm1', position: 2, description: 'Transport materiałów', unit_price: '250.00', amount: '250.00' });
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([makeLine(), manual]))
      .mockResolvedValueOnce(makeDetail([makeLine({ quantity: '20.000', quantity_overridden: false, amount: '700.00' }), manual]));
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ updated: 1, preserved_manual: 1, changes: [makeChange({ change_type: 'UPDATED' })] }),
    );
    vi.mocked(estimatesApi.regenerateEstimate).mockResolvedValue(makePreview({ updated: 1, preserved_manual: 1 }));

    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    // Two groups: the planned work and the singleton manual line.
    expect(screen.getAllByLabelText(/^estimate-group-/).length).toBe(2);

    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-confirm'));
    fireEvent.click(screen.getByLabelText('estimate-regeneration-confirm'));

    await waitFor(() => expect(screen.queryByLabelText('estimate-regeneration-panel')).toBeNull());
    // Manual line's own group is still present after regeneration.
    await waitFor(() => expect(screen.getAllByLabelText(/^estimate-group-/).length).toBe(2));
  });
});

describe('Stage 10G.3C — NULL vs 0.00 for manual lines', () => {
  it('a manual line with NULL price shows quantity normally and "Do ustalenia" for price, "—" for amount', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeManualLine({ quantity: '3.500', unit_price: null, amount: null })]),
    );
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-quantity-1').textContent).toContain('3.500');
    expect(screen.getByLabelText('line-unit-price-1').textContent).toBe('Do ustalenia');
    expect(screen.getByLabelText('line-amount-1').textContent).toBe('—');
  });

  it('a manual line with explicit 0.00 price shows 0.00, never "Do ustalenia"', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeManualLine({ quantity: '1.000', unit_price: '0.00', amount: '0.00' })]),
    );
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-unit-price-1').textContent).toContain('0.00');
    expect(screen.getByLabelText('line-unit-price-1').textContent).not.toBe('Do ustalenia');
    expect(screen.getByLabelText('line-amount-1').textContent).toContain('0.00');
  });
});

describe('Stage 10G.3C — mobile touch targets', () => {
  it('add-manual-line, form controls, and delete controls all meet the 44px minimum', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeManualLine()]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-add-manual-line-action').className).toContain('min-h-[44px]');

    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    await waitFor(() => screen.getByLabelText('estimate-manual-line-save'));
    expect(screen.getByLabelText('estimate-manual-line-save').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('estimate-manual-line-cancel').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('manual-line-quantity').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('manual-line-scope').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('manual-line-unit').className).toContain('min-h-[44px]');
  });

  it('delete action and confirm buttons meet the 44px minimum', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeManualLine()]));
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-delete-action-1').className).toContain('min-h-[44px]');
    fireEvent.click(screen.getByLabelText('line-delete-action-1'));
    await waitFor(() => screen.getByLabelText('line-delete-confirm-yes-1'));
    expect(screen.getByLabelText('line-delete-confirm-yes-1').className).toContain('min-h-[44px]');
    expect(screen.getByLabelText('line-delete-cancel-1').className).toContain('min-h-[44px]');
  });
});

describe('Stage 10G.3C regression — accepted 10G.2/10G.3A/10G.3B behavior untouched', () => {
  it('regeneration preview still works alongside the new manual-line entry', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(makePreview());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-no-changes'));
  });

  it('group price editing still works alongside the new manual-line entry', async () => {
    renderGroupedShell([
      makeLine({ id: 'l1', position: 1, unit_price: '35.00' }),
      makeLine({ id: 'l2', position: 2, unit_price: '35.00' }),
    ]);
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      makeLine({ unit_price: '40.00', price_override: true }),
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-add-manual-line-action')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('group-options-0'));
    fireEvent.click(screen.getByLabelText('group-price-edit-action-0'));
    const input = (await waitFor(() => screen.getByLabelText('group-price-edit-value-0'))) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '40.00' } });
    fireEvent.click(screen.getByLabelText('group-price-edit-save-0'));
    await waitFor(() => expect(estimatesApi.patchEstimateLine).toHaveBeenCalledTimes(2));
  });

  it('compact provenance and cross-room grouping remain unaffected by the new manual-line UI', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-provenance-1').textContent).toBe('Salon — Ściana 1');
  });

  it('no JS Number financial arithmetic is introduced by the manual-line form', async () => {
    vi.mocked(estimatesApi.addManualEstimateLine).mockResolvedValue(makeManualLine());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Test' } });
    fireEvent.change(screen.getByLabelText('manual-line-quantity'), { target: { value: '12.750' } });
    fireEvent.change(screen.getByLabelText('manual-line-price'), { target: { value: '312.34' } });
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));
    await waitFor(() => {
      const call = vi.mocked(estimatesApi.addManualEstimateLine).mock.calls[0];
      expect(call[2].quantity).toBe('12.750');
      expect(call[2].unit_price).toBe('312.34');
    });
  });
});

// ─── Stage 10G.3D — estimate finalization and version lifecycle ──────────────

describe('Stage 10G.3D — finalize entry (DRAFT-only, whole-estimate)', () => {
  it('a DRAFT estimate shows Finalizuj kosztorys', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-finalize-action')).toBeTruthy();
  });

  it('a DRAFT estimate shows Finalizuj kosztorys in the grouped summary view too', async () => {
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('estimate-finalize-action')).toBeTruthy();
  });

  it('does not expose Finalizuj kosztorys for a FINAL estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'FINAL' }));
    renderShell(makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('estimate-finalize-action')).toBeNull();
  });

  it('does not expose Finalizuj kosztorys for an ACCEPTED estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'ACCEPTED' }));
    renderShell(makeSummary({ status: 'ACCEPTED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('estimate-finalize-action')).toBeNull();
  });

  it('does not expose Finalizuj kosztorys for an ARCHIVED estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'ARCHIVED' }));
    renderShell(makeSummary({ status: 'ARCHIVED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.queryByLabelText('estimate-finalize-action')).toBeNull();
  });
});

describe('Stage 10G.3D — finalize confirmation gating', () => {
  it('requires explicit confirmation before calling finalize', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm'));
    expect(estimatesApi.finalizeEstimate).not.toHaveBeenCalled();
  });

  it('Anuluj cancels without calling finalize', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-cancel'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-cancel'));
    expect(screen.queryByLabelText('estimate-finalize-confirm')).toBeNull();
    expect(estimatesApi.finalizeEstimate).not.toHaveBeenCalled();
  });

  it('confirming calls finalizeEstimate with the correct project and estimate ids', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'FINAL' }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));
    await waitFor(() => {
      expect(estimatesApi.finalizeEstimate).toHaveBeenCalledWith(PROJECT_ID, ESTIMATE_ID);
    });
  });
});

describe('Stage 10G.3D — finalize failure (unresolved price)', () => {
  it('an unresolved-price failure keeps the Estimate in DRAFT, shows a localized (not raw English) error inline, and stays recoverable', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockRejectedValue(
      new Error('Cannot finalize: 1 line(s) have no price set (Do ustalenia). Set prices in the Price Book or add line overrides.'),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));
    const errorText = screen.getByLabelText('estimate-finalize-error').textContent ?? '';
    expect(errorText).not.toContain('Cannot finalize');
    expect(errorText).toBe(
      'Nie można sfinalizować kosztorysu. 1 pozycji nie ma ustalonej ceny. Uzupełnij ceny pozycji oznaczonych „Do ustalenia” i spróbuj ponownie.',
    );
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Szkic');
    expect(screen.getByLabelText('estimate-finalize-confirm')).toBeTruthy();
    expect(screen.getByLabelText('estimate-lines')).toBeTruthy();
  });

  it('retrying finalize after a failure remains possible', async () => {
    vi.mocked(estimatesApi.finalizeEstimate)
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(makeDetail([makeLine()], { status: 'FINAL' }));
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([makeLine()]))
      .mockResolvedValueOnce(makeDetail([makeLine({ unit_price: '35.00' })], { status: 'FINAL' }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));

    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));
    await waitFor(() => expect(estimatesApi.finalizeEstimate).toHaveBeenCalledTimes(2));
  });

  it('extracts the real backend count, not a hardcoded number (e.g. 4, not 6)', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockRejectedValue(
      new Error('Cannot finalize: 4 line(s) have no price set (Do ustalenia). Set prices in the Price Book or add line overrides.'),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));
    expect(screen.getByLabelText('estimate-finalize-error').textContent).toBe(
      'Nie można sfinalizować kosztorysu. 4 pozycji nie ma ustalonej ceny. Uzupełnij ceny pozycji oznaczonych „Do ustalenia” i spróbuj ponownie.',
    );
  });

  it('shows the RU localized unresolved-price message, not raw English, with the real count', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(estimatesApi.finalizeEstimate).mockRejectedValue(
      new Error('Cannot finalize: 6 line(s) have no price set (Do ustalenia). Set prices in the Price Book or add line overrides.'),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));
    const errorText = screen.getByLabelText('estimate-finalize-error').textContent ?? '';
    expect(errorText).not.toContain('Cannot finalize');
    expect(errorText).toBe(
      'Невозможно зафиксировать смету. У 6 позиций не указана цена. Заполните цены у позиций «Цена уточняется» и повторите попытку.',
    );
  });

  it('falls back to the generic finalize error for a malformed/unexpected error shape, without inventing a count', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockRejectedValue(
      new Error('Cannot finalize: something unexpected happened'),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));
    // Does not match the known "Cannot finalize: N line(s)..." shape, so the
    // raw (non-localized) message passes through the existing fallback path
    // unchanged rather than being misclassified as the unresolved-price case.
    expect(screen.getByLabelText('estimate-finalize-error').textContent).toBe(
      'Cannot finalize: something unexpected happened',
    );
  });

  it('does not misclassify an unrelated error (e.g. a 409-style conflict) as the unresolved-price case', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockRejectedValue(
      new Error('Only DRAFT estimates can be finalized; estimate is FINAL'),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));
    expect(screen.getByLabelText('estimate-finalize-error').textContent).toBe(
      'Only DRAFT estimates can be finalized; estimate is FINAL',
    );
  });

  it('a network/non-Error rejection uses the generic localized fallback', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockRejectedValue('network down');
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));
    expect(screen.getByLabelText('estimate-finalize-error').textContent).toBe(
      'Nie udało się sfinalizować kosztorysu.',
    );
  });
});

describe('Stage 10H.1 — unresolved MANUAL quantity display', () => {
  function unresolvedLine(overrides: Partial<EstimateLineRead> = {}): EstimateLineRead {
    return makeLine({
      unit: 'LM',
      quantity: '0.000',
      source_quantity: null,
      quantity_source: 'MANUAL',
      quantity_overridden: false,
      description: 'Naprawa rys i pęknięć (poszerzenie, wypełnienie)',
      ...overrides,
    });
  }

  it('shows "Ilość do ustalenia" instead of the generated 0.000 fallback', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([unresolvedLine()]));
    renderShell(makeSummary(), PLANNED_SURFACE_LM_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const text = screen.getByLabelText('line-quantity-1').textContent ?? '';
    expect(text).toContain('Ilość do ustalenia');
    expect(text).toContain('mb');
    expect(text).not.toContain('0.000');
  });

  it('the quantity edit action remains available for an unresolved line', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([unresolvedLine()]));
    renderShell(makeSummary(), PLANNED_SURFACE_LM_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-edit-action-1')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(
      () => screen.getByLabelText('line-edit-quantity-1'),
    )) as HTMLInputElement;
    // Prefilled with the stored 0.000, exactly like any other line — the
    // owner is expected to type over it, nothing new here.
    expect(input.value).toBe('0.000');
  });

  it('entering 4.5 and saving shows 4.500 mb, no longer unresolved, after the authoritative refetch', async () => {
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([unresolvedLine()]))
      .mockResolvedValueOnce(
        makeDetail([unresolvedLine({ quantity: '4.500', quantity_overridden: true })]),
      );
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(
      unresolvedLine({ quantity: '4.500', quantity_overridden: true }),
    );
    renderShell(makeSummary(), PLANNED_SURFACE_LM_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));

    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    const input = (await waitFor(
      () => screen.getByLabelText('line-edit-quantity-1'),
    )) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '4.5' } });
    fireEvent.click(screen.getByLabelText('line-edit-save-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { quantity: '4.5' },
      );
    });
    await waitFor(() => {
      const text = screen.getByLabelText('line-quantity-1').textContent ?? '';
      expect(text).toContain('4.500');
      expect(text).toContain('mb');
      expect(text).not.toContain('Ilość do ustalenia');
    });
  });

  it('an explicit owner-confirmed 0.000 (quantity_overridden=true) displays as 0.000 mb, never as unresolved', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([unresolvedLine({ quantity: '0.000', quantity_overridden: true })]),
    );
    renderShell(makeSummary(), PLANNED_SURFACE_LM_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const text = screen.getByLabelText('line-quantity-1').textContent ?? '';
    expect(text).toContain('0.000');
    expect(text).toContain('mb');
    expect(text).not.toContain('Ilość do ustalenia');
    // The distinct "manually changed" annotation still applies, as for any override.
    expect(screen.getByLabelText('line-qty-override-1')).toBeTruthy();
  });

  it('resetting an overridden quantity restores the unresolved display', async () => {
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(
        makeDetail([unresolvedLine({ quantity: '4.500', quantity_overridden: true })]),
      )
      .mockResolvedValueOnce(makeDetail([unresolvedLine()]));
    vi.mocked(estimatesApi.patchEstimateLine).mockResolvedValue(unresolvedLine());
    renderShell(makeSummary(), PLANNED_SURFACE_LM_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-quantity-1').textContent).toContain('4.500');

    fireEvent.click(screen.getByLabelText('line-reset-quantity-1'));

    await waitFor(() => {
      expect(estimatesApi.patchEstimateLine).toHaveBeenCalledWith(
        PROJECT_ID, ESTIMATE_ID, 'line-1', { reset_quantity_override: true },
      );
    });
    await waitFor(() => {
      const text = screen.getByLabelText('line-quantity-1').textContent ?? '';
      expect(text).toContain('Ilość do ustalenia');
      expect(text).not.toContain('4.500');
    });
  });

  it('an auto-derived Surface M2 quantity (e.g. 1.284 m²) displays normally, unaffected', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([
        makeLine({
          unit: 'M2',
          quantity: '1.284',
          source_quantity: '1.284',
          quantity_source: 'SURFACE_NET_AREA',
          quantity_overridden: false,
          description: 'Gruntowanie gruntem penetrującym',
        }),
      ]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const text = screen.getByLabelText('line-quantity-1').textContent ?? '';
    expect(text).toContain('1.284');
    expect(text).toContain('m²');
    expect(text).not.toContain('Ilość do ustalenia');
  });

  it('a freeform MANUAL-origin line is never shown as unresolved, even though it shares the same underlying fingerprint', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([
        makeLine({
          origin: 'MANUAL',
          unit: 'FLAT',
          quantity: '1.000',
          source_quantity: null,
          quantity_source: 'MANUAL',
          quantity_overridden: false,
          price_item_id: null,
          description: 'Transport materiałów',
        }),
      ]),
    );
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const text = screen.getByLabelText('line-quantity-1').textContent ?? '';
    expect(text).toContain('1.000');
    expect(text).not.toContain('Ilość do ustalenia');
  });
});

describe('Stage 10H.1 defect #4 — main estimate card/list quantity parity', () => {
  function unresolvedGroupLine(overrides: Partial<EstimateLineRead> = {}): EstimateLineRead {
    return makeLine({
      unit: 'LM',
      quantity: '0.000',
      source_quantity: null,
      quantity_source: 'MANUAL',
      quantity_overridden: false,
      description: 'Naprawa rys i pęknięć (poszerzenie, wypełnienie)',
      ...overrides,
    });
  }

  it('the main card/list view shows "Ilość do ustalenia" for an unresolved group, not 0.000 (the reported defect)', async () => {
    renderGroupedShell([unresolvedGroupLine()]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const text = screen.getByLabelText('group-quantity-0').textContent ?? '';
    expect(text).toContain('Ilość do ustalenia');
    expect(text).toContain('mb');
    expect(text).not.toContain('0.000');
  });

  it('an explicit owner-confirmed 0.000 in the main card/list view still shows 0.000, not unresolved', async () => {
    renderGroupedShell([unresolvedGroupLine({ quantity_overridden: true })]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const text = screen.getByLabelText('group-quantity-0').textContent ?? '';
    expect(text).toContain('0.000');
    expect(text).toContain('mb');
    expect(text).not.toContain('Ilość do ustalenia');
  });

  it('a freeform MANUAL-origin line in the main card/list view is never classified as unresolved', async () => {
    renderGroupedShell([
      makeLine({
        origin: 'MANUAL', unit: 'FLAT', quantity: '1.000', source_quantity: null,
        quantity_source: 'MANUAL', quantity_overridden: false, price_item_id: null,
        description: 'Transport materiałów',
      }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const text = screen.getByLabelText('group-quantity-0').textContent ?? '';
    expect(text).toContain('1.000');
    expect(text).not.toContain('Ilość do ustalenia');
  });

  it('an auto-derived Surface M2 group quantity displays numerically, unaffected', async () => {
    renderGroupedShell([
      makeLine({
        unit: 'M2', quantity: '1.284', source_quantity: '1.284',
        quantity_source: 'SURFACE_NET_AREA', quantity_overridden: false,
        description: 'Gruntowanie gruntem penetrującym',
      }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const text = screen.getByLabelText('group-quantity-0').textContent ?? '';
    expect(text).toContain('1.284');
    expect(text).not.toContain('Ilość do ustalenia');
  });

  it('an auto-derived Reveal LM group quantity displays numerically, unaffected', async () => {
    renderGroupedShell([
      makeLine({
        unit: 'LM', quantity: '4.000', source_quantity: '4.000',
        quantity_source: 'REVEAL_LENGTH', quantity_overridden: false,
        opening_id: 'opening-uuid', description: 'Praca na ościeżu',
      }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const text = screen.getByLabelText('group-quantity-0').textContent ?? '';
    expect(text).toContain('4.000');
    expect(text).not.toContain('Ilość do ustalenia');
  });

  it('an auto-derived Reveal M2 group quantity displays numerically, unaffected', async () => {
    renderGroupedShell([
      makeLine({
        unit: 'M2', quantity: '1.000', source_quantity: '1.000',
        quantity_source: 'REVEAL_AREA', quantity_overridden: false,
        opening_id: 'opening-uuid', description: 'Praca na ościeżu',
      }),
    ]);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const text = screen.getByLabelText('group-quantity-0').textContent ?? '';
    expect(text).toContain('1.000');
    expect(text).not.toContain('Ilość do ustalenia');
  });

});

// Detail-view parity for the same unresolved line (drilled-down, not the
// group card) is already covered by 'Stage 10H.1 — unresolved MANUAL
// quantity display' above, via renderShell(..., PLANNED_SURFACE_LM_KEY).

describe('Stage 10H.1 — finalize blocked by unresolved quantity', () => {
  it('shows the localized, actionable PL message for an unresolved-quantity-only rejection', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockRejectedValue(
      new Error(
        'Cannot finalize: 1 line(s) have unresolved quantity (Ilość do ustalenia). Set quantities via line overrides.',
      ),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));
    const errorText = screen.getByLabelText('estimate-finalize-error').textContent ?? '';
    expect(errorText).not.toContain('Cannot finalize');
    expect(errorText).toBe(
      'Nie można sfinalizować kosztorysu. 1 pozycji ma nieustaloną ilość. Uzupełnij ilości prac oznaczonych jako „Ilość do ustalenia” przed finalizacją kosztorysu.',
    );
  });

  it('shows the localized RU message for an unresolved-quantity-only rejection', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(estimatesApi.finalizeEstimate).mockRejectedValue(
      new Error(
        'Cannot finalize: 2 line(s) have unresolved quantity (Ilość do ustalenia). Set quantities via line overrides.',
      ),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));
    const errorText = screen.getByLabelText('estimate-finalize-error').textContent ?? '';
    expect(errorText).toBe(
      'Невозможно зафиксировать смету. У 2 позиций не определено количество. Укажите объём работ, отмеченных как «Количество не определено», перед финализацией сметы.',
    );
  });

  it('presents both blockers together when price AND quantity are both unresolved', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockRejectedValue(
      new Error(
        'Cannot finalize: 1 line(s) have no price set (Do ustalenia). Set prices in the Price Book or add line overrides. ' +
          'Cannot finalize: 1 line(s) have unresolved quantity (Ilość do ustalenia). Set quantities via line overrides.',
      ),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));
    const errorText = screen.getByLabelText('estimate-finalize-error').textContent ?? '';
    expect(errorText).not.toContain('Cannot finalize');
    expect(errorText).toContain('nie ma ustalonej ceny');
    expect(errorText).toContain('nieustaloną ilość');
  });

  it('price-unresolved-only behavior is unaffected by the new quantity blocker', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockRejectedValue(
      new Error('Cannot finalize: 1 line(s) have no price set (Do ustalenia). Set prices in the Price Book or add line overrides.'),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => screen.getByLabelText('estimate-finalize-error'));
    const errorText = screen.getByLabelText('estimate-finalize-error').textContent ?? '';
    expect(errorText).toBe(
      'Nie można sfinalizować kosztorysu. 1 pozycji nie ma ustalonej ceny. Uzupełnij ceny pozycji oznaczonych „Do ustalenia” i spróbuj ponownie.',
    );
    expect(errorText).not.toContain('nieustaloną ilość');
  });
});

describe('Stage 10G.3D — successful finalization', () => {
  it('refetches the authoritative Estimate and updates the status badge to Finalny', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'FINAL' }));
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([makeLine()]))
      .mockResolvedValueOnce(makeDetail([makeLine({ unit_price: '35.00' })], { status: 'FINAL' }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(2));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Finalny');
  });

  it('all mutation controls disappear after a successful finalization: Dodaj pozycję, Sprawdź zmiany, Edytuj, and Finalizuj itself; read-only drill-down remains', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'FINAL' }));
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([makeLine({ unit_price: '35.00' })]))
      .mockResolvedValueOnce(makeDetail([makeLine({ unit_price: '35.00' })], { status: 'FINAL' }));
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-add-manual-line-action')).toBeTruthy();
    expect(screen.getByLabelText('estimate-check-changes-action')).toBeTruthy();
    expect(screen.getByLabelText('line-edit-action-1')).toBeTruthy();

    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => expect(screen.queryByLabelText('estimate-finalize-action')).toBeNull());
    expect(screen.queryByLabelText('estimate-add-manual-line-action')).toBeNull();
    expect(screen.queryByLabelText('estimate-check-changes-action')).toBeNull();
    expect(screen.queryByLabelText('line-edit-action-1')).toBeNull();
    // Read-only drill-down remains available.
    expect(screen.getByLabelText('estimate-lines')).toBeTruthy();
    expect(screen.getByLabelText('line-quantity-1')).toBeTruthy();
  });

  it('group-level Opcje disappears from the grouped summary after finalization', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockResolvedValue(makeDetail([makeLine()], { status: 'FINAL' }));
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([makeLine({ unit_price: '35.00' })]))
      .mockResolvedValueOnce(makeDetail([makeLine({ unit_price: '35.00' })], { status: 'FINAL' }));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.getByLabelText('group-options-0')).toBeTruthy();

    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => expect(screen.queryByLabelText('group-options-0')).toBeNull());
    expect(screen.getByLabelText('estimate-groups')).toBeTruthy();
  });

  it('Usuń pozycję disappears from a manual line after finalization', async () => {
    vi.mocked(estimatesApi.finalizeEstimate).mockResolvedValue(makeDetail([makeManualLine()], { status: 'FINAL' }));
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce(makeDetail([makeManualLine({ unit_price: '250.00', amount: '250.00' })]))
      .mockResolvedValueOnce(
        makeDetail([makeManualLine({ unit_price: '250.00', amount: '250.00' })], { status: 'FINAL' }),
      );
    renderShell(makeSummary(), MANUAL_KEY);
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-delete-action-1')).toBeTruthy();

    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    await waitFor(() => screen.getByLabelText('estimate-finalize-confirm-yes'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-confirm-yes'));

    await waitFor(() => expect(screen.queryByLabelText('line-delete-action-1')).toBeNull());
  });
});

describe('Stage 10G.3D — FINAL remains fully readable', () => {
  it('a FINAL estimate still shows quantity, price, amount, provenance, and total', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: '35.00' })], makeSummary({ status: 'FINAL', total: '437.50' })),
    );
    renderShell(makeSummary({ status: 'FINAL', total: '437.50' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-quantity-1').textContent).toContain('12.500');
    expect(screen.getByLabelText('line-unit-price-1').textContent).toContain('35.00');
    expect(screen.getByLabelText('line-amount-1').textContent).toContain('437.50');
    expect(screen.getByLabelText('line-provenance-1').textContent).toBe('Salon — Ściana 1');
    expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('437.50 PLN');
  });

  it('a FINAL estimate still allows navigating back to the grouped summary', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: '35.00' })], { status: 'FINAL' }),
    );
    const onGroupKeyChange = vi.fn();
    render(
      <I18nProvider>
        <EstimateShell
          estimate={makeSummary({ status: 'FINAL' })}
          onBack={vi.fn()}
          selectedGroupKey={PLANNED_SURFACE_KEY}
          onGroupKeyChange={onGroupKeyChange}
        />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-detail-back'));
    fireEvent.click(screen.getByLabelText('estimate-detail-back'));
    expect(onGroupKeyChange).toHaveBeenCalledWith(null);
  });
});

describe('Stage 10G.3D — state isolation across estimate/version switches', () => {
  it('switching to a different estimate (unmount + fresh mount, matching real navigation) never leaks stale edit/detail state', async () => {
    // A DRAFT v2 with a line mid-edit.
    vi.mocked(estimatesApi.getEstimate).mockResolvedValueOnce(
      makeDetail([makeLine()], makeSummary({ version: 2 })),
    );
    const { unmount } = render(
      <I18nProvider>
        <EstimateShell
          estimate={makeSummary({ version: 2 })}
          onBack={vi.fn()}
          selectedGroupKey={PLANNED_SURFACE_KEY}
          onGroupKeyChange={vi.fn()}
        />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('line-edit-action-1'));
    await waitFor(() => screen.getByLabelText('line-edit-panel-1'));
    expect(screen.getByLabelText('line-edit-panel-1')).toBeTruthy();
    // Matches real navigation: ProjectWorkspace's onBack sets selectedEstimate
    // to null, fully unmounting EstimateShell before any other estimate opens.
    unmount();

    // Opening a different, FINAL v1 estimate must start completely fresh.
    const finalSummary = makeSummary({ version: 1, status: 'FINAL' });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValueOnce(
      makeDetail([makeLine({ unit_price: '35.00' })], finalSummary),
    );
    render(
      <I18nProvider>
        <EstimateShell
          estimate={finalSummary}
          onBack={vi.fn()}
          selectedGroupKey={PLANNED_SURFACE_KEY}
          onGroupKeyChange={vi.fn()}
        />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Finalny');
    expect(screen.queryByLabelText('line-edit-panel-1')).toBeNull();
    expect(screen.queryByLabelText('line-edit-action-1')).toBeNull(); // FINAL: no edit action at all
  });

  it('a manual-line form left open in one estimate never leaks into a freshly-opened different estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValueOnce(makeDetail([makeLine()]));
    const { unmount } = render(
      <I18nProvider>
        <EstimateShell estimate={makeSummary()} onBack={vi.fn()} selectedGroupKey={null} onGroupKeyChange={vi.fn()} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    await waitFor(() => screen.getByLabelText('estimate-manual-line-form'));
    unmount();

    vi.mocked(estimatesApi.getEstimate).mockResolvedValueOnce(makeDetail([makeLine()]));
    render(
      <I18nProvider>
        <EstimateShell estimate={makeSummary()} onBack={vi.fn()} selectedGroupKey={null} onGroupKeyChange={vi.fn()} />
      </I18nProvider>,
    );
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    expect(screen.queryByLabelText('estimate-manual-line-form')).toBeNull();
    expect(screen.getByLabelText('estimate-add-manual-line-action')).toBeTruthy();
  });
});

describe('Stage 10G.3D regression — accepted 10G.2/10G.3A/10G.3B/10G.3C behavior untouched', () => {
  it('regeneration preview still works alongside the new finalize action', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(makePreview());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-finalize-action')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-no-changes'));
  });

  it('manual line creation still works alongside the new finalize action', async () => {
    vi.mocked(estimatesApi.addManualEstimateLine).mockResolvedValue(makeManualLine());
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-add-manual-line-action'));
    fireEvent.change(screen.getByLabelText('manual-line-description'), { target: { value: 'Transport' } });
    fireEvent.click(screen.getByLabelText('manual-line-price-unresolved'));
    fireEvent.click(screen.getByLabelText('estimate-manual-line-save'));
    await waitFor(() => expect(estimatesApi.addManualEstimateLine).toHaveBeenCalledTimes(1));
  });

  it('NULL price still renders "Do ustalenia" (never 0.00) for a FINAL estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: null, amount: null })], { status: 'FINAL' }),
    );
    renderShell(makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-unit-price-1').textContent).toBe('Do ustalenia');
    expect(screen.getByLabelText('line-amount-1').textContent).toBe('—');
  });

  it('explicit 0.00 still renders as zero (never "Do ustalenia") for a FINAL estimate', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit_price: '0.00', amount: '0.00' })], { status: 'FINAL' }),
    );
    renderShell(makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('line-unit-price-1').textContent).toContain('0.00');
    expect(screen.getByLabelText('line-unit-price-1').textContent).not.toBe('Do ustalenia');
  });

  it('no JS Number financial arithmetic is introduced by the finalize confirmation panel', async () => {
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-finalize-action'));
    const panel = await waitFor(() => screen.getByLabelText('estimate-finalize-confirm'));
    // The confirmation panel renders no amount/quantity/price fields at all —
    // it never touches Estimate financial values, only calls the backend.
    expect(within(panel).queryByLabelText(/line-amount|line-unit-price|line-quantity/)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Stage 10G.4 — localized PriceUnit.LM presentation ("mb" / "пог. м")
// ---------------------------------------------------------------------------

describe('Stage 10G.4 — localized LM unit label', () => {
  function renderShellRu(
    summary: EstimateSummaryRead = makeSummary(),
    selectedGroupKey: string | null = PLANNED_SURFACE_KEY,
  ) {
    localStorage.setItem('locale', 'ru');
    return render(
      <I18nProvider>
        <EstimateShell estimate={summary} onBack={vi.fn()} selectedGroupKey={selectedGroupKey} onGroupKeyChange={vi.fn()} />
      </I18nProvider>,
    );
  }

  it('PL renders an LM line as "mb", never raw "LM"', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit: 'LM', quantity: '10.540' })]),
    );
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const text = screen.getByLabelText('group-quantity-0').textContent ?? '';
    expect(text).toContain('mb');
    expect(text).not.toMatch(/\bLM\b/);
  });

  it('RU renders an LM line as "пог. м", never raw "LM"', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit: 'LM', quantity: '10.540' })]),
    );
    renderShellRu(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const text = screen.getByLabelText('group-quantity-0').textContent ?? '';
    expect(text).toContain('пог. м');
    expect(text).not.toMatch(/\bLM\b/);
  });

  it('a REVEAL-origin LM line in the grouped summary view also shows "mb"', async () => {
    const revealLine = makeLine({
      id: 'reveal-1',
      unit: 'LM',
      quantity: '5.040',
      opening_id: 'opening-1',
      surface_id: null,
    });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([revealLine]));
    renderShell(makeSummary(), null);
    await waitFor(() => screen.getByLabelText('estimate-groups'));
    const text = screen.getByLabelText('group-quantity-0').textContent ?? '';
    expect(text).toContain('mb');
    expect(text).not.toMatch(/\bLM\b/);
  });

  it('the "Sprawdź zmiany" preview shows "mb" for an LM change entry, never raw "LM"', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({ added: 1, changes: [makeChange({ change_type: 'ADDED', unit: 'LM', new_source_quantity: '3.200' })] }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    await waitFor(() => screen.getByLabelText('estimate-regeneration-category-ADDED'));
    const text = screen.getByLabelText('estimate-regeneration-change-quantity-ADDED-0').textContent ?? '';
    expect(text).toContain('mb');
    expect(text).not.toMatch(/\bLM\b/);
  });

  it('M2 remains localized as "m²" — unaffected by the LM fix', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ unit: 'M2', quantity: '10.540' })]),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    const text = screen.getByLabelText('line-quantity-1').textContent ?? '';
    expect(text).toContain('m²');
    expect(text).not.toMatch(/\bM2\b/);
  });
});

describe('Stage 12F — coefficient provenance', () => {
  const snapshot = [
    {
      group_id: 'grp-height', group_code: 'HEIGHT', group_name: 'Wysokość',
      option_id: 'opt-high', option_code: 'HIGH', option_name: 'wysoka',
      percentage: '20.00', is_base: false,
    },
    {
      group_id: 'grp-furniture', group_code: 'FURNITURE', group_name: 'Umeblowanie',
      option_id: 'opt-furnished', option_code: 'FURNISHED', option_name: 'umeblowane',
      percentage: '10.00', is_base: false,
    },
  ];

  it('renders the stored snapshot: base price, each adjustment and the additive total', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ base_unit_price: '40.00', unit_price: '52.00', coefficient_snapshot: snapshot })]),
    );
    renderShell();
    const block = await screen.findByLabelText('line-coefficient-snapshot-1');
    const text = block.textContent ?? '';
    expect(text).toContain('Cena bazowa');
    expect(text).toContain('40.00');
    expect(text).toContain('Wysokość');
    expect(text).toContain('wysoka');
    expect(text).toContain('+20%');
    expect(text).toContain('umeblowane');
    expect(text).toContain('+10%');
    expect(text).toContain('+30%');
  });

  it('shows no coefficient block for lines without a snapshot', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail([makeLine({ coefficient_snapshot: null })]));
    renderShell();
    await screen.findByLabelText('estimate-lines');
    expect(screen.queryByLabelText('line-coefficient-snapshot-1')).toBeNull();
  });

  it('distinguishes a manually overridden price from a calculated one', async () => {
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue(
      makeDetail([makeLine({ price_override: true, base_unit_price: '40.00', coefficient_snapshot: snapshot })]),
    );
    renderShell();
    const override = await screen.findByLabelText('line-price-override-1');
    expect(override.textContent).toContain('Cena zmieniona ręcznie');
    expect(override.textContent).toContain('Cena ręczna');
  });

  it('shows coefficient changes in the regeneration preview', async () => {
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockResolvedValue(
      makePreview({
        updated: 1,
        changes: [
          makeChange({
            change_type: 'UPDATED',
            old_base_unit_price: '40.00',
            new_base_unit_price: '40.00',
            old_coefficient_snapshot: [snapshot[0]],
            new_coefficient_snapshot: snapshot,
          }),
        ],
      }),
    );
    renderShell();
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    fireEvent.click(screen.getByLabelText('estimate-check-changes-action'));
    const block = await screen.findByLabelText('estimate-regeneration-change-coefficients-UPDATED-0');
    const text = block.textContent ?? '';
    expect(text).toContain('+20%');
    expect(text).toContain('+30%');
  });
});
