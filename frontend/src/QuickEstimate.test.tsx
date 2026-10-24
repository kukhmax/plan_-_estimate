import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as clientsApi from './api/clients';
import * as priceItemsApi from './api/priceItems';
import * as quickApi from './api/quickEstimate';
import { QuickEstimate } from './components/QuickEstimate';
import { I18nProvider } from './hooks/useI18n';
import type { PriceItem } from './types/priceItem';

vi.mock('./api/clients', () => ({ fetchClients: vi.fn() }));
vi.mock('./api/priceItems', () => ({ updatePriceItem: vi.fn() }));
vi.mock('./api/onboarding', () => ({ fetchStarterPrices: vi.fn() }));
vi.mock('./api/marketEvidence', () => ({ fetchMarketEvidence: vi.fn().mockResolvedValue({ references: [] }) }));
vi.mock('./api/quickEstimate', async () => {
  const actual = await vi.importActual<typeof import('./api/quickEstimate')>('./api/quickEstimate');
  return { ...actual, fetchQuickEstimateOptions: vi.fn(), createQuickEstimate: vi.fn() };
});

const row = (code: string, price: string | null = null): PriceItem => ({
  id: `id-${code}`, code, name_key: null, display_name: `Praca ${code}`, category: 'SKIM_COAT', unit: 'M2', price, currency: 'PLN',
  price_scope: 'LABOR', quality_level: null, is_archived: false, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
});
const CODES = ['PREP', 'PRIM', 'SKIM', 'SAND', 'PAINT'];
const options = (prices: Record<string, string | null> = {}): quickApi.QuickEstimateOptions => ({
  works: CODES.map((code) => ({ code, ceiling_code: code === 'PAINT' ? 'CEIL' : code, default_on: code !== 'PREP' })),
  items: [...CODES, 'CEIL'].map((code) => row(code, prices[code] ?? null)),
  substrates: ['GYPSUM_PLASTER', 'CEMENT_LIME_PLASTER', 'CONCRETE', 'GYPSUM_BOARD'],
  default_substrate: 'GYPSUM_PLASTER',
  default_quality: 'S2',
});
const client = (id: string, first: string) => ({ id, client_type: 'PRIVATE_PERSON' as const, first_name: first, last_name: 'Kowalski', company_name: null });

const onDone = vi.fn();
const onClose = vi.fn();
const view = () => render(<I18nProvider><QuickEstimate onDone={onDone} onClose={onClose} /></I18nProvider>);
const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

async function fillRoom(index = 0, name = 'Salon') {
  type(`quick-room-name-${index}`, name);
  type(`quick-room-length-${index}`, '520');
  type(`quick-room-width-${index}`, '360');
  type(`quick-room-height-${index}`, '260');
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(quickApi.fetchQuickEstimateOptions).mockResolvedValue(options());
  vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [], total: 0 } as never);
  vi.mocked(quickApi.createQuickEstimate).mockResolvedValue({ project_id: 'p1', client_id: 'c1', estimate_id: 'e1', rooms: 1, lines: 16, unpriced_lines: 0, total: '100.00' });
  vi.mocked(priceItemsApi.updatePriceItem).mockResolvedValue(row('X', '1.00'));
});

