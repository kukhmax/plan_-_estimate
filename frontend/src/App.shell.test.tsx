import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';
import * as api from './api/auth';
import * as priceItemsApi from './api/priceItems';

vi.mock('./api/auth', async () => {
  const actual = await vi.importActual<typeof import('./api/auth')>('./api/auth');
  return {
    ...actual,
    loginWithTelegram: vi.fn(),
    fetchCurrentUser: vi.fn(),
  };
});

vi.mock('./api/clients', () => ({
  fetchClients: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createClient: vi.fn(),
  archiveClient: vi.fn(),
  restoreClient: vi.fn(),
}));
vi.mock('./api/projects', () => ({
  fetchProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  archiveProject: vi.fn(),
  restoreProject: vi.fn(),
}));
vi.mock('./api/rooms', () => ({
  fetchRooms: vi.fn(),
  fetchRoom: vi.fn(),
  createRoom: vi.fn(),
  updateRoom: vi.fn(),
  archiveRoom: vi.fn(),
  restoreRoom: vi.fn(),
}));
vi.mock('./api/surfaces', () => ({
  fetchSurfaces: vi.fn(),
  createSurface: vi.fn(),
  updateSurface: vi.fn(),
  archiveSurface: vi.fn(),
  restoreSurface: vi.fn(),
  generateWalls: vi.fn(),
}));
vi.mock('./api/openings', () => ({
  fetchOpenings: vi.fn(),
  createOpening: vi.fn(),
  updateOpening: vi.fn(),
  archiveOpening: vi.fn(),
  restoreOpening: vi.fn(),
}));
vi.mock('./api/priceItems', () => ({
  fetchPriceItems: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createPriceItem: vi.fn(),
  updatePriceItem: vi.fn(),
  archivePriceItem: vi.fn(),
  restorePriceItem: vi.fn(),
}));

const mockUser = {
  id: '11111111-1111-1111-1111-111111111111',
  telegram_user_id: 999999999,
  username: 'dev_contractor',
  first_name: 'Jan',
  last_name: 'Kowalski',
  language_code: 'pl',
  created_at: '2026-09-08T12:00:00Z',
  updated_at: '2026-09-08T12:00:00Z',
};

function mockDevAuth() {
  vi.mocked(api.loginWithTelegram).mockResolvedValueOnce({
    access_token: 'mock-jwt-token',
    token_type: 'bearer',
    is_dev_auth: true,
    user: mockUser,
  });
}

