import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchExecutorProfile, profileFieldErrors, saveExecutorProfile } from './executorProfile';

const PAYLOAD = {
  name: 'Jan', nip: '', street: '', postal_code: '', city: '', phone: '', email: '', bank_account: '',
};

function respond(status: number, body: unknown) {
  vi.mocked(fetch).mockResolvedValueOnce({
    ok: status < 400,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response);
}

describe('executor profile API', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('GET unwraps the profile and is null before the first save', async () => {
    respond(200, { profile: null });
    expect(await fetchExecutorProfile()).toBeNull();
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe('/api/executor-profile');
    expect((init?.headers as Headers).get('Authorization')).toBe('Bearer tok');
    respond(200, { profile: { id: 'p1', name: 'Jan' } });
    expect(await fetchExecutorProfile()).toMatchObject({ id: 'p1', name: 'Jan' });
  });

  it('PUT sends the whole form as JSON', async () => {
    respond(200, { id: 'p1', name: 'Jan' });
    await saveExecutorProfile(PAYLOAD);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe('/api/executor-profile');
    expect(init?.method).toBe('PUT');
    expect(JSON.parse(String(init?.body))).toEqual(PAYLOAD);
  });

  it('reads field codes only from the EXECUTOR_PROFILE_INVALID envelope', () => {
    expect(profileFieldErrors({ code: 'EXECUTOR_PROFILE_INVALID', message: 'm', fields: { nip: 'NIP_INVALID', x: 5 } }))
      .toEqual({ nip: 'NIP_INVALID' });
    expect(profileFieldErrors({ code: 'OTHER', fields: { nip: 'NIP_INVALID' } })).toEqual({});
    expect(profileFieldErrors({ code: 'EXECUTOR_PROFILE_INVALID', fields: ['nip'] })).toEqual({});
    expect(profileFieldErrors('text')).toEqual({});
    expect(profileFieldErrors(null)).toEqual({});
    expect(profileFieldErrors([{ msg: 'x' }])).toEqual({});
  });
});
