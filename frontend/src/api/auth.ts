import { TelegramAuthResponse, User } from '../types/auth';

const API_URL = import.meta.env.VITE_API_URL || '';

export class TelegramAuthRequestError extends Error {
  constructor(
    public readonly code: string | null,
    public readonly status: number,
    /** closed registration: the contact text the administrator set, shown to a refused person */
    public readonly contact: string | null = null,
  ) {
    super('Telegram authentication request failed');
    this.name = 'TelegramAuthRequestError';
  }
}

function readErrorCode(payload: unknown): string | null {
  if (typeof payload !== 'object' || payload === null || !('detail' in payload)) return null;
  const detail = payload.detail;
  if (typeof detail !== 'object' || detail === null || !('code' in detail)) return null;
  return typeof detail.code === 'string' ? detail.code : null;
}

function readContact(payload: unknown): string | null {
  if (typeof payload !== 'object' || payload === null || !('detail' in payload)) return null;
  const detail = payload.detail;
  if (typeof detail !== 'object' || detail === null || !('contact' in detail)) return null;
  return typeof detail.contact === 'string' && detail.contact.trim() ? detail.contact : null;
}

export async function loginWithTelegram(initData: string): Promise<TelegramAuthResponse> {
  let response: Response;

  try {
    response = await fetch(`${API_URL}/api/auth/telegram`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ init_data: initData }),
    });
  } catch {
    throw new TelegramAuthRequestError(null, 0);
  }

  if (!response.ok) {
    const errorData: unknown = await response.json().catch(() => null);
    throw new TelegramAuthRequestError(readErrorCode(errorData), response.status, readContact(errorData));
  }

  return response.json();
}

export async function fetchCurrentUser(token: string): Promise<User> {
  const response = await fetch(`${API_URL}/api/me`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const message = errorData?.detail?.message || `Failed to fetch profile (${response.status})`;
    throw new Error(message);
  }

  return response.json();
}
