import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ClientList } from './components/ClientList';
import { GettingStarted } from './components/GettingStarted';
import { I18nProvider } from './hooks/useI18n';
import * as clientsApi from './api/clients';
import * as projectsApi from './api/projects';
import * as roomsApi from './api/rooms';
import * as priceItemsApi from './api/priceItems';
import * as onboardingApi from './api/onboarding';

vi.mock('./api/clients', () => ({
  fetchClients: vi.fn(),
  createClient: vi.fn(),
  archiveClient: vi.fn(),
  restoreClient: vi.fn(),
  fetchClient: vi.fn(),
  updateClient: vi.fn(),
}));
vi.mock('./api/projects', () => ({ fetchProjects: vi.fn() }));
vi.mock('./api/rooms', () => ({ fetchRooms: vi.fn() }));
vi.mock('./api/priceItems', () => ({ fetchPriceItems: vi.fn(), updatePriceItem: vi.fn() }));
vi.mock('./api/onboarding', () => ({ fetchStarterPrices: vi.fn(), createExample: vi.fn(), fetchExample: vi.fn(), deleteExample: vi.fn() }));

const client = (id: string, first = 'Jan') => ({
  id, owner_user_id: 'o', client_type: 'PRIVATE_PERSON' as const, first_name: first, last_name: 'Kowalski', company_name: null, phone: null,
  email: null, nip: null, street: null, postal_code: null, city: null, telegram_username: null, notes: null, is_archived: false,
  created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z',
});

const project = { id: 'p1', name: 'Dom' };

function renderList(props: Partial<React.ComponentProps<typeof ClientList>> = {}) {
  return render(<I18nProvider><ClientList {...props} /></I18nProvider>);
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(onboardingApi.fetchStarterPrices).mockResolvedValue({ items: [], total: 0 });
});

