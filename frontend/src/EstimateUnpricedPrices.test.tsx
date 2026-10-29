import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as estimatesApi from './api/estimates';
import * as marketApi from './api/marketEvidence';
import * as priceItemsApi from './api/priceItems';
import { EstimateShell } from './components/EstimateShell';
import { StarterPricesSheet } from './components/StarterPricesSheet';
import { I18nProvider } from './hooks/useI18n';
import type { EstimateSummaryRead } from './types/estimate';
import type { PriceItem } from './types/priceItem';

vi.mock('./api/estimates', () => ({
  getEstimate: vi.fn(), setEstimateVat: vi.fn(), patchEstimateLine: vi.fn(), previewEstimateRegeneration: vi.fn(), regenerateEstimate: vi.fn(),
  addManualEstimateLine: vi.fn(), deleteEstimateLine: vi.fn(), finalizeEstimate: vi.fn(), fillEstimatePrices: vi.fn(),
}));
vi.mock('./api/priceItems', async (orig) => ({ ...(await orig<typeof import('./api/priceItems')>()), fetchPriceItems: vi.fn(), updatePriceItem: vi.fn() }));
vi.mock('./api/marketEvidence', () => ({ fetchMarketEvidence: vi.fn() }));

const PROJECT_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const item = (id: string, code: string, name: string, price: string | null = null): PriceItem => ({
  id, code, name_key: null, display_name: name, category: 'PLUMBING' as PriceItem['category'], unit: 'PCS', price, currency: 'PLN',
  price_scope: 'LABOR', quality_level: null, is_archived: false, created_at: 'x', updated_at: 'x',
});
const WATER = item('pi-water', 'PT_WATER', 'Punkt wodny');
const DRAIN = item('pi-drain', 'PT_DRAIN', 'Punkt kanalizacyjny');
const OTHER = item('pi-other', 'PT_OTHER', 'Inna pozycja', '50.00');
const reference = (price: string | null, unit = 'PCS') => ({
  items: [{ id: 'r', region: 'PL', unit, currency: 'PLN', market_min: '40.00', market_max: '70.00', reference_price: price, methodology_note: null, checked_at: '2026-10-01', sources: [] }],
  total: 1,
});

function summary(over: Partial<EstimateSummaryRead> = {}): EstimateSummaryRead {
  return {
    id: 'est-1', project_id: PROJECT_ID, version: 1, status: 'DRAFT', name: null, total: '480.00', currency: 'PLN',
    vat_mode: null, vat_rate_percent: null, vat_amount: null, gross_total: null, created_at: 'x', updated_at: 'x', ...over,
  };
}
const LINE = (id: string, priceItem: string | null, unit_price: string | null) => ({
  id, estimate_id: 'est-1', origin: 'MANUAL', position: 0, description: 'x', unit: 'PCS', quantity: '4.000', unit_price, amount: unit_price ? '480.00' : null,
  price_item_id: priceItem, planned_work_id: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem('locale', 'pl');
  vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [WATER, DRAIN, OTHER], total: 3 });
  vi.mocked(priceItemsApi.updatePriceItem).mockImplementation(async (id, body) => ({ ...WATER, id, price: (body as { price: string }).price }));
  vi.mocked(marketApi.fetchMarketEvidence).mockImplementation(async (id: string) => (id === 'pi-water' ? reference('55.00') : reference(null)) as never);
});

