import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';
import { chooseSection, openAccountDialog, openMenu } from './test/menu';
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
      expect(screen.getByRole('button', { name: 'open-menu' })).toBeInTheDocument(),
    );

    expect(screen.queryByLabelText('user-card')).not.toBeInTheDocument();
    expect(screen.queryByText('Telegram User ID')).not.toBeInTheDocument();
    expect(screen.queryByText('999999999')).not.toBeInTheDocument();
    // The sections are behind the menu: nothing of the navigation takes room on the page.
    expect(screen.queryByRole('navigation', { name: 'main-navigation' })).not.toBeInTheDocument();
  });

  it('B: the header is one compact row (logo, menu, language) and the account lives in the menu', async () => {
    mockDevAuth();
    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'open-menu' })).toBeInTheDocument(),
    );

    const header = screen.getByRole('banner', { name: 'app-header' });
    expect(header).toHaveTextContent('Plan & Estimate');
    expect(header).toContainElement(screen.getByRole('button', { name: 'open-menu' }));
    expect(header).toContainElement(screen.getByRole('button', { name: 'lang-pl' }));
    expect(header).toContainElement(screen.getByRole('button', { name: 'lang-ru' }));
    // No second title line and no footer any more.
    expect(screen.queryByText(/Telegram Mini App/)).not.toBeInTheDocument();
    expect(screen.queryByRole('contentinfo')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'open-account' })).not.toBeInTheDocument();

    await openMenu();
    const menu = screen.getByRole('dialog', { name: 'main-menu' });
    expect(menu).toContainElement(screen.getByRole('button', { name: 'open-account' }));
    const nav = screen.getByRole('navigation', { name: 'main-navigation' });
    expect(nav).toContainElement(screen.getByRole('button', { name: 'show-clients' }));
    expect(nav).toContainElement(screen.getByRole('button', { name: 'show-projects' }));
    expect(nav).toContainElement(screen.getByRole('button', { name: 'show-pricebook' }));
  });

  it('C: opening the account control shows verification, Telegram ID, username, and UUID', async () => {
    mockDevAuth();
    render(<App />);

    await openAccountDialog();

    // The menu closes when the account is chosen, so only the dialog stays.
    expect(screen.queryByRole('dialog', { name: 'main-menu' })).not.toBeInTheDocument();
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

    await openAccountDialog();
    expect(screen.getByRole('dialog', { name: 'Dane użytkownika' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'close-account-modal' }));
    expect(screen.queryByRole('dialog', { name: 'Dane użytkownika' })).not.toBeInTheDocument();

    // The underlying page controls remain usable after closing.
    expect(screen.getByRole('button', { name: 'open-menu' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'add-client' })).toBeInTheDocument();

    await openAccountDialog();
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

    await openMenu();
    const accountButton = screen.getByRole('button', { name: 'open-account' });
    expect(accountButton).toHaveTextContent('Аккаунт');
    expect(screen.getByRole('button', { name: 'show-projects' })).toHaveTextContent('Объекты');

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

    await chooseSection('show-pricebook');
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
    await openAccountDialog();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByLabelText('price-item-display-name')).toBeInTheDocument();
  });

  it('exposes readable control theme variables for the light fallback', async () => {
    mockDevAuth();
    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'open-menu' })).toBeInTheDocument(),
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
      expect(screen.getByRole('button', { name: 'open-menu' })).toBeInTheDocument(),
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
describe('App shell — executor profile entry (Stage 15C)', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(api.fetchCurrentUser).mockResolvedValue(mockUser);
  });

  it('opens the profile from the account dialog without closing the dialog, and closes back to it', async () => {
    mockDevAuth();
    render(<App />);
    await openAccountDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Profil wykonawcy' }));
    expect(await screen.findByRole('dialog', { name: 'Profil wykonawcy' })).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Dane użytkownika' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'close-executor-profile' }));
    expect(screen.queryByRole('dialog', { name: 'Profil wykonawcy' })).toBeNull();
    expect(screen.getByRole('dialog', { name: 'Dane użytkownika' })).toBeInTheDocument();
  });

  it('Escape closes the profile first and the dialog second', async () => {
    mockDevAuth();
    render(<App />);
    await openAccountDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Profil wykonawcy' }));
    await screen.findByRole('dialog', { name: 'Profil wykonawcy' });
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Profil wykonawcy' })).toBeNull();
    expect(screen.getByRole('dialog', { name: 'Dane użytkownika' })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Dane użytkownika' })).toBeNull();
  });
});

describe('App shell — the main menu (Stage 16K.1)', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(api.fetchCurrentUser).mockResolvedValue(mockUser);
  });

  it('opens from the burger, marks the current section and closes after a choice', async () => {
    mockDevAuth();
    render(<App />);
    await openMenu();
    expect(screen.getByRole('button', { name: 'show-clients' })).toHaveAttribute('aria-current', 'page');

    fireEvent.click(screen.getByRole('button', { name: 'show-pricebook' }));
    expect(screen.queryByRole('dialog', { name: 'main-menu' })).toBeNull();
    await screen.findByRole('region', { name: 'price-book-section' });

    await openMenu();
    expect(screen.getByRole('button', { name: 'show-pricebook' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'show-clients' })).not.toHaveAttribute('aria-current');
  });

  it('closes on Escape and on a tap outside without changing the section', async () => {
    mockDevAuth();
    render(<App />);
    await openMenu();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'main-menu' })).toBeNull();

    await openMenu();
    fireEvent.click(screen.getByRole('button', { name: 'close-menu-backdrop' }));
    expect(screen.queryByRole('dialog', { name: 'main-menu' })).toBeNull();
    expect(screen.getByRole('button', { name: 'add-client' })).toBeInTheDocument();
  });

  it('the language switch stays in the header and changes the menu labels', async () => {
    mockDevAuth();
    render(<App />);
    await openMenu();
    expect(screen.getByRole('button', { name: 'show-projects' })).toHaveTextContent('Obiekty');
    fireEvent.click(screen.getByRole('button', { name: 'lang-ru' }));
    expect(screen.getByRole('button', { name: 'show-projects' })).toHaveTextContent('Объекты');
    expect(screen.getByRole('button', { name: 'open-account' })).toHaveTextContent('Аккаунт');
  });

  it('the menu button is not offered while the user is not signed in', async () => {
    vi.mocked(api.loginWithTelegram).mockRejectedValue(new Error('network'));
    render(<App />);
    await screen.findByText(/./, { selector: 'h2' });
    expect(screen.queryByRole('button', { name: 'open-menu' })).toBeNull();
    // the language switch still works on the error screen
    expect(screen.getByRole('button', { name: 'lang-ru' })).toBeInTheDocument();
  });
});
