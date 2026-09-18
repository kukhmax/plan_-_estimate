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
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as estimatesApi from '../api/estimates';
import { I18nProvider } from '../hooks/useI18n';
import type { EstimateLineRead, EstimateRead, EstimateSummaryRead } from '../types/estimate';
import { EstimateShell } from './EstimateShell';

vi.mock('../api/estimates', () => ({
  listEstimates: vi.fn(),
  generateEstimate: vi.fn(),
  getEstimate: vi.fn(),
}));

const PROJECT_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const ESTIMATE_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';

// Group key for the default makeLine() (PLANNED_WORK, price_item_id=pi-1, scope=LABOR, unit=M2, no opening_id)
const PLANNED_SURFACE_KEY = 'planned::pi-1::LABOR::M2::surface';
const PLANNED_REVEAL_KEY = 'planned::pi-1::LABOR::M2::reveal';
const MANUAL_KEY = 'manual::line-1';

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
  vi.mocked(estimatesApi.getEstimate).mockResolvedValue(makeDetail());
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
    renderShell(makeSummary({ status: 'FINAL' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Finalny');
  });

  it('shows ACCEPTED status badge (PL)', async () => {
    renderShell(makeSummary({ status: 'ACCEPTED' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Zaakceptowany');
  });

  it('shows ARCHIVED status badge (PL)', async () => {
    renderShell(makeSummary({ status: 'ARCHIVED' }));
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
    renderShell(makeSummary({ name: 'Kosztorys bazowy' }));
    await waitFor(() => screen.getByLabelText('estimate-lines'));
    expect(screen.getByText('Kosztorys bazowy')).toBeTruthy();
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
    expect(screen.getByLabelText('line-quantity-1').textContent).toContain('M2');
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
    expect(screen.getByLabelText('line-qty-override-1').textContent).toContain('M2');
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
    expect(screen.getByLabelText('group-quantity-0').textContent).toContain('M2');
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
