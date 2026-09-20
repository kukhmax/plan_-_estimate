import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ClientList } from './components/ClientList';
import { I18nProvider } from './hooks/useI18n';
import * as clientsApi from './api/clients';
import * as clipboardUtil from './utils/clipboard';

vi.mock('./api/clients', () => ({
  fetchClients: vi.fn(),
  createClient: vi.fn(),
  archiveClient: vi.fn(),
  restoreClient: vi.fn(),
  fetchClient: vi.fn(),
  updateClient: vi.fn(),
}));

vi.mock('./utils/clipboard', () => ({
  copyTextToClipboard: vi.fn(),
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
  telegram_username: null,
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

  it('renders the section title with the theme-aware text color, not a hardcoded dark slate class (Stage 10H.1)', async () => {
    // Regression: a hardcoded `text-slate-900` on page-level (non-card) text
    // never adapts to Telegram's dark theme, where the page background is
    // itself dark — the heading became invisible dark-on-dark.
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({ items: [], total: 0 });
    renderWithI18n(<ClientList />);
    const heading = await screen.findByText('Klienci');
    expect(heading.className).toContain('text-[var(--tg-theme-text-color)]');
    expect(heading.className).not.toContain('text-slate-900');
  });
});

// ---------------------------------------------------------------------------
// Stage 10G.4 — Telegram contact field + client card display + edit
// ---------------------------------------------------------------------------

describe('ClientList — Telegram contact field', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('the create form contains the Telegram field', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({ items: [], total: 0 });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByLabelText('no-clients'));
    fireEvent.click(screen.getByLabelText('add-client'));
    expect(screen.getByLabelText('telegram-username')).toBeInTheDocument();
  });

  it('sends the Telegram value on create', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({ items: [], total: 0 });
    vi.mocked(clientsApi.createClient).mockResolvedValueOnce(mockClient());
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByLabelText('no-clients'));
    fireEvent.click(screen.getByLabelText('add-client'));

    fireEvent.change(screen.getByLabelText('first-name'), { target: { value: 'Wasyl' } });
    fireEvent.change(screen.getByLabelText('telegram-username'), { target: { value: '@vasiya' } });
    fireEvent.submit(screen.getByLabelText('client-form'));

    await waitFor(() =>
      expect(clientsApi.createClient).toHaveBeenCalledWith(
        expect.objectContaining({ telegram_username: '@vasiya' }),
      ),
    );
  });

  it('the edit form pre-fills the Telegram field', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ telegram_username: '@vasiya' })],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    fireEvent.click(screen.getByLabelText('edit-11111111-0000-0000-0000-000000000001'));

    expect(screen.getByLabelText('telegram-username')).toHaveValue('@vasiya');
  });

  it('editing can update the Telegram field', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({
      items: [mockClient({ telegram_username: '@vasiya' })],
      total: 1,
    });
    vi.mocked(clientsApi.updateClient).mockResolvedValueOnce(mockClient({ telegram_username: '@vasiya_new' }));
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    fireEvent.click(screen.getByLabelText('edit-11111111-0000-0000-0000-000000000001'));

    fireEvent.change(screen.getByLabelText('telegram-username'), { target: { value: '@vasiya_new' } });
    fireEvent.submit(screen.getByLabelText('client-form'));

    await waitFor(() =>
      expect(clientsApi.updateClient).toHaveBeenCalledWith(
        '11111111-0000-0000-0000-000000000001',
        expect.objectContaining({ telegram_username: '@vasiya_new' }),
      ),
    );
  });

  it('editing can clear the Telegram field back to NULL', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({
      items: [mockClient({ telegram_username: '@vasiya' })],
      total: 1,
    });
    vi.mocked(clientsApi.updateClient).mockResolvedValueOnce(mockClient({ telegram_username: null }));
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    fireEvent.click(screen.getByLabelText('edit-11111111-0000-0000-0000-000000000001'));

    fireEvent.change(screen.getByLabelText('telegram-username'), { target: { value: '' } });
    fireEvent.submit(screen.getByLabelText('client-form'));

    await waitFor(() =>
      expect(clientsApi.updateClient).toHaveBeenCalledWith(
        '11111111-0000-0000-0000-000000000001',
        expect.objectContaining({ telegram_username: null }),
      ),
    );
  });

  it('editing preserves NIP/phone/email unrelated to the Telegram change', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({
      items: [mockClient({ nip: '1234567890', phone: '500600700', email: 'jan@example.pl', telegram_username: '@jan' })],
      total: 1,
    });
    vi.mocked(clientsApi.updateClient).mockResolvedValueOnce(mockClient());
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    fireEvent.click(screen.getByLabelText('edit-11111111-0000-0000-0000-000000000001'));

    fireEvent.change(screen.getByLabelText('telegram-username'), { target: { value: '@jan_new' } });
    fireEvent.submit(screen.getByLabelText('client-form'));

    await waitFor(() =>
      expect(clientsApi.updateClient).toHaveBeenCalledWith(
        '11111111-0000-0000-0000-000000000001',
        expect.objectContaining({
          nip: '1234567890',
          phone: '500600700',
          email: 'jan@example.pl',
        }),
      ),
    );
  });
});

