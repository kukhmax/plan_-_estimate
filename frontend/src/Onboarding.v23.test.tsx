import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as onboardingApi from './api/onboarding';
import * as priceItemsApi from './api/priceItems';
import { ExampleBanner } from './components/ExampleBanner';
import { GettingStarted } from './components/GettingStarted';
import { PriceBook } from './components/PriceBook';
import { StarterPricesSheet } from './components/StarterPricesSheet';
import { I18nProvider } from './hooks/useI18n';
import type { PriceItem } from './types/priceItem';

vi.mock('./api/onboarding', () => ({ fetchStarterPrices: vi.fn(), fetchExample: vi.fn(), createExample: vi.fn(), deleteExample: vi.fn() }));
vi.mock('./api/priceItems', () => ({ fetchPriceItems: vi.fn(), updatePriceItem: vi.fn(), createPriceItem: vi.fn(), archivePriceItem: vi.fn(), restorePriceItem: vi.fn() }));
vi.mock('./api/marketEvidence', () => ({ fetchMarketEvidence: vi.fn().mockResolvedValue({ references: [] }) }));

const row = (code: string, over: Partial<PriceItem> = {}): PriceItem => ({
  id: `id-${code}`, code, name_key: null, display_name: `Pozycja ${code}`, category: 'SKIM_COAT', unit: 'M2', price: null, currency: 'PLN',
  price_scope: 'LABOR', quality_level: null, is_archived: false, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z', ...over,
});
const STARTER = ['A', 'B', 'C', 'D', 'E'].map((code) => row(code));

const wrap = (node: React.ReactNode) => render(<I18nProvider>{node}</I18nProvider>);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(onboardingApi.fetchStarterPrices).mockResolvedValue({ items: STARTER, total: 5 });
  vi.mocked(onboardingApi.fetchExample).mockResolvedValue({ project_id: null, client_id: null });
  vi.mocked(priceItemsApi.updatePriceItem).mockImplementation(async (id) => row(String(id).replace('id-', '')));
  vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
});