describe('UX walk B7: the prices of the lines without a price are entered in the estimate', () => {
  it('opens the rows of the price book behind the unpriced lines, saves the typed prices and fills the estimate', async () => {
    const base = summary();
    vi.mocked(estimatesApi.getEstimate)
      .mockResolvedValueOnce({ ...base, lines: [LINE('l1', 'pi-water', null), LINE('l2', 'pi-water', null), LINE('l3', 'pi-drain', null), LINE('l4', null, null), LINE('l5', 'pi-other', '50.00')] } as never)
      .mockResolvedValue({ ...base, total: '1400.00', lines: [] } as never);
    vi.mocked(estimatesApi.fillEstimatePrices).mockResolvedValue({ filled: 3, missing: 1, missing_planned: 0 });
    render(<I18nProvider><EstimateShell estimate={base} onBack={vi.fn()} selectedGroupKey={null} onGroupKeyChange={vi.fn()} /></I18nProvider>);
    const box = await screen.findByLabelText('estimate-unpriced');
    expect(box).toHaveTextContent('Wpisz ich ceny tutaj');
    const open = within(box).getByLabelText('estimate-set-prices');
    expect(open).toHaveTextContent('Wpisz ceny tych pozycji (2)'); // two items behind four lines; a line with no item is not one
    expect(open.className).toContain('min-h-11');
    fireEvent.click(open);
    const form = await screen.findByLabelText('starter-prices-form');
    expect(form).toHaveTextContent('Ceny pozycji bez ceny');
    expect(within(form).getByLabelText('starter-price-PT_WATER')).toBeInTheDocument();
    expect(within(form).getByLabelText('starter-price-PT_DRAIN')).toBeInTheDocument();
    expect(within(form).queryByLabelText('starter-price-PT_OTHER')).toBeNull();
    fireEvent.change(within(form).getByLabelText('starter-price-PT_DRAIN'), { target: { value: '90' } });
    const use = await within(form).findByLabelText('starter-use-reference-PT_WATER');
    expect(use).toHaveTextContent('Użyj ceny orientacyjnej: 55,00');
    fireEvent.click(use);
    expect(within(form).getByLabelText('starter-price-PT_WATER')).toHaveValue('55,00');
    expect(priceItemsApi.updatePriceItem).not.toHaveBeenCalled(); // the tap only fills the field
    await act(async () => { fireEvent.submit(form); });
    await waitFor(() => expect(estimatesApi.fillEstimatePrices).toHaveBeenCalledWith(PROJECT_ID, 'est-1'));
    expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith('pi-water', { price: '55.00' });
    expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith('pi-drain', { price: '90' });
    expect(await screen.findByText(/Uzupełniono z cennika: 3\./)).toBeInTheDocument();
  });

  it('the works of the plan are repriced by one more tap: "Sprawdź zmiany" opens from the message', async () => {
    const base = summary();
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue({ ...base, lines: [{ ...LINE('l1', 'pi-water', null), origin: 'PLANNED_WORK', planned_work_id: 'pw1' }] } as never);
    vi.mocked(estimatesApi.fillEstimatePrices).mockResolvedValue({ filled: 0, missing: 1, missing_planned: 1 });
    vi.mocked(estimatesApi.previewEstimateRegeneration).mockReturnValue(new Promise(() => undefined));
    render(<I18nProvider><EstimateShell estimate={base} onBack={vi.fn()} selectedGroupKey={null} onGroupKeyChange={vi.fn()} /></I18nProvider>);
    fireEvent.click(await screen.findByLabelText('estimate-set-prices'));
    const form = await screen.findByLabelText('starter-prices-form');
    fireEvent.change(await within(form).findByLabelText('starter-price-PT_WATER'), { target: { value: '60' } });
    await act(async () => { fireEvent.submit(form); });
    const check = await screen.findByLabelText('estimate-fill-check-changes');
    expect(check).toHaveTextContent('Sprawdź zmiany — przelicz prace planu (1)');
    expect(check.className).toContain('min-h-11');
    fireEvent.click(check);
    await waitFor(() => expect(estimatesApi.previewEstimateRegeneration).toHaveBeenCalledWith(PROJECT_ID, 'est-1'));
    expect(screen.queryByLabelText('estimate-fill-check-changes')).toBeNull(); // the panel is open now
  });

  it('offers no entry on a finished estimate', async () => {
    const base = summary({ status: 'FINAL' });
    vi.mocked(estimatesApi.getEstimate).mockResolvedValue({ ...base, lines: [LINE('l1', 'pi-water', null)] } as never);
    render(<I18nProvider><EstimateShell estimate={base} onBack={vi.fn()} selectedGroupKey={null} onGroupKeyChange={vi.fn()} /></I18nProvider>);
    await screen.findByLabelText('estimate-unpriced');
    expect(screen.queryByLabelText('estimate-set-prices')).toBeNull();
  });
});

describe('UX walk B7: the market reference is taken only by a tap', () => {
  it('puts the references into the empty fields only, never a reference in another unit, and saves nothing by itself', async () => {
    vi.mocked(marketApi.fetchMarketEvidence).mockImplementation(async (id: string) =>
      (id === 'pi-water' ? reference('55.00') : id === 'pi-drain' ? reference('80.00', 'M2') : reference('60.00')) as never);
    const typed = { ...OTHER, id: 'pi-typed', code: 'PT_TYPED', price: null };
    const load = async () => ({ items: [WATER, DRAIN, typed], total: 3 });
    render(<I18nProvider><StarterPricesSheet onClose={vi.fn()} load={load} /></I18nProvider>);
    const form = await screen.findByLabelText('starter-prices-form');
    fireEvent.change(await within(form).findByLabelText('starter-price-PT_TYPED'), { target: { value: '45' } });
    const all = await within(form).findByLabelText('starter-use-all-references');
    expect(all).toHaveTextContent('(1)'); // the water only: the drain's reference is per m², the typed row is not empty
    fireEvent.click(all);
    expect(within(form).getByLabelText('starter-price-PT_WATER')).toHaveValue('55,00');
    expect(within(form).getByLabelText('starter-price-PT_DRAIN')).toHaveValue('');
    expect(within(form).getByLabelText('starter-price-PT_TYPED')).toHaveValue('45');
    expect(within(form).queryByLabelText('starter-use-reference-PT_DRAIN')).toBeNull();
    expect(within(form).getByLabelText('starter-use-reference-PT_TYPED')).toHaveTextContent('60,00'); // offered, not forced
    expect(priceItemsApi.updatePriceItem).not.toHaveBeenCalled();
  });
});
