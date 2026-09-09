import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loginWithTelegram, TelegramAuthRequestError } from './auth';

describe('Telegram authentication API', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends raw Telegram initData unchanged', async () => {
    const initData = 'query_id=AAHdF6IQAAAAAN0XohDhrOrc&user=%7B%22id%22%3A12345678%7D&auth_date=1788991000&hash=valid%2Bhash';
    const responseData = {
      access_token: 'telegram-jwt',
      token_type: 'bearer',
      is_dev_auth: false,
      user: {
        id: '22222222-2222-2222-2222-222222222222',
        telegram_user_id: 12345678,
        username: 'real_contractor',
        first_name: 'Adam',
        last_name: 'Nowak',
        language_code: 'pl',
        created_at: '2026-09-10T00:00:00Z',
        updated_at: '2026-09-10T00:00:00Z',
      },
    };
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: vi.fn().mockResolvedValue(responseData),
    } as unknown as Response);

    await expect(loginWithTelegram(initData)).resolves.toEqual(responseData);

    const [, request] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(request?.body as string)).toEqual({ init_data: initData });
  });

  it('preserves the backend authentication error code without its message', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: vi.fn().mockResolvedValue({
        detail: {
          code: 'INVALID_TELEGRAM_SIGNATURE',
          message: 'Telegram signature mismatch',
        },
      }),
    } as unknown as Response);

    const request = loginWithTelegram('invalid-data');

    await expect(request).rejects.toMatchObject({
      code: 'INVALID_TELEGRAM_SIGNATURE',
      status: 401,
      message: 'Telegram authentication request failed',
    });
    await expect(request).rejects.toBeInstanceOf(TelegramAuthRequestError);
  });

  it('reports an unavailable backend without exposing the request payload', async () => {
    const initData = 'sensitive-raw-init-data';
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Failed to fetch'));

    const request = loginWithTelegram(initData);

    await expect(request).rejects.toMatchObject({
      code: null,
      status: 0,
      message: 'Telegram authentication request failed',
    });
    await expect(request).rejects.not.toHaveProperty('message', expect.stringContaining(initData));
  });
});
