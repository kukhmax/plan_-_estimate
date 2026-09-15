import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as priceItemsApi from '../api/priceItems';
import { I18nProvider } from '../hooks/useI18n';
import { PriceItem } from '../types/priceItem';
import { PriceBook } from './PriceBook';

vi.mock('../api/priceItems', () => ({
  fetchPriceItems: vi.fn(),
  createPriceItem: vi.fn(),
  updatePriceItem: vi.fn(),
  archivePriceItem: vi.fn(),
  restorePriceItem: vi.fn(),
}));

const seedWallp: PriceItem = {
  id: 'item-1',
  code: 'CENNIK_PREP_WALLP-01',
  name_key: 'pricebook.seed.prep_wallp',
  display_name: null,
  category: 'PREPARATION',
  unit: 'M2',
  price: null,
  currency: 'PLN',
  price_scope: 'LABOR',
  quality_level: null,
  is_archived: false,
  created_at: '2026-09-13T10:00:00Z',
  updated_at: '2026-09-13T10:00:00Z',
};

const zeroSkim: PriceItem = {
  id: 'item-2',
  code: 'CUSTOM_ZERO0000001',
  name_key: null,
  display_name: 'Promocyjne 0 zł',
  category: 'SKIM_COAT',
  unit: 'M2',
  price: '0.00',
  currency: 'PLN',
  price_scope: 'LABOR',
  quality_level: null,
  is_archived: false,
  created_at: '2026-09-13T10:00:00Z',
  updated_at: '2026-09-13T10:00:00Z',
};

function renderBook() {
  return render(
    <I18nProvider>
      <PriceBook />
    </I18nProvider>,
  );
}

describe('PriceBook — nullable owner price (Stage 9E.7)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
  });

  it('renders "Do ustalenia" (not 0,00 zł) for a null seed price in PL', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedWallp],
      total: 1,
    });
    renderBook();

    await screen.findByText('Usuwanie tapet (zdzieranie, utylizacja)');
    expect(screen.getByText('Do ustalenia')).toBeInTheDocument();
    expect(screen.getByText(/ m²/)).toBeInTheDocument();
    expect(screen.queryByText('0,00 zł')).not.toBeInTheDocument();
  });

  it('renders "Уточняется" for a null seed price in RU', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedWallp],
      total: 1,
    });
    renderBook();

    await screen.findByText('Снятие обоев (сдирание, утилизация)');
    expect(screen.getByText('Уточняется')).toBeInTheDocument();
  });

  it('renders an explicit 0.00 owner price as a real price (0,00 zł)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [zeroSkim],
      total: 1,
    });
    renderBook();

    await screen.findByText('Promocyjne 0 zł');
    expect(screen.getByText('0,00 zł')).toBeInTheDocument();
    expect(screen.queryByText('Do ustalenia')).not.toBeInTheDocument();
  });

  it('lets the owner type a price on a null-priced seed row (inline input starts empty, not 0)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedWallp],
      total: 1,
    });
    vi.mocked(priceItemsApi.updatePriceItem).mockResolvedValueOnce({
      ...seedWallp,
      price: '20.00',
    });
    renderBook();
    await screen.findByText('Usuwanie tapet (zdzieranie, utylizacja)');

    fireEvent.click(screen.getByLabelText('edit-price-item-item-1'));

    const priceInput = screen.getByLabelText('inline-price-input-item-1');
    expect(priceInput).toHaveValue('');
    fireEvent.change(priceInput, { target: { value: '20' } });
    fireEvent.click(screen.getByLabelText('inline-price-save-item-1'));

    await waitFor(() =>
      expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith('item-1', { price: '20' }),
    );
  });

  it('still requires a price when saving a null-priced seed row', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedWallp],
      total: 1,
    });
    renderBook();
    await screen.findByText('Usuwanie tapet (zdzieranie, utylizacja)');

    fireEvent.click(screen.getByLabelText('edit-price-item-item-1'));
    fireEvent.click(screen.getByLabelText('inline-price-save-item-1'));

    expect(
      await within(screen.getByLabelText('inline-price-edit-item-1')).findByText('Podaj cenę.'),
    ).toBeInTheDocument();
    expect(priceItemsApi.updatePriceItem).not.toHaveBeenCalled();
  });

  it('shows a null-priced seed resolved to its catalog name alongside a priced row', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedWallp, zeroSkim],
      total: 2,
    });
    renderBook();

    await screen.findByText('Usuwanie tapet (zdzieranie, utylizacja)');
    expect(screen.getByText('Promocyjne 0 zł')).toBeInTheDocument();
    expect(screen.getByText('Do ustalenia')).toBeInTheDocument();
    expect(screen.getByText('0,00 zł')).toBeInTheDocument();
  });

  // Stage 9E.7.1: a null-priced canonical row must be editable end-to-end.
  it('edits a null-priced seed row end-to-end: empty input → 65.00 → PATCH → 65,00 zł card', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedWallp],
      total: 1,
    });
    vi.mocked(priceItemsApi.updatePriceItem).mockResolvedValueOnce({
      ...seedWallp,
      price: '65.00',
    });
    renderBook();
    await screen.findByText('Usuwanie tapet (zdzieranie, utylizacja)');

    fireEvent.click(screen.getByLabelText('edit-price-item-item-1'));

    expect(screen.getByLabelText('inline-price-edit-item-1')).toBeInTheDocument();
    const priceInput = screen.getByLabelText('inline-price-input-item-1');
    expect(priceInput).toHaveValue('');

    fireEvent.change(priceInput, { target: { value: '65.00' } });
    fireEvent.click(screen.getByLabelText('inline-price-save-item-1'));

    await waitFor(() =>
      expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith('item-1', { price: '65.00' }),
    );
    await waitFor(() =>
      expect(screen.queryByLabelText('inline-price-edit-item-1')).not.toBeInTheDocument(),
    );
    expect(screen.getByText('65,00 zł')).toBeInTheDocument();
    expect(screen.getByText(/ m²/)).toBeInTheDocument();
    expect(screen.queryByText('Do ustalenia')).not.toBeInTheDocument();
  });

  it('lets the owner set a price on a null-priced seed row in RU', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedWallp],
      total: 1,
    });
    vi.mocked(priceItemsApi.updatePriceItem).mockResolvedValueOnce({
      ...seedWallp,
      price: '65.00',
    });
    renderBook();

    await screen.findByText('Снятие обоев (сдирание, утилизация)');
    expect(screen.getByText('Уточняется')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('edit-price-item-item-1'));
    const priceInput = screen.getByLabelText('inline-price-input-item-1');
    expect(priceInput).toHaveValue('');

    fireEvent.change(priceInput, { target: { value: '65.00' } });
    fireEvent.click(screen.getByLabelText('inline-price-save-item-1'));

    await waitFor(() =>
      expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith('item-1', { price: '65.00' }),
    );
    expect(await screen.findByText('65,00 zł')).toBeInTheDocument();
    expect(screen.queryByText('Уточняется')).not.toBeInTheDocument();
  });
});