describe('"Od czego zacząć" on the empty list of clients (usability U-3)', () => {
  it('shows the three steps to a new contractor, the first one as the main button', async () => {
    renderList();
    const card = await screen.findByLabelText('getting-started');
    expect(card).toHaveTextContent('Od czego zacząć');
    expect(screen.getByLabelText('start-step-client')).toHaveTextContent('1. Dodaj klienta i obiekt');
    expect(screen.getByLabelText('start-step-prices')).toHaveTextContent('2. Ustaw swoje ceny');
    expect(screen.getByLabelText('start-step-room')).toHaveTextContent('3. Zmierz pierwsze pomieszczenie');
    expect(screen.getByLabelText('start-step-client').className).toContain('bg-blue-600');
    await waitFor(() => expect(priceItemsApi.fetchPriceItems).toHaveBeenCalled());
    for (const step of ['client', 'prices', 'room']) expect(screen.getByLabelText(`start-step-${step}`)).toHaveAttribute('data-done', 'false');
  });

  it('ticks the steps that are already done, read from the existing lists', async () => {
    vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [project], total: 1 } as never);
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [{ id: 'r1' }], total: 1 } as never);
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [{ id: 'i1', price: '35.00' }], total: 1 } as never);
    renderList();
    await waitFor(() => expect(screen.getByLabelText('start-step-prices')).toHaveAttribute('data-done', 'true'));
    await waitFor(() => expect(screen.getByLabelText('start-step-room')).toHaveAttribute('data-done', 'true'));
    expect(screen.getByLabelText('start-step-prices')).toHaveTextContent('gotowe');
    // no client yet: the first step stays open even though an object exists
    expect(screen.getByLabelText('start-step-client')).toHaveAttribute('data-done', 'false');
    expect(roomsApi.fetchRooms).toHaveBeenCalledWith('p1');
  });

  it('a price without a value does not count as "my prices"', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [{ id: 'i1', price: null }], total: 1 } as never);
    renderList();
    await waitFor(() => expect(priceItemsApi.fetchPriceItems).toHaveBeenCalled());
    expect(screen.getByLabelText('start-step-prices')).toHaveAttribute('data-done', 'false');
  });

  it('a list that fails to load leaves its step open and does not block the card', async () => {
    vi.mocked(projectsApi.fetchProjects).mockRejectedValue(new Error('down'));
    vi.mocked(priceItemsApi.fetchPriceItems).mockRejectedValue(new Error('down'));
    renderList();
    expect(await screen.findByLabelText('getting-started')).toBeInTheDocument();
    await waitFor(() => expect(projectsApi.fetchProjects).toHaveBeenCalled());
    expect(screen.getByLabelText('start-step-room')).toHaveAttribute('data-done', 'false');
  });

  it('the second step opens the sheet of five prices (with a way to the whole price book), the third the objects', async () => {
    const pricebook = vi.fn();
    const projects = vi.fn();
    renderList({ onOpenPricebook: pricebook, onOpenProjects: projects });
    fireEvent.click(await screen.findByLabelText('start-step-prices'));
    expect(await screen.findByLabelText('starter-prices-form')).toBeInTheDocument();
    expect(pricebook).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('starter-prices-all'));
    expect(screen.queryByLabelText('starter-prices-form')).toBeNull();
    fireEvent.click(screen.getByLabelText('start-step-room'));
    expect(pricebook).toHaveBeenCalledTimes(1);
    expect(projects).toHaveBeenCalledTimes(1);
  });

  it('the first step opens the form of a client and, after saving, hands his id on to the form of his object', async () => {
    vi.mocked(clientsApi.createClient).mockResolvedValue(client('c-new', 'Anna') as never);
    const startObject = vi.fn();
    renderList({ onStartObject: startObject });
    fireEvent.click(await screen.findByLabelText('start-step-client'));
    expect(screen.getByLabelText('client-form')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('first-name'), { target: { value: 'Anna' } });
    fireEvent.submit(screen.getByLabelText('client-form'));
    await waitFor(() => expect(startObject).toHaveBeenCalledWith('c-new'));
    expect(clientsApi.createClient).toHaveBeenCalledTimes(1);
  });

  it('the ordinary "Dodaj klienta" button does not lead on to an object', async () => {
    vi.mocked(clientsApi.createClient).mockResolvedValue(client('c-new', 'Anna') as never);
    const startObject = vi.fn();
    renderList({ onStartObject: startObject });
    fireEvent.click(await screen.findByLabelText('add-client'));
    fireEvent.change(screen.getByLabelText('first-name'), { target: { value: 'Anna' } });
    fireEvent.submit(screen.getByLabelText('client-form'));
    await waitFor(() => expect(clientsApi.createClient).toHaveBeenCalled());
    expect(startObject).not.toHaveBeenCalled();
  });

  it('opens the form of a client by itself when another screen asks (the token changes)', async () => {
    const { rerender } = renderList({ autoCreateToken: 0 });
    await screen.findByLabelText('getting-started');
    expect(screen.queryByLabelText('client-form')).toBeNull();
    rerender(<I18nProvider><ClientList autoCreateToken={1} /></I18nProvider>);
    expect(await screen.findByLabelText('client-form')).toBeInTheDocument();
  });

  it('a search with no result says so instead of showing the card of a new contractor', async () => {
    renderList();
    await screen.findByLabelText('getting-started');
    fireEvent.change(screen.getByLabelText('search-clients'), { target: { value: 'zzz' } });
    await waitFor(() => expect(screen.queryByLabelText('getting-started')).toBeNull());
    expect(screen.getByLabelText('no-clients')).toHaveTextContent('Brak klientów');
  });

  it('the card is not shown when there are clients, and the number under the list is named', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [client('c1'), client('c2', 'Piotr')], total: 2 });
    renderList();
    expect(await screen.findByLabelText('clients-list')).toBeInTheDocument();
    expect(screen.queryByLabelText('getting-started')).toBeNull();
    expect(screen.getByLabelText('clients-count')).toHaveTextContent('Klienci: 2');
  });

  it('speaks Russian, with the number named without a case form', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [client('c1')], total: 1 });
    const { unmount } = renderList();
    expect(await screen.findByLabelText('clients-count')).toHaveTextContent('Клиентов: 1');
    unmount();
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [], total: 0 });
    renderList();
    expect(await screen.findByLabelText('getting-started')).toHaveTextContent('С чего начать');
    expect(screen.getByLabelText('start-step-client')).toHaveTextContent('1. Добавьте клиента и объект');
    expect(screen.getByLabelText('start-step-room')).toHaveTextContent('3. Замерь первое помещение');
  });

  it('the card alone renders its three steps from the progress it is given', () => {
    render(
      <I18nProvider>
        <GettingStarted
          progress={{ hasClients: true, hasProjects: true, hasPrices: true, hasRooms: false }}
          onAddClient={() => {}}
          onOpenPricebook={() => {}}
          onOpenProjects={() => {}}
        />
      </I18nProvider>,
    );
    expect(screen.getByLabelText('start-step-client')).toHaveAttribute('data-done', 'true');
    expect(screen.getByLabelText('start-step-prices')).toHaveAttribute('data-done', 'true');
    expect(screen.getByLabelText('start-step-room')).toHaveAttribute('data-done', 'false');
    // once the first step is done it is no longer the blue main button
    expect(screen.getByLabelText('start-step-client').className).not.toContain('bg-blue-600');
  });
});
