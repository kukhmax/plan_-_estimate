/** EN-1 -- the test page of the encryption spike is the last item of the menu and opens in the application. */
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import * as authApi from './api/auth';
import { chooseSection } from './test/menu';

vi.mock('./api/auth', async () => ({ ...(await vi.importActual<typeof import('./api/auth')>('./api/auth')), loginWithTelegram: vi.fn(), fetchCurrentUser: vi.fn() }));
vi.mock('./api/clients', () => ({ fetchClients: vi.fn().mockResolvedValue({ items: [], total: 0 }), createClient: vi.fn(), archiveClient: vi.fn(), restoreClient: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllEnvs();
  vi.stubEnv('DEV', true);
  vi.stubEnv('VITE_DEV_MOCK_AUTH', 'true');
  delete (window as unknown as { Telegram?: unknown }).Telegram;
  localStorage.clear();
  vi.mocked(authApi.loginWithTelegram).mockResolvedValue({
    access_token: 't', token_type: 'bearer', is_dev_auth: true,
    user: { id: 'u1', telegram_user_id: 1, username: 'u', first_name: 'Jan', last_name: 'K', language_code: 'pl', created_at: '2026-09-08T12:00:00Z', updated_at: '2026-09-08T12:00:00Z' },
  });
});

describe('the test page of the security spike in the menu', () => {
  it('is the last item of the menu and opens the page', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'open-menu' }));
    const items = screen.getAllByRole('button').map((b) => b.getAttribute('aria-label')).filter((label) => label?.startsWith('show-'));
    expect(items[items.length - 1]).toBe('show-security');
    fireEvent.click(screen.getByRole('button', { name: 'show-security' }));
    expect(await screen.findByLabelText('security-probe')).toBeInTheDocument();
    expect(screen.queryByLabelText('clients-section')).toBeNull();
  });

  it('is named in Polish and in Russian', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'open-menu' }));
    expect(screen.getByRole('button', { name: 'show-security' })).toHaveTextContent('Test zabezpieczeń');
  });

  it('opens by the helper of the other tests too', async () => {
    render(<App />);
    await chooseSection('show-security');
    expect(await screen.findByLabelText('probe-run-all')).toBeInTheDocument();
  });
});
