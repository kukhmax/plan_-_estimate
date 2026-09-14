import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketEvidenceApi from '../api/marketEvidence';
import * as priceItemsApi from '../api/priceItems';
import { I18nProvider } from '../hooks/useI18n';
import { PriceItem } from '../types/priceItem';
import {
  PriceMarketReference,
  PriceMarketReferenceListResponse,
  PriceSource,
} from '../types/marketEvidence';
import { PriceBook } from './PriceBook';

vi.mock('../api/priceItems', () => ({
  fetchPriceItems: vi.fn(),
  createPriceItem: vi.fn(),
  updatePriceItem: vi.fn(),
  archivePriceItem: vi.fn(),
  restorePriceItem: vi.fn(),
}));

vi.mock('../api/marketEvidence', () => ({
  fetchMarketEvidence: vi.fn(),
}));

const item: PriceItem = {
  id: 'item-1',
  code: 'CENNIK_SKIM_2L_M2',
  name_key: null,
  display_name: 'Szpachlowanie 2 warstwy',
  category: 'SKIM_COAT',
  unit: 'M2',
  price: '70.00',
  currency: 'PLN',
  price_scope: 'LABOR',
  quality_level: null,
  is_archived: false,
  created_at: '2026-09-13T10:00:00Z',
  updated_at: '2026-09-13T10:00:00Z',
};

const archivedItem: PriceItem = { ...item, id: 'item-4', is_archived: true };

function makeSource(over: Partial<PriceSource> = {}): PriceSource {
  return {
    id: 'src-1',
    source_name: 'Firma Wykończeniowa sp. z o.o.',
    source_type: 'CONTRACTOR_PRICE_LIST',
    source_url: null,
    source_region: 'Kraków',
    quoted_price_min: null,
    quoted_price_max: null,
    quoted_price_single: null,
    quoted_unit: null,
    note: null,
    checked_at: '2026-09-13T10:00:00Z',
    ...over,
  };
}

function makeReference(
  over: Partial<PriceMarketReference> = {},
  sources: PriceSource[] = [makeSource()],
): PriceMarketReference {
  return {
    id: 'mr-1',
    region: 'Kraków',
    unit: 'M2',
    currency: 'PLN',
    market_min: '55.00',
    market_max: '75.00',
    reference_price: null,
    methodology_note: null,
    checked_at: '2026-09-13T10:00:00Z',
    sources,
    ...over,
  };
}

function renderBook() {
  return render(
    <I18nProvider>
      <PriceBook />
    </I18nProvider>,
  );
}

