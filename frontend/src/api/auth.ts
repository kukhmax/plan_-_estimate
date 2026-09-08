import { TelegramAuthResponse, User } from '../types/auth';

const API_URL = import.meta.env.VITE_API_URL || '';

export async function loginWithTelegram(initData: string): Promise<TelegramAuthResponse> {
  const response = await fetch(`${API_URL}/api/auth/telegram`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ init_data: initData }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const message = errorData?.detail?.message || `Authentication failed (${response.status})`;
    throw new Error(message);
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
