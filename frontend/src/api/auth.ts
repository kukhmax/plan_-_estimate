import { AuthConfig, TelegramAuthResponse, User } from '../types/auth';

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


/** A refused sign-in by password: the code of the server (`INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`, ...), and for a lock the seconds to wait. */
export class PasswordLoginError extends Error {
  constructor(
    public readonly code: string | null,
    public readonly status: number,
    public readonly retryAfterSeconds: number | null = null,
    public readonly contact: string | null = null,
  ) {
    super('Password sign-in failed');
    this.name = 'PasswordLoginError';
  }
}

/** Is the sign-in by password switched on? Any failure counts as "no": the old message for an application opened outside Telegram stays. */
export async function fetchAuthConfig(): Promise<AuthConfig> {
  try {
    const response = await fetch(`${API_URL}/api/auth/config`);
    if (!response.ok) return { password_login: false };
    const body: unknown = await response.json();
    return { password_login: typeof body === 'object' && body !== null && 'password_login' in body && body.password_login === true };
  } catch {
    return { password_login: false };
  }
}

export async function loginWithPassword(email: string, password: string): Promise<TelegramAuthResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/auth/password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    throw new PasswordLoginError(null, 0);
  }
  if (!response.ok) {
    const errorData: unknown = await response.json().catch(() => null);
    const detail =
      typeof errorData === 'object' && errorData !== null && 'detail' in errorData && typeof errorData.detail === 'object' && errorData.detail !== null
        ? (errorData.detail as Record<string, unknown>)
        : {};
    throw new PasswordLoginError(
      typeof detail.code === 'string' ? detail.code : null,
      response.status,
      typeof detail.retry_after_seconds === 'number' ? detail.retry_after_seconds : null,
      readContact(errorData),
    );
  }
  return response.json();
}