describe('PriceBook — market evidence (Stage 9E.6B)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValue({ items: [], total: 0 });
  });

  it('keeps the owner price primary with a Moja cena label above the market data', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    expect(screen.getByText('70,00 zł')).toBeInTheDocument();
    expect(screen.getByText('Moja cena')).toBeInTheDocument();
    const market = await screen.findByLabelText('price-item-market-item-1');
    expect(market).toHaveTextContent('Rynek:');
    expect(market).toHaveTextContent('55,00–75,00 zł / m²');
  });

  it('renders the market range with unit when evidence exists', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    renderBook();

    const market = await screen.findByLabelText('price-item-market-item-1');
    expect(market).toHaveTextContent('55,00–75,00');
    expect(market).toHaveTextContent('zł / m²');
  });

  it('renders the checked date against the market reference', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    renderBook();

    const market = await screen.findByLabelText('price-item-market-item-1');
    expect(market).toHaveTextContent('Sprawdzono: 13.09.2026');
  });

  it('shows the source count on the disclosure control', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [
        makeReference(
          {},
          [makeSource(), makeSource({ id: 'src-2' }), makeSource({ id: 'src-3' })],
        ),
      ],
      total: 1,
    });
    renderBook();

    const toggle = await screen.findByLabelText('price-item-sources-toggle-item-1');
    expect(toggle).toHaveTextContent('Źródła (3)');
  });

  it('opens and closes the source list via progressive disclosure', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    expect(screen.queryByText('Firma Wykończeniowa sp. z o.o.')).not.toBeInTheDocument();

    fireEvent.click(await screen.findByLabelText('price-item-sources-toggle-item-1'));
    expect(await screen.findByText('Firma Wykończeniowa sp. z o.o.')).toBeInTheDocument();

    fireEvent.click(await screen.findByLabelText('price-item-sources-toggle-item-1'));
    await waitFor(() =>
      expect(screen.queryByText('Firma Wykończeniowa sp. z o.o.')).not.toBeInTheDocument(),
    );
  });

  it('formats a SINGLE source quote with two decimals', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference({}, [makeSource({ quoted_price_single: '40.00' })])],
      total: 1,
    });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    fireEvent.click(await screen.findByLabelText('price-item-sources-toggle-item-1'));
    const source = await screen.findByLabelText('price-item-source-item-1-0');
    expect(source).toHaveTextContent('40,00 zł');
  });

  it('formats a RANGE source quote as min–max with two decimals', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [
        makeReference(
          {},
          [makeSource({ quoted_price_min: '30.00', quoted_price_max: '38.00' })],
        ),
      ],
      total: 1,
    });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    fireEvent.click(await screen.findByLabelText('price-item-sources-toggle-item-1'));
    const source = await screen.findByLabelText('price-item-source-item-1-0');
    expect(source).toHaveTextContent('30,00–38,00 zł');
  });

  it('shows the QUALITATIVE note and no numeric quote', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference({}, [makeSource({ note: 'Wycena indywidualna po oględzinach.' })])],
      total: 1,
    });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    fireEvent.click(await screen.findByLabelText('price-item-sources-toggle-item-1'));
    const source = await screen.findByLabelText('price-item-source-item-1-0');
    expect(source).toHaveTextContent('Wycena indywidualna po oględzinach.');
    expect(source).not.toHaveTextContent(/^\d+,\d+ zł$/);
  });

  it('handles a source without a URL (no link, source still renders)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    fireEvent.click(await screen.findByLabelText('price-item-sources-toggle-item-1'));
    const source = await screen.findByLabelText('price-item-source-item-1-0');
    expect(source).toHaveTextContent('Firma Wykończeniowa sp. z o.o.');
    expect(within(source).queryByRole('link')).not.toBeInTheDocument();
  });

  it('renders a tappable external source link when a URL is present', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference({}, [makeSource({ source_url: 'https://example.com/cennik' })])],
      total: 1,
    });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    fireEvent.click(await screen.findByLabelText('price-item-sources-toggle-item-1'));
    const link = await screen.findByLabelText('price-item-source-link-item-1-0');
    expect(link).toHaveTextContent('Otwórz źródło');
    expect(link).toHaveAttribute('href', 'https://example.com/cennik');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('localizes the source type in PL', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    fireEvent.click(await screen.findByLabelText('price-item-sources-toggle-item-1'));
    const source = await screen.findByLabelText('price-item-source-item-1-0');
    expect(source).toHaveTextContent('Cennik wykonawcy');
    expect(source).toHaveTextContent('Kraków');
  });

  it('localizes the source type and labels in RU', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    const market = await screen.findByLabelText('price-item-market-item-1');
    expect(market).toHaveTextContent('Рынок:');
    const toggle = await screen.findByLabelText('price-item-sources-toggle-item-1');
    expect(toggle).toHaveTextContent('Источники (1)');
    fireEvent.click(toggle);
    const source = await screen.findByLabelText('price-item-source-item-1-0');
    expect(source).toHaveTextContent('Прайс подрядчика');
  });

  it('shows a graceful no-evidence state', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [],
      total: 0,
    });
    renderBook();

    const empty = await screen.findByLabelText('price-item-market-empty-item-1');
    expect(empty).toHaveTextContent('Brak danych rynkowych');
  });

  it('renders the optional reference price as a secondary point of reference', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference({ reference_price: '60.00' })],
      total: 1,
    });
    renderBook();

    const market = await screen.findByLabelText('price-item-market-item-1');
    expect(market).toHaveTextContent('Punkt odniesienia: 60,00 zł');
  });

  it('keeps market evidence visible on an archived item', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems)
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValueOnce({ items: [archivedItem], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    renderBook();

    fireEvent.click(await screen.findByLabelText('pricebook-tab-archived'));
    const market = await screen.findByLabelText('price-item-market-item-4');
    expect(market).toHaveTextContent('55,00–75,00 zł / m²');
  });

  it('shows a compact loading state until the evidence resolves', async () => {
    let resolveEvidence!: (value: PriceMarketReferenceListResponse) => void;
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockReturnValueOnce(
      new Promise<PriceMarketReferenceListResponse>((resolve) => {
        resolveEvidence = (value) => resolve(value);
      }),
    );
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    const loading = await screen.findByLabelText('price-item-market-loading-item-1');
    expect(loading).toHaveTextContent('Ładowanie danych rynkowych...');

    resolveEvidence({ items: [makeReference()], total: 1 });
    const market = await screen.findByLabelText('price-item-market-item-1');
    expect(market).toHaveTextContent('55,00–75,00');
  });

  it('collapses silently when the evidence API fails without breaking the Price Book', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockRejectedValueOnce(
      new Error('Failed to fetch market evidence: 500'),
    );
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    await waitFor(() => {
      expect(screen.queryByLabelText(/^price-item-market-/)).not.toBeInTheDocument();
    });
    expect(screen.getByText('70,00 zł')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('updates evidence labels when the UI language changes', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    const first = renderBook();
    await screen.findByText('Szpachlowanie 2 warstwy');
    fireEvent.click(await screen.findByLabelText('price-item-sources-toggle-item-1'));
    const plSource = await screen.findByLabelText('price-item-source-item-1-0');
    expect(plSource).toHaveTextContent('Cennik wykonawcy');
    first.unmount();

    localStorage.setItem('locale', 'ru');
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    fireEvent.click(await screen.findByLabelText('price-item-sources-toggle-item-1'));
    const ruSource = await screen.findByLabelText('price-item-source-item-1-0');
    expect(ruSource).toHaveTextContent('Прайс подрядчика');
    expect(await screen.findByLabelText('price-item-market-item-1')).toHaveTextContent('Рынок:');
  });

  it('does not expose market evidence fields in the Add or Edit forms', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({ items: [], total: 0 });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');

    fireEvent.click(screen.getByLabelText('add-price-item'));
    let form = screen.getByLabelText('price-item-form');
    expect(within(form).queryByLabelText(/market|source|rynek|рынок|источник/i)).not.toBeInTheDocument();
    expect(within(form).getByLabelText('price-item-price')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('price-item-options-item-1'));
    fireEvent.click(screen.getByLabelText('edit-price-item-item-1'));
    form = screen.getByLabelText('price-item-form');
    expect(within(form).queryByLabelText(/market|source|rynek|рынок|источник/i)).not.toBeInTheDocument();
    expect(within(form).getByLabelText('price-item-price')).toBeInTheDocument();
  });

  it('keeps the owner price editing behaviour unchanged', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({ items: [item], total: 1 });
    vi.mocked(marketEvidenceApi.fetchMarketEvidence).mockResolvedValueOnce({
      items: [makeReference()],
      total: 1,
    });
    vi.mocked(priceItemsApi.updatePriceItem).mockResolvedValueOnce({ ...item, price: '3.33' });
    renderBook();

    await screen.findByText('Szpachlowanie 2 warstwy');
    fireEvent.click(screen.getByLabelText('price-item-options-item-1'));
    fireEvent.click(screen.getByLabelText('edit-price-item-item-1'));
    fireEvent.change(screen.getByLabelText('price-item-price'), { target: { value: '3.33' } });
    fireEvent.submit(screen.getByLabelText('price-item-form'));

    await waitFor(() =>
      expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith(
        'item-1',
        expect.objectContaining({ price: '3.33' }),
      ),
    );
  });
});