describe('the sheet of five prices (V2-3)', () => {
  it('lists the five rows from the server with an empty field each and a decimal keyboard', async () => {
    wrap(<StarterPricesSheet onClose={() => undefined} />);
    expect(await screen.findByRole('dialog', { name: '5 cen na start' })).toBeInTheDocument();
    for (const code of ['A', 'B', 'C', 'D', 'E']) {
      const input = await screen.findByLabelText(`starter-price-${code}`);
      expect(input).toHaveValue('');
      expect(input).toHaveAttribute('inputMode', 'decimal');
    }
    expect(screen.getByText('Pozycja A')).toBeInTheDocument();
  });

  it('saves only the filled rows, the comma is a decimal separator, and closes', async () => {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    wrap(<StarterPricesSheet onClose={onClose} onSaved={onSaved} />);
    fireEvent.change(await screen.findByLabelText('starter-price-C'), { target: { value: '48,5' } });
    fireEvent.change(screen.getByLabelText('starter-price-E'), { target: { value: '22' } });
    fireEvent.submit(screen.getByLabelText('starter-prices-form'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(priceItemsApi.updatePriceItem).toHaveBeenCalledTimes(2);
    expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith('id-C', { price: '48.5' });
    expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith('id-E', { price: '22' });
    expect(onSaved).toHaveBeenCalledWith(2);
  });

  it('refuses an empty form and a wrong number without sending anything', async () => {
    const onClose = vi.fn();
    wrap(<StarterPricesSheet onClose={onClose} />);
    await screen.findByLabelText('starter-price-A');
    fireEvent.submit(screen.getByLabelText('starter-prices-form'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Wpisz co najmniej jedną cenę.');
    fireEvent.change(screen.getByLabelText('starter-price-A'), { target: { value: 'abc' } });
    fireEvent.submit(screen.getByLabelText('starter-prices-form'));
    expect(await screen.findByText('Podaj cenę jako liczbę, np. 45 lub 45,50.')).toBeInTheDocument();
    expect(priceItemsApi.updatePriceItem).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes with Escape and keeps a failed save open with the error', async () => {
    const onClose = vi.fn();
    wrap(<StarterPricesSheet onClose={onClose} />);
    fireEvent.change(await screen.findByLabelText('starter-price-B'), { target: { value: '10' } });
    vi.mocked(priceItemsApi.updatePriceItem).mockRejectedValueOnce(new Error('boom'));
    fireEvent.submit(screen.getByLabelText('starter-prices-form'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się zapisać pozycji.');
    expect(onClose).not.toHaveBeenCalled();
    act(() => { fireEvent.keyDown(window, { key: 'Escape' }); });
    expect(onClose).toHaveBeenCalled();
  });
});

describe('"Od czego zacząć": the example object (V2-3)', () => {
  const progress = { hasClients: false, hasProjects: false, hasPrices: false, hasRooms: false };
  const props = { progress, onAddClient: () => undefined, onOpenPricebook: () => undefined, onOpenProjects: () => undefined };

  it('makes the example and opens it', async () => {
    vi.mocked(onboardingApi.createExample).mockResolvedValue({ project_id: 'p-example', client_id: 'c-example', created: true });
    const open = vi.fn();
    wrap(<GettingStarted {...props} onOpenProject={open} />);
    fireEvent.click(screen.getByLabelText('start-try-example'));
    await waitFor(() => expect(open).toHaveBeenCalledWith('p-example'));
    expect(onboardingApi.createExample).toHaveBeenCalledTimes(1);
  });

  it('says so when the example could not be made, and the button works again', async () => {
    vi.mocked(onboardingApi.createExample).mockRejectedValue(new Error('x'));
    wrap(<GettingStarted {...props} onOpenProject={() => undefined} />);
    fireEvent.click(screen.getByLabelText('start-try-example'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się utworzyć przykładu.');
    expect(screen.getByLabelText('start-try-example')).not.toBeDisabled();
  });

  it('has no example button where the screen cannot open an object', () => {
    wrap(<GettingStarted {...props} />);
    expect(screen.queryByLabelText('start-try-example')).toBeNull();
  });

  it('ticks the price step after the five prices were saved', async () => {
    wrap(<GettingStarted {...props} />);
    fireEvent.click(screen.getByLabelText('start-step-prices'));
    fireEvent.change(await screen.findByLabelText('starter-price-A'), { target: { value: '30' } });
    fireEvent.submit(screen.getByLabelText('starter-prices-form'));
    await waitFor(() => expect(screen.getByLabelText('start-step-prices')).toHaveAttribute('data-done', 'true'));
  });
});

describe('the banner of the example object (V2-3)', () => {
  it('shows nothing on an ordinary object', async () => {
    vi.mocked(onboardingApi.fetchExample).mockResolvedValue({ project_id: 'other', client_id: 'c' });
    wrap(<ExampleBanner projectId="mine" onRemoved={() => undefined} />);
    await waitFor(() => expect(onboardingApi.fetchExample).toHaveBeenCalled());
    expect(screen.queryByLabelText('example-banner')).toBeNull();
  });

  it('shows the banner on the example, offers the five prices while they are empty, deletes after one confirmation', async () => {
    vi.mocked(onboardingApi.fetchExample).mockResolvedValue({ project_id: 'mine', client_id: 'c' });
    vi.mocked(onboardingApi.deleteExample).mockResolvedValue({ removed_project: true, removed_client: true });
    const removed = vi.fn();
    wrap(<ExampleBanner projectId="mine" onRemoved={removed} />);
    expect(await screen.findByLabelText('example-banner')).toHaveTextContent('To jest przykładowy obiekt');
    expect(await screen.findByLabelText('example-set-prices')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('example-remove'));
    expect(onboardingApi.deleteExample).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('example-remove-confirm'));
    await waitFor(() => expect(removed).toHaveBeenCalled());
    expect(onboardingApi.deleteExample).toHaveBeenCalledTimes(1);
  });

  it('does not offer the prices once they are set, and a cancelled deletion deletes nothing', async () => {
    vi.mocked(onboardingApi.fetchExample).mockResolvedValue({ project_id: 'mine', client_id: 'c' });
    vi.mocked(onboardingApi.fetchStarterPrices).mockResolvedValue({ items: STARTER.map((item) => ({ ...item, price: '10.00' })), total: 5 });
    wrap(<ExampleBanner projectId="mine" onRemoved={() => undefined} />);
    await screen.findByLabelText('example-banner');
    await waitFor(() => expect(onboardingApi.fetchStarterPrices).toHaveBeenCalled());
    expect(screen.queryByLabelText('example-set-prices')).toBeNull();
    fireEvent.click(screen.getByLabelText('example-remove'));
    fireEvent.click(screen.getByLabelText('example-remove-cancel'));
    expect(onboardingApi.deleteExample).not.toHaveBeenCalled();
    expect(screen.getByLabelText('example-remove')).toBeInTheDocument();
  });

  it('keeps the object open and says so when the deletion fails', async () => {
    vi.mocked(onboardingApi.fetchExample).mockResolvedValue({ project_id: 'mine', client_id: 'c' });
    vi.mocked(onboardingApi.deleteExample).mockRejectedValue(new Error('x'));
    const removed = vi.fn();
    wrap(<ExampleBanner projectId="mine" onRemoved={removed} />);
    fireEvent.click(await screen.findByLabelText('example-remove'));
    fireEvent.click(screen.getByLabelText('example-remove-confirm'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się usunąć przykładu.');
    expect(removed).not.toHaveBeenCalled();
  });

  it('stays silent when the status cannot be read', async () => {
    vi.mocked(onboardingApi.fetchExample).mockRejectedValue(new Error('x'));
    wrap(<ExampleBanner projectId="mine" onRemoved={() => undefined} />);
    await waitFor(() => expect(onboardingApi.fetchExample).toHaveBeenCalled());
    expect(screen.queryByLabelText('example-banner')).toBeNull();
  });
});

describe('the hint in the price book (V2-3)', () => {
  it('is shown while no row has a price and not once there is one', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [row('X'), row('Y')], total: 2 });
    wrap(<PriceBook />);
    fireEvent.click(await screen.findByLabelText('pricebook-maintab-items'));
    expect(await screen.findByLabelText('starter-prices-hint')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('starter-prices-open'));
    expect(await screen.findByLabelText('starter-prices-form')).toBeInTheDocument();
  });

  it('is not shown when a price exists', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [row('X', { price: '12.00' }), row('Y')], total: 2 });
    wrap(<PriceBook />);
    fireEvent.click(await screen.findByLabelText('pricebook-maintab-items'));
    await screen.findByText('Pozycja X');
    expect(screen.queryByLabelText('starter-prices-hint')).toBeNull();
  });
});