describe('ClientList — client card contact details', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('displays NIP when present', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ nip: '1234567890' })],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    const contact = screen.getByLabelText('client-contact-11111111-0000-0000-0000-000000000001');
    expect(contact.textContent).toContain('1234567890');
  });

  it('displays phone when present', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({ items: [mockClient()], total: 1 });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    const contact = screen.getByLabelText('client-contact-11111111-0000-0000-0000-000000000001');
    expect(contact.textContent).toContain('500600700');
  });

  it('displays email when present', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ email: 'jan@example.pl' })],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    const contact = screen.getByLabelText('client-contact-11111111-0000-0000-0000-000000000001');
    expect(contact.textContent).toContain('jan@example.pl');
  });

  it('displays Telegram when present', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ telegram_username: '@vasiya' })],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    const contact = screen.getByLabelText('client-contact-11111111-0000-0000-0000-000000000001');
    expect(contact.textContent).toContain('@vasiya');
    expect(contact.textContent).toContain('Telegram:');
  });

  it('missing fields do not render empty labels (no NIP:/e-mail:/Telegram: with no value)', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ phone: '500600700', nip: null, email: null, telegram_username: null })],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    const contact = screen.getByLabelText('client-contact-11111111-0000-0000-0000-000000000001');
    expect(contact.textContent).not.toContain('NIP:');
    expect(contact.textContent).not.toContain('e-mail:');
    expect(contact.textContent).not.toContain('Telegram:');
    expect(contact.textContent).toContain('tel.:');
  });

  it('renders no contact block at all when every contact field is absent', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ phone: null, nip: null, email: null, telegram_username: null })],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    expect(screen.queryByLabelText('client-contact-11111111-0000-0000-0000-000000000001')).toBeNull();
  });

  it('long email and Telegram content wraps instead of overflowing (mobile-safe)', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({
        email: 'a.very.long.email.address.for.testing.wrapping@example-company-domain.pl',
        telegram_username: '@a_very_long_telegram_username_for_mobile_wrap_testing',
      })],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));
    const contact = screen.getByLabelText('client-contact-11111111-0000-0000-0000-000000000001');
    for (const p of Array.from(contact.querySelectorAll('p'))) {
      expect(p.className).toContain('break-words');
    }
  });

  it('existing archive/edit action behavior remains intact', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [mockClient()], total: 1 });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));

    expect(screen.getByLabelText('archive-11111111-0000-0000-0000-000000000001')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('archive-11111111-0000-0000-0000-000000000001'));
    await waitFor(() => expect(clientsApi.archiveClient).toHaveBeenCalledWith('11111111-0000-0000-0000-000000000001'));
  });
});

// ---------------------------------------------------------------------------
// Stage 10H.1 — actionable client contact interactions
// ---------------------------------------------------------------------------

describe('ClientList — actionable contact interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders the phone as a tel: link built from the stored value', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ phone: '+48 500 600 700' })],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));

    const link = screen.getByLabelText('call-11111111-0000-0000-0000-000000000001');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', 'tel:+48500600700');
    // Human-readable value is preserved exactly as stored.
    expect(link).toHaveTextContent('+48 500 600 700');
  });

  it('renders the Telegram username as a t.me link without a duplicated leading @', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ telegram_username: '@vasiya' })],
      total: 1,
    });
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));

    const link = screen.getByLabelText('open-telegram-11111111-0000-0000-0000-000000000001');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', 'https://t.me/vasiya');
    expect(link).toHaveTextContent('@vasiya');
  });

  it('tapping the e-mail copies it and shows a localized confirmation, without opening a mail composer', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ email: 'jan@example.pl' })],
      total: 1,
    });
    vi.mocked(clipboardUtil.copyTextToClipboard).mockResolvedValue(true);
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));

    const button = screen.getByLabelText('copy-email-11111111-0000-0000-0000-000000000001');
    expect(button.tagName).toBe('BUTTON');
    fireEvent.click(button);

    await waitFor(() => expect(clipboardUtil.copyTextToClipboard).toHaveBeenCalledWith('jan@example.pl'));
    expect(await screen.findByText('Skopiowano e-mail')).toBeInTheDocument();
    // Never a mailto: href / mail composer as the primary action.
    expect(button).not.toHaveAttribute('href');
  });

  it('shows a localized failure message when the clipboard copy fails', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValueOnce({
      items: [mockClient({ email: 'jan@example.pl' })],
      total: 1,
    });
    vi.mocked(clipboardUtil.copyTextToClipboard).mockResolvedValue(false);
    renderWithI18n(<ClientList />);
    await waitFor(() => screen.getByText('Jan Kowalski'));

    fireEvent.click(screen.getByLabelText('copy-email-11111111-0000-0000-0000-000000000001'));
    expect(await screen.findByText('Nie udało się skopiować e-maila')).toBeInTheDocument();
  });
});
