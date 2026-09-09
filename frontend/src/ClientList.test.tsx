import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ClientList } from './components/ClientList';
import { I18nProvider } from './hooks/useI18n';
import * as clientsApi from './api/clients';

vi.mock('./api/clients', () => ({
  fetchClients: vi.fn(),
  createClient: vi.fn(),
  archiveClient: vi.fn(),
  restoreClient: vi.fn(),
  fetchClient: vi.fn(),
  updateClient: vi.fn(),
}));

const mockClient = (overrides = {}) => ({
  id: '11111111-0000-0000-0000-000000000001',
  owner_user_id: 'aaaaaaaa-0000-0000-0000-000000000001',
  client_type: 'PRIVATE_PERSON' as const,
  first_name: 'Jan',
  last_name: 'Kowalski',
  company_name: null,
  phone: '500600700',
  email: null,
  nip: null,
  notes: null,
  is_archived: false,
  created_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-01T10:00:00Z',
  ...overrides,
});

function renderWithI18n(ui: React.ReactElement) {
  return render(<I18nProvider>{ui}</I18nProvider>);
}

describe('ClientList component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('shows empty state when no clients', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({ items: [], total: 0 });
    renderWithI18n(<ClientList />);
    await waitFor(() => {
      expect(screen.getByLabelText('no-clients')).toBeInTheDocument();
    });
  });

  it('renders a list of clients', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient()],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => {
      expect(screen.getByText('Jan Kowalski')).toBeInTheDocument();
    });
    expect(screen.getByText('500600700')).toBeInTheDocument();
  });

  it('shows archived badge for archived client', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ is_archived: true })],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => {
      expect(screen.getByText('Zarchiwizowany')).toBeInTheDocument();
    });
    expect(screen.getByLabelText(`restore-11111111-0000-0000-0000-000000000001`)).toBeInTheDocument();
  });

  it('opens add form when add button clicked', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({ items: [], total: 0 });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByLabelText('no-clients'));
    fireEvent.click(screen.getByLabelText('add-client'));
    expect(screen.getByLabelText('client-form')).toBeInTheDocument();
  });

  it('shows validation error for PRIVATE_PERSON without name', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({ items: [], total: 0 });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByLabelText('no-clients'));
    fireEvent.click(screen.getByLabelText('add-client'));
    fireEvent.submit(screen.getByLabelText('client-form'));
    await waitFor(() => {
      expect(screen.getByText('Podaj imię lub nazwisko')).toBeInTheDocument();
    });
  });
});