describe('App shell — compact account control (Stage 9D.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
    vi.stubEnv('DEV', true);
    vi.stubEnv('VITE_DEV_MOCK_AUTH', 'true');
    delete (window as any).Telegram;
    document.documentElement.removeAttribute('style');
    document.documentElement.removeAttribute('data-color-scheme');
    localStorage.clear();
  });

  it('A: no large authenticated-user card is rendered in normal page content', async () => {
    mockDevAuth();
    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'open-account' })).toBeInTheDocument(),
    );

    expect(screen.queryByLabelText('user-card')).not.toBeInTheDocument();
    expect(screen.queryByText('Telegram User ID')).not.toBeInTheDocument();
    expect(screen.queryByText('999999999')).not.toBeInTheDocument();
    // Navigation still first — the card did not consume the top of the page.
    expect(screen.getByRole('navigation', { name: 'main-navigation' })).toBeInTheDocument();
  });

  it('B: a compact account control exists in the app footer', async () => {
    mockDevAuth();
    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'open-account' })).toBeInTheDocument(),
    );

    const footer = screen.getByRole('contentinfo');
    const accountButton = screen.getByRole('button', { name: 'open-account' });
    expect(footer).toContainElement(accountButton);
    expect(footer).toHaveTextContent('Plan & Estimate');
  });

  it('C: opening the account control shows verification, Telegram ID, username, and UUID', async () => {
    mockDevAuth();
    render(<App />);

    fireEvent.click(
      await screen.findByRole('button', { name: 'open-account' }),
    );

    expect(screen.getByRole('dialog', { name: 'Dane użytkownika' })).toBeInTheDocument();
    expect(screen.getByText('Mock Auth')).toBeInTheDocument();
    expect(screen.getByText('Jan Kowalski')).toBeInTheDocument();
    expect(screen.getByText('999999999')).toBeInTheDocument();
    expect(screen.getByText('@dev_contractor')).toBeInTheDocument();
    expect(screen.getByText('11111111-1111-1111-1111-111111111111')).toBeInTheDocument();
  });

  it('D: closing restores the underlying page via the close button and ESC', async () => {
    mockDevAuth();
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'open-account' }));
    expect(screen.getByRole('dialog', { name: 'Dane użytkownika' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'close-account-modal' }));
    expect(screen.queryByRole('dialog', { name: 'Dane użytkownika' })).not.toBeInTheDocument();

    // The underlying page controls remain usable after closing.
    expect(screen.getByRole('button', { name: 'show-clients' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'open-account' }));
    expect(screen.getByRole('dialog', { name: 'Dane użytkownika' })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Dane użytkownika' })).not.toBeInTheDocument();
  });

  it('E: the account shell is localized in RU', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(api.loginWithTelegram).mockResolvedValueOnce({
      access_token: 'valid-jwt-token',
      token_type: 'bearer',
      is_dev_auth: false,
      user: mockUser,
    });
    render(<App />);

    const accountButton = await screen.findByRole('button', { name: 'open-account' });
    expect(accountButton).toHaveTextContent('Аккаунт');

    fireEvent.click(accountButton);
    expect(screen.getByRole('dialog', { name: 'Данные пользователя' })).toBeInTheDocument();
    expect(screen.getByText('Telegram подтверждён')).toBeInTheDocument();
    expect(screen.getByText('Имя пользователя')).toBeInTheDocument();
    // RU keeps the technical label in English.
    expect(screen.getByText('Telegram User ID')).toBeInTheDocument();
  });

  it('F: Price Book add-item form still opens fully after the account shell changes', async () => {
    mockDevAuth();
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'show-pricebook' }));
    await screen.findByRole('region', { name: 'price-book-section' });
    expect(priceItemsApi.fetchPriceItems).toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText('add-price-item'));
    expect(screen.getByLabelText('price-item-display-name')).toBeInTheDocument();
    expect(screen.getByLabelText('price-item-category')).toBeInTheDocument();
    expect(screen.getByLabelText('price-item-unit')).toBeInTheDocument();
    expect(screen.getByLabelText('price-item-scope')).toBeInTheDocument();
    expect(screen.getByLabelText('price-item-price')).toBeInTheDocument();
    expect(screen.getByLabelText('price-item-quality')).toBeInTheDocument();

    // Opening and closing the account modal leaves the form state intact.
    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: 'Nazwa testowa' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'open-account' }));
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByLabelText('price-item-display-name')).toBeInTheDocument();
  });

  it('exposes readable control theme variables for the light fallback', async () => {
    mockDevAuth();
    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'open-account' })).toBeInTheDocument(),
    );

    expect(document.documentElement.getAttribute('data-color-scheme')).toBe('light');
    const bg = document.documentElement.style.getPropertyValue('--tg-control-bg-color');
    const text = document.documentElement.style.getPropertyValue('--tg-control-text-color');
    expect(bg).toBeTruthy();
    expect(text).toBeTruthy();
    expect(bg).not.toBe(text);
  });

  it('exposes readable control theme variables for the Telegram dark theme', async () => {
    (window as any).Telegram = {
      WebApp: {
        initData: 'query_id=dark_shell&auth_date=1788991000&hash=valid',
        colorScheme: 'dark',
        themeParams: {
          bg_color: '#17212b',
          secondary_bg_color: '#232e3c',
          text_color: '#f5f5f5',
          hint_color: '#708499',
          link_color: '#6ab2f2',
          button_color: '#5288c1',
          button_text_color: '#ffffff',
        },
        viewportHeight: 700,
        viewportStableHeight: 700,
        ready: vi.fn(),
        expand: vi.fn(),
      },
    };
    vi.mocked(api.loginWithTelegram).mockResolvedValueOnce({
      access_token: 'valid-jwt-token',
      token_type: 'bearer',
      is_dev_auth: false,
      user: { ...mockUser, id: '22222222-2222-2222-2222-222222222222' },
    });

    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'open-account' })).toBeInTheDocument(),
    );

    expect(document.documentElement.getAttribute('data-color-scheme')).toBe('dark');
    const bg = document.documentElement.style.getPropertyValue('--tg-control-bg-color');
    const text = document.documentElement.style.getPropertyValue('--tg-control-text-color');
    const border = document.documentElement.style.getPropertyValue('--tg-control-border-color');
    expect(bg).toBe('#232e3c');
    expect(text).toBe('#f5f5f5');
    expect(bg).not.toBe(text);
    expect(border).toBeTruthy();
  });
});