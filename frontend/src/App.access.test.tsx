/** Closed registration -- the menu item of the administrator, the card of a refused person, and the loss of access while the application is open. */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import * as authApi from './api/auth';
import { ACCESS_LOST_EVENT, ApiError, apiRequest } from './api/http';
import type { TelegramAuthResponse } from './types/auth';

vi.mock('./api/auth', async () => ({ ...(await vi.importActual<typeof import('./api/auth')>('./api/auth')), loginWithTelegram: vi.fn(), fetchCurrentUser: vi.fn() }));
vi.mock('./api/clients', () => ({ fetchClients: vi.fn().mockResolvedValue({ items: [], total: 0 }), createClient: vi.fn(), archiveClient: vi.fn(), restoreClient: vi.fn() }));
vi.mock('./api/access', () => ({
  fetchAccess: vi.fn().mockResolvedValue({ settings: { closed: true, contact: '' }, entries: [] }),
  decideAccess: vi.fn(), removeAccess: vi.fn(), saveAccessSettings: vi.fn(),
}));

const login = (isAdmin: boolean): TelegramAuthResponse => ({
  access_token: 't', token_type: 'bearer', is_dev_auth: true,
  user: { id: 'u1', telegram_user_id: 1, username: 'u', first_name: 'Jan', last_name: 'K', language_code: 'pl', created_at: '2026-09-08T12:00:00Z', updated_at: '2026-09-08T12:00:00Z', is_admin: isAdmin },
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllEnvs();
  vi.stubEnv('DEV', true);
  vi.stubEnv('VITE_DEV_MOCK_AUTH', 'true');
  delete (window as unknown as { Telegram?: unknown }).Telegram;
  localStorage.clear();
});

const items = () => screen.getAllByRole('button').map((b) => b.getAttribute('aria-label')).filter((label) => label?.startsWith('show-'));

describe('the access list in the menu', () => {
  it('is offered to the administrator, just before the test page, and opens the screen', async () => {
    vi.mocked(authApi.loginWithTelegram).mockResolvedValue(login(true));
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'open-menu' }));
    const names = items();
    expect(names[names.length - 2]).toBe('show-access');
    expect(names[names.length - 1]).toBe('show-security');
    expect(screen.getByRole('button', { name: 'show-access' })).toHaveTextContent('Dostęp');
    fireEvent.click(screen.getByRole('button', { name: 'show-access' }));
    expect(await screen.findByLabelText('access-screen')).toBeInTheDocument();
  });

  it('is not offered to anyone else', async () => {
    vi.mocked(authApi.loginWithTelegram).mockResolvedValue(login(false));
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'open-menu' }));
    expect(screen.queryByRole('button', { name: 'show-access' })).toBeNull();
  });
});

describe('a refused person', () => {
  it('sees that the access is closed and the contact of the owner, and can ask again', async () => {
    vi.mocked(authApi.loginWithTelegram).mockRejectedValueOnce(new authApi.TelegramAuthRequestError('ACCESS_DENIED', 403, 'Jan, @jan'));
    render(<App />);
    const card = await screen.findByLabelText('access-denied');
    expect(card).toHaveTextContent('Brak dostępu');
    expect(screen.getByLabelText('access-contact-text')).toHaveTextContent('Kontakt: Jan, @jan');
    expect(screen.queryByRole('button', { name: 'open-menu' })).toBeNull();
    vi.mocked(authApi.loginWithTelegram).mockResolvedValueOnce(login(false));
    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź ponownie' }));
    expect(await screen.findByRole('button', { name: 'open-menu' })).toBeInTheDocument();
    expect(screen.queryByLabelText('access-denied')).toBeNull();
  });

  it('is told apart when the account is blocked, and no contact line appears when there is none', async () => {
    vi.mocked(authApi.loginWithTelegram).mockRejectedValueOnce(new authApi.TelegramAuthRequestError('ACCESS_BLOCKED', 403, null));
    render(<App />);
    expect(await screen.findByLabelText('access-denied')).toHaveTextContent('Dostęp zablokowany');
    expect(screen.queryByLabelText('access-contact-text')).toBeNull();
  });

  it('reads the contact from the answer of the server', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 403,
      json: async () => ({ detail: { code: 'ACCESS_DENIED', message: 'closed', contact: '@owner' } }),
    }));
    const real = await vi.importActual<typeof import('./api/auth')>('./api/auth');
    await expect(real.loginWithTelegram('x')).rejects.toMatchObject({ code: 'ACCESS_DENIED', status: 403, contact: '@owner' });
    vi.unstubAllGlobals();
  });
});

describe('access taken away while the application is open', () => {
  it('shows the card when a request is refused with ACCESS_BLOCKED', async () => {
    vi.mocked(authApi.loginWithTelegram).mockResolvedValue(login(false));
    render(<App />);
    await screen.findByRole('button', { name: 'open-menu' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 403,
      json: async () => ({ detail: { code: 'ACCESS_BLOCKED', message: 'blocked', contact: '@owner' } }),
    }));
    await act(async () => {
      await expect(apiRequest('/api/access')).rejects.toBeInstanceOf(ApiError);
    });
    expect(await screen.findByLabelText('access-denied')).toHaveTextContent('Dostęp zablokowany');
    expect(screen.getByLabelText('access-contact-text')).toHaveTextContent('@owner');
    expect(localStorage.getItem('access_token')).toBeNull();
    vi.unstubAllGlobals();
  });

  it('is announced for ACCESS_DENIED but not for any other 403', async () => {
    const heard = vi.fn();
    window.addEventListener(ACCESS_LOST_EVENT, heard);
    for (const [code, expected] of [['ACCESS_DENIED', 1], ['ACCESS_ADMIN_ONLY', 1], ['ACCESS_BLOCKED', 2]] as const) {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: { code, message: 'm', contact: '' } }) }));
      await expect(apiRequest('/api/access')).rejects.toBeInstanceOf(ApiError);
      expect(heard).toHaveBeenCalledTimes(expected);
    }
    window.removeEventListener(ACCESS_LOST_EVENT, heard);
    vi.unstubAllGlobals();
  });
});
