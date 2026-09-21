import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as priceItemsApi from '../api/priceItems';
import { I18nProvider } from '../hooks/useI18n';
import { PriceItem } from '../types/priceItem';
import { RecommendationPriceItemPicker } from './RecommendationPriceItemPicker';

vi.mock('../api/priceItems', () => ({
  fetchPriceItems: vi.fn(),
}));

function priceItem(overrides: Partial<PriceItem> = {}): PriceItem {
  return {
    id: 'price-1',
    code: 'PAINT_M2',
    name_key: null,
    display_name: 'Malowanie ścian',
    category: 'PAINTING',
    unit: 'M2',
    price: '18.00',
    currency: 'PLN',
    price_scope: 'LABOR',
    quality_level: null,
    is_archived: false,
    created_at: '2026-09-20T08:00:00Z',
    updated_at: '2026-09-20T08:00:00Z',
    ...overrides,
  };
}

function renderPicker(props: { disabled?: boolean; onConfirm?: (item: PriceItem) => void; onCancel?: () => void } = {}) {
  const onConfirm = props.onConfirm ?? vi.fn();
  const onCancel = props.onCancel ?? vi.fn();
  render(
    <I18nProvider>
      <RecommendationPriceItemPicker
        disabled={props.disabled ?? false}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    </I18nProvider>,
  );
  return { onConfirm, onCancel };
}

describe('RecommendationPriceItemPicker (Stage 11D.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
      items: [priceItem()],
      total: 1,
    });
  });

  it('loads active PriceItems on mount', async () => {
    renderPicker();
    await waitFor(() =>
      expect(priceItemsApi.fetchPriceItems).toHaveBeenCalledWith({ archived: 'active' }),
    );
    expect(await screen.findByText('Malowanie ścian')).toBeInTheDocument();
  });

  it('filters the list by search text', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
      items: [
        priceItem(),
        priceItem({ id: 'price-2', display_name: 'Gładź gipsowa', category: 'SKIM_COAT' }),
      ],
      total: 2,
    });
    renderPicker();
    await screen.findByText('Gładź gipsowa');
    fireEvent.change(screen.getByLabelText('Szukaj w cenniku'), {
      target: { value: 'malow' },
    });
    expect(screen.getByText('Malowanie ścian')).toBeInTheDocument();
    expect(screen.queryByText('Gładź gipsowa')).not.toBeInTheDocument();
  });

  it('excludes REVEAL-category items entirely', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
      items: [priceItem(), priceItem({ id: 'reveal-1', display_name: 'Ościeże', category: 'REVEAL' })],
      total: 2,
    });
    renderPicker();
    await screen.findByText('Malowanie ścian');
    expect(screen.queryByText('Ościeże')).not.toBeInTheDocument();
  });

  it('includes a NULL-price item and shows "Do ustalenia"', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
      items: [priceItem({ price: null })],
      total: 1,
    });
    renderPicker();
    expect(await screen.findByText(/Do ustalenia/)).toBeInTheDocument();
  });

  it('includes an explicit zero-price item, rendered distinctly from NULL', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
      items: [priceItem({ price: '0.00' })],
      total: 1,
    });
    renderPicker();
    expect(await screen.findByText(/0,00 zł/)).toBeInTheDocument();
  });

  it('highlights the selected item and requires explicit confirmation before calling onConfirm', async () => {
    const { onConfirm } = renderPicker();
    const item = await screen.findByLabelText(/Wybierz pozycję Malowanie ścian/);
    expect(screen.getByLabelText('Potwierdź wybór')).toBeDisabled();
    fireEvent.click(item);
    expect(item).toHaveAttribute('aria-pressed', 'true');
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('Potwierdź wybór'));
    expect(onConfirm).toHaveBeenCalledWith(priceItem());
  });

  it('disables selection and confirmation while a submission is pending', async () => {
    renderPicker({ disabled: true });
    const item = await screen.findByLabelText(/Wybierz pozycję Malowanie ścian/);
    expect(item).toBeDisabled();
    expect(screen.getByLabelText('Potwierdź wybór')).toBeDisabled();
  });

  it('calls onCancel without ever calling onConfirm', async () => {
    const { onConfirm, onCancel } = renderPicker();
    fireEvent.click(await screen.findByLabelText('Anuluj'));
    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('uses ~44px touch targets for its interactive controls (MOBILE)', async () => {
    renderPicker();
    const item = await screen.findByLabelText(/Wybierz pozycję Malowanie ścian/);
    expect(item).toHaveClass('min-h-11');
    expect(screen.getByLabelText('Potwierdź wybór')).toHaveClass('min-h-11');
    expect(screen.getByLabelText('Szukaj w cenniku')).toHaveClass('min-h-11');
  });
});
