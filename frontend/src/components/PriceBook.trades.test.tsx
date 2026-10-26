import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as coefficientsApi from '../api/coefficients';
import * as priceItemsApi from '../api/priceItems';
import * as tradesApi from '../api/trades';
import { I18nProvider } from '../hooks/useI18n';
import { resetTrades } from '../hooks/useTrades';
import { CATALOG } from '../test/tradesFixture';
import { PriceItem } from '../types/priceItem';
import { PriceBook } from './PriceBook';

vi.mock('../api/priceItems', () => ({ fetchPriceItems: vi.fn(), createPriceItem: vi.fn(), updatePriceItem: vi.fn(), archivePriceItem: vi.fn(), restorePriceItem: vi.fn() }));
vi.mock('../api/coefficients', () => ({ fetchCoefficientGroups: vi.fn() }));
vi.mock('../api/trades', () => ({ fetchTrades: vi.fn(), saveTrades: vi.fn() }));

const item = (id: string, category: PriceItem['category'], name: string): PriceItem => ({
  id, code: `CUSTOM_${id}`, name_key: null, display_name: name, category, unit: 'M2', price: '1.00', currency: 'PLN', price_scope: 'LABOR', quality_level: null,
  is_archived: false, created_at: '2026-09-13T10:00:00Z', updated_at: '2026-09-13T10:00:00Z',
});
const ITEMS = [item('a', 'PAINTING', 'Malowanie dwukrotne'), item('b', 'ELECTRICAL', 'Punkt elektryczny'), item('c', 'TILE', 'Układanie płytek'), item('d', 'POINTS_ROUTES', 'Trasa uniwersalna')];

async function openList() {
  render(<I18nProvider><PriceBook /></I18nProvider>);
  fireEvent.click(screen.getByLabelText('pricebook-maintab-items'));
  await screen.findByLabelText('pricebook-list');
}

describe('PriceBook — the trades of the owner (V2-13)', () => {
  beforeEach(() => {
    resetTrades();
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: ITEMS, total: ITEMS.length });
    vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ groups: [] } as never);
  });
  afterEach(() => {
    cleanup();
    resetTrades();
  });

  it('shows everything, and no switch, while every trade is on', async () => {
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue(CATALOG);
    await openList();
    await waitFor(() => expect(tradesApi.fetchTrades).toHaveBeenCalled());
    expect(screen.getByLabelText('price-item-b')).toBeInTheDocument();
    expect(screen.queryByLabelText('pricebook-show-all-trades')).toBeNull();
    const select = screen.getByLabelText('pricebook-category-filter') as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toContain('ELECTRICAL');
  });

  it('hides the positions and the filter entries of the trades that are off, keeps the universal ones, and counts what is hidden', async () => {
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING', 'TILE'] });
    await openList();
    const toggle = await screen.findByLabelText('pricebook-show-all-trades');
    expect(toggle).toHaveTextContent('Pokaż wszystkie kategorie (1)');
    expect(toggle.className).toContain('min-h-11');
    expect(screen.queryByLabelText('price-item-b')).toBeNull();
    for (const id of ['a', 'c', 'd']) expect(screen.getByLabelText(`price-item-${id}`)).toBeInTheDocument();
    const values = Array.from((screen.getByLabelText('pricebook-category-filter') as HTMLSelectElement).options).map((o) => o.value);
    expect(values).not.toContain('ELECTRICAL');
    expect(values).not.toContain('DRYWALL');
    expect(values).toEqual(expect.arrayContaining(['PAINTING', 'TILE', 'POINTS_ROUTES', 'MATERIAL', 'OTHER']));
  });

  it('"show all" lifts the filter for the moment and puts it back', async () => {
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING'] });
    await openList();
    fireEvent.click(await screen.findByLabelText('pricebook-show-all-trades'));
    expect(screen.getByLabelText('price-item-b')).toBeInTheDocument();
    expect(screen.getByLabelText('pricebook-show-all-trades')).toHaveTextContent('Ukryj kategorie innych zawodów');
    expect(Array.from((screen.getByLabelText('pricebook-category-filter') as HTMLSelectElement).options).map((o) => o.value)).toContain('ELECTRICAL');
    fireEvent.click(screen.getByLabelText('pricebook-show-all-trades'));
    expect(screen.queryByLabelText('price-item-b')).toBeNull();
  });

  it('says why the list is empty when every position belongs to a trade that is off', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [ITEMS[1]], total: 1 });
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING'] });
    await openList().catch(() => undefined);
    expect(await screen.findByLabelText('pricebook-empty')).toHaveTextContent('Wszystkie pozycje należą do wyłączonych zawodów');
    expect(screen.getByLabelText('pricebook-show-all-trades')).toBeInTheDocument();
  });

  it('a chosen category that becomes hidden is dropped from the filter', async () => {
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING', 'ELECTRIC'] });
    await openList();
    const select = await screen.findByLabelText('pricebook-category-filter');
    await act(async () => { fireEvent.change(select, { target: { value: 'ELECTRICAL' } }); });
    expect((select as HTMLSelectElement).value).toBe('ELECTRICAL');
    await act(async () => { await (await import('../hooks/useTrades')).refreshTrades(); });
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING'] });
    await act(async () => { await (await import('../hooks/useTrades')).refreshTrades(); });
    await waitFor(() => expect((screen.getByLabelText('pricebook-category-filter') as HTMLSelectElement).value).toBe(''));
  });
});