describe('the quick estimate screen (V2-4)', () => {
  it('offers the works in the order of the server with the defaults ticked and the ceiling off', async () => {
    view();
    await screen.findByLabelText('quick-work-PRIM');
    expect(screen.getByLabelText('quick-work-PREP')).not.toBeChecked();
    for (const code of ['PRIM', 'SKIM', 'SAND', 'PAINT']) expect(screen.getByLabelText(`quick-work-${code}`)).toBeChecked();
    expect(screen.getByLabelText('quick-ceiling')).not.toBeChecked();
    expect(within(screen.getByLabelText('quick-works')).getAllByText('Do ustalenia')).toHaveLength(5); // no work has a price yet
    expect(screen.getByText(/Bez odjęcia otworów/)).toBeInTheDocument();
  });

  it('sends the sizes in metres, the ticked works in the order of the server, and opens the object', async () => {
    view();
    await screen.findByLabelText('quick-work-PRIM');
    type('quick-client-name', 'Jan Kowalski');
    type('quick-client-phone', '600 100 200');
    type('quick-address', 'ul. Długa 5/7');
    type('quick-city', 'Kraków');
    await fillRoom();
    fireEvent.click(screen.getByLabelText('quick-work-PREP'));
    fireEvent.click(screen.getByLabelText('quick-work-SAND'));
    fireEvent.submit(screen.getByLabelText('quick-estimate-form'));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith('p1'));
    expect(quickApi.createQuickEstimate).toHaveBeenCalledWith({
      client_name: 'Jan Kowalski', client_phone: '600 100 200', address: 'ul. Długa 5/7', city: 'Kraków',
      rooms: [{ name: 'Salon', length: '5.2', width: '3.6', height: '2.6' }],
      work_codes: ['PREP', 'PRIM', 'SKIM', 'PAINT'], include_ceiling: false, substrate: 'GYPSUM_PLASTER', quality_target: 'S2',
    });
  });

  it('uses an existing client when there are some, and the ceiling switch goes with the request', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [client('c9', 'Anna')], total: 1 } as never);
    view();
    const select = await screen.findByLabelText('quick-client-select');
    fireEvent.change(select, { target: { value: 'c9' } });
    type('quick-address', 'ul. Krótka 1');
    type('quick-city', 'Kraków');
    await fillRoom();
    fireEvent.click(screen.getByLabelText('quick-ceiling'));
    fireEvent.submit(screen.getByLabelText('quick-estimate-form'));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const sent = vi.mocked(quickApi.createQuickEstimate).mock.calls[0][0];
    expect(sent.client_id).toBe('c9');
    expect(sent.client_name).toBeUndefined();
    expect(sent.include_ceiling).toBe(true);
  });

  it('a drywall substrate switches to the Q classes and sends one of them', async () => {
    view();
    await screen.findByLabelText('quick-substrate');
    fireEvent.change(screen.getByLabelText('quick-substrate'), { target: { value: 'GYPSUM_BOARD' } });
    expect(screen.getByLabelText('quick-quality')).toHaveValue('Q2');
    expect(within(screen.getByLabelText('quick-quality')).getAllByRole('option').map((o) => (o as HTMLOptionElement).value)).toEqual(['Q1', 'Q2', 'Q3', 'Q4']);
    type('quick-client-name', 'Jan');
    type('quick-address', 'ul. A 1');
    type('quick-city', 'Kraków');
    await fillRoom();
    fireEvent.submit(screen.getByLabelText('quick-estimate-form'));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(vi.mocked(quickApi.createQuickEstimate).mock.calls[0][0]).toMatchObject({ substrate: 'GYPSUM_BOARD', quality_target: 'Q2' });
  });

  it('a new room takes the height of the previous one, a room can be removed while another stays', async () => {
    view();
    await screen.findByLabelText('quick-room-add');
    expect(screen.queryByLabelText('quick-room-remove-0')).toBeNull();
    await fillRoom();
    fireEvent.click(screen.getByLabelText('quick-room-add'));
    expect(screen.getByLabelText('quick-room-height-1')).toHaveValue('260');
    expect(screen.getByLabelText('quick-room-length-1')).toHaveValue('');
    fireEvent.click(screen.getByLabelText('quick-room-remove-0'));
    expect(screen.queryByLabelText('quick-room-1')).toBeNull();
    expect(screen.getByLabelText('quick-room-0')).toBeInTheDocument();
  });

  it('a name chip fills the name of the room', async () => {
    view();
    await screen.findByLabelText('quick-room-add');
    fireEvent.click(within(screen.getByLabelText('quick-room-0')).getByRole('button', { name: 'Łazienka' }));
    expect(screen.getByLabelText('quick-room-name-0')).toHaveValue('Łazienka');
  });

  it.each([
    ['no client', async () => { type('quick-address', 'a'); type('quick-city', 'b'); await fillRoom(); }, 'Wybierz klienta albo wpisz jego nazwę.'],
    ['no address', async () => { type('quick-client-name', 'Jan'); await fillRoom(); }, 'Wpisz adres i miasto.'],
    ['a room without a size', async () => { type('quick-client-name', 'Jan'); type('quick-address', 'a'); type('quick-city', 'b'); type('quick-room-name-0', 'Salon'); }, 'Każde pomieszczenie potrzebuje nazwy i trzech wymiarów.'],
  ])('says what is missing (%s) and sends nothing', async (_name, fill, message) => {
    view();
    await screen.findByLabelText('quick-work-PRIM');
    type('quick-room-name-0', '');
    await fill();
    fireEvent.submit(screen.getByLabelText('quick-estimate-form'));
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(quickApi.createQuickEstimate).not.toHaveBeenCalled();
  });

  it('asks for at least one work', async () => {
    view();
    await screen.findByLabelText('quick-work-PRIM');
    type('quick-client-name', 'Jan'); type('quick-address', 'a'); type('quick-city', 'b');
    await fillRoom();
    for (const code of ['PRIM', 'SKIM', 'SAND', 'PAINT']) fireEvent.click(screen.getByLabelText(`quick-work-${code}`));
    fireEvent.submit(screen.getByLabelText('quick-estimate-form'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Zaznacz co najmniej jedną pracę.');
  });

  it('names a server refusal it knows and keeps the form for another try on any other failure', async () => {
    view();
    await screen.findByLabelText('quick-work-PRIM');
    type('quick-client-name', 'Jan'); type('quick-address', 'a'); type('quick-city', 'b');
    await fillRoom();
    vi.mocked(quickApi.createQuickEstimate).mockRejectedValueOnce(new quickApi.QuickEstimateRequestError('QUICK_WORK_UNAVAILABLE', 422));
    fireEvent.submit(screen.getByLabelText('quick-estimate-form'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Jedna z prac jest zarchiwizowana w cenniku');
    vi.mocked(quickApi.createQuickEstimate).mockRejectedValueOnce(new Error('boom'));
    fireEvent.submit(screen.getByLabelText('quick-estimate-form'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Nie udało się utworzyć wyceny. Nic nie zostało zapisane.'));
    expect(screen.getByLabelText('quick-submit')).not.toBeDisabled();
    expect(onDone).not.toHaveBeenCalled();
  });

  it('offers the prices of the chosen works that are not set, and reads the screen again after they were saved', async () => {
    view();
    fireEvent.click(await screen.findByLabelText('quick-set-prices'));
    const sheet = await screen.findByLabelText('starter-prices-form');
    expect(within(sheet).getAllByLabelText(/^starter-price-(?!row)/)).toHaveLength(4); // PRIM, SKIM, SAND, PAINT (the ceiling row only with the ceiling)
    fireEvent.change(within(sheet).getByLabelText('starter-price-SKIM'), { target: { value: '35' } });
    vi.mocked(quickApi.fetchQuickEstimateOptions).mockResolvedValue(options({ PRIM: '7.00', SKIM: '35.00', SAND: '10.00', PAINT: '10.00' }));
    fireEvent.submit(sheet);
    await waitFor(() => expect(quickApi.fetchQuickEstimateOptions).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByLabelText('quick-set-prices')).toBeNull());
    expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith('id-SKIM', { price: '35' });
  });

  it('saving the prices in the sheet does not submit the estimate behind it', async () => {
    view();
    type('quick-client-name', 'Jan'); type('quick-address', 'a'); type('quick-city', 'b');
    await fillRoom();
    fireEvent.click(await screen.findByLabelText('quick-set-prices'));
    const sheet = await screen.findByLabelText('starter-prices-form');
    fireEvent.change(within(sheet).getByLabelText('starter-price-SKIM'), { target: { value: '35' } });
    fireEvent.submit(sheet);
    await waitFor(() => expect(priceItemsApi.updatePriceItem).toHaveBeenCalled());
    expect(quickApi.createQuickEstimate).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
  });

  it('the ceiling adds its own painting row to the prices that are asked for', async () => {
    view();
    await screen.findByLabelText('quick-ceiling');
    fireEvent.click(screen.getByLabelText('quick-ceiling'));
    fireEvent.click(screen.getByLabelText('quick-set-prices'));
    const sheet = await screen.findByLabelText('starter-prices-form');
    expect(within(sheet).getAllByLabelText(/^starter-price-(?!row)/)).toHaveLength(5);
    expect(within(sheet).getByLabelText('starter-price-CEIL')).toBeInTheDocument();
  });

  it('says so when the settings cannot be read, and the cancel button leaves', async () => {
    vi.mocked(quickApi.fetchQuickEstimateOptions).mockRejectedValue(new Error('x'));
    view();
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać ustawień szybkiej wyceny.');
    expect(screen.getByLabelText('quick-submit')).toBeDisabled();
    fireEvent.click(screen.getByLabelText('quick-cancel'));
    expect(onClose).toHaveBeenCalled();
  });
});
