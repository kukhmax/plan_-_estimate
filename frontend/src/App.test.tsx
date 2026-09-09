import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App';
import * as api from './api/auth';

vi.mock('./api/auth', () => ({
  loginWithTelegram: vi.fn(),
  fetchCurrentUser: vi.fn(),
}));

// Mock clients API to prevent fetch errors in tests
vi.mock('./api/clients', () => ({
  fetchClients: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createClient: vi.fn(),
  archiveClient: vi.fn(),
  restoreClient: vi.fn(),
}));

describe('App authentication component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete (window as any).Telegram;
    localStorage.clear();
  });

  it('displays DEV AUTH banner when in dev mock mode', async () => {
    vi.mocked(api.loginWithTelegram).mockResolvedValueOnce({
      access_token: 'mock-jwt-token',
      token_type: 'bearer',
      is_dev_auth: true,
      user: {
        id: '11111111-1111-1111-1111-111111111111',
        telegram_user_id: 999999999,
        username: 'dev_contractor',
        first_name: 'Jan',
        last_name: 'Kowalski',
        language_code: 'pl',
        created_at: '2026-09-08T12:00:00Z',
        updated_at: '2026-09-08T12:00:00Z',
      },
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('alert', { name: 'dev-auth-banner' })).toBeInTheDocument();
    });

    expect(screen.getByText(/DEV AUTH MODE/i)).toBeInTheDocument();
    expect(screen.getByText('Jan Kowalski')).toBeInTheDocument();
    expect(screen.getByText('@dev_contractor')).toBeInTheDocument();
    expect(screen.getByText('999999999')).toBeInTheDocument();
    expect(localStorage.getItem('access_token')).toBe('mock-jwt-token');
  });

  it('displays verified user card without banner in standard Telegram mode', async () => {
    (window as any).Telegram = {
      WebApp: {
        initData: 'query_id=123&hash=valid_hash',
        ready: vi.fn(),
        expand: vi.fn(),
      },
    };

    vi.mocked(api.loginWithTelegram).mockResolvedValueOnce({
      access_token: 'valid-jwt-token',
      token_type: 'bearer',
      is_dev_auth: false,
      user: {
        id: '22222222-2222-2222-2222-222222222222',
        telegram_user_id: 12345678,
        username: 'real_contractor',
        first_name: 'Adam',
        last_name: 'Nowak',
        language_code: 'pl',
        created_at: '2026-09-08T12:00:00Z',
        updated_at: '2026-09-08T12:00:00Z',
      },
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Adam Nowak')).toBeInTheDocument();
    });

    expect(screen.queryByRole('alert', { name: 'dev-auth-banner' })).not.toBeInTheDocument();
    expect(screen.getByText('Telegram Verified')).toBeInTheDocument();
    expect(screen.getByText('@real_contractor')).toBeInTheDocument();
  });

  it('displays error state when authentication fails', async () => {
    vi.mocked(api.loginWithTelegram).mockRejectedValueOnce(
      new Error('Telegram signature mismatch'),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/błąd autoryzacji/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Telegram signature mismatch/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /ponów próbę/i })).toBeInTheDocument();
  });
});
