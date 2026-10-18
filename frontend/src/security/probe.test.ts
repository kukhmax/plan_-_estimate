import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { TelegramBiometricManager, TelegramCloudStorage, TelegramKeyStorage, TelegramWebApp } from '../types/telegram';
import {
  AUTOMATIC_PROBES,
  MARKER_KEY,
  TIMEOUT_MS,
  askBiometricAccess,
  authenticateBiometric,
  buildReport,
  markerAction,
  probeArgon2,
  probeBiometric,
  probeCloudLimits,
  probeCloudStorage,
  probeDeviceStorage,
  probeEnvironment,
  probePbkdf2,
  probeSecureStorage,
  probeWebCrypto,
  runProbe,
  viaCallback,
} from './probe';

// the WebCrypto of Node (the page uses the one of the phone's browser); loaded by name so that the test needs no Node typings
let crypto: Crypto;
beforeAll(async () => {
  crypto = (await vi.importActual<{ webcrypto: Crypto }>('node:crypto')).webcrypto;
});

function cloud(limit = 4096, over: Partial<TelegramCloudStorage> = {}): TelegramCloudStorage & { map: Map<string, string> } {
  const map = new Map<string, string>();
  return {
    map,
    setItem: (key, value, cb) => (value.length > limit ? cb?.('VALUE_INVALID') : (map.set(key, value), cb?.(null, true))),
    getItem: (key, cb) => cb(null, map.get(key) ?? ''),
    removeItem: (key, cb) => (map.delete(key), cb?.(null, true)),
    getKeys: (cb) => cb(null, [...map.keys()]),
    ...over,
  };
}

function keystore(over: Partial<TelegramKeyStorage> = {}): TelegramKeyStorage & { map: Map<string, string> } {
  const map = new Map<string, string>();
  return {
    map,
    setItem: (key, value, cb) => (map.set(key, value), cb?.(null, true)),
    getItem: (key, cb) => cb(null, map.get(key) ?? '', true),
    removeItem: (key, cb) => (map.delete(key), cb?.(null, true)),
    ...over,
  };
}

const app = (over: Partial<TelegramWebApp> = {}): TelegramWebApp => ({ version: '9.1', platform: 'android', ...over }) as TelegramWebApp;

function biometrics(over: Partial<TelegramBiometricManager> = {}): TelegramBiometricManager {
  const manager: TelegramBiometricManager = {
    isInited: false, isBiometricAvailable: true, biometricType: 'finger', isAccessRequested: false, isAccessGranted: false, isBiometricTokenSaved: false, deviceId: 'd',
    init: (cb) => { manager.isInited = true; cb?.(); },
    requestAccess: (_p, cb) => { manager.isAccessGranted = true; cb?.(true); },
    authenticate: (_p, cb) => cb?.(true, 'token'),
    ...over,
  };
  return manager;
}

afterEach(() => {
  vi.useRealTimers();
});

describe('viaCallback', () => {
  it('resolves with what the callback gives, an error text included', async () => {
    expect(await viaCallback<string>((done) => done(null, 'v', 'extra'))).toEqual({ error: null, value: 'v', extra: 'extra' });
    expect(await viaCallback<string>((done) => done('BOOM'))).toEqual({ error: 'BOOM', value: undefined, extra: undefined });
  });

  it('is a timeout when the callback never comes', async () => {
    vi.useFakeTimers();
    const pending = viaCallback(() => undefined, 1000);
    const caught = pending.catch((error: Error) => error.message);
    await vi.advanceTimersByTimeAsync(1001);
    expect(await caught).toBe('TIMEOUT');
  });

  it('rejects when the call itself throws', async () => {
    await expect(viaCallback(() => { throw new Error('nope'); })).rejects.toThrow('nope');
  });
});

describe('probeEnvironment', () => {
  it('says it is not inside Telegram when there is no WebApp', async () => {
    const result = await probeEnvironment(undefined);
    expect(result).toMatchObject({ id: 'environment', status: 'unsupported' });
    expect(result.detail).toContain('telegram=absent');
  });

  it('lists the version, the platform, the version checks and which APIs exist', async () => {
    const tg = app({ isVersionAtLeast: (v) => parseFloat(v) <= 8, CloudStorage: cloud(), BiometricManager: biometrics() });
    const result = await probeEnvironment(tg);
    expect(result.status).toBe('ok');
    expect(result.detail).toContain('version=9.1');
    expect(result.detail).toContain('platform=android');
    expect(result.detail).toContain('>=8.0=true');
    expect(result.detail).toContain('>=9.0=false');
    expect(result.detail).toContain('CloudStorage=true');
    expect(result.detail).toContain('SecureStorage=false');
    expect(result.detail).toContain('BiometricManager=true');
  });

  it('says n/a for the version checks when the client has no isVersionAtLeast', async () => {
    expect((await probeEnvironment(app())).detail).toContain('>=6.9=n/a');
  });
});

describe('WebCrypto, PBKDF2, Argon2', () => {
  it('encrypts, decrypts and refuses a damaged ciphertext', async () => {
    const result = await probeWebCrypto(crypto);
    expect(result.status).toBe('ok');
    expect(result.detail).toContain('aes256gcm_roundtrip=true');
    expect(result.detail).toContain('damaged_refused=true');
  });

  it('is an error when a damaged ciphertext is NOT refused (the tag is not checked)', async () => {
    const lax = {
      getRandomValues: crypto.getRandomValues.bind(crypto),
      subtle: new Proxy(crypto.subtle, {
        get: (target, name) => {
          if (name === 'decrypt') return async (_a: unknown, _k: unknown, data: ArrayBuffer) => data;
          const member = (target as never)[name] as unknown;
          return typeof member === 'function' ? (member as (...args: unknown[]) => unknown).bind(target) : member;
        },
      }),
    } as unknown as Crypto;
    const result = await probeWebCrypto(lax);
    expect(result.status).toBe('error');
    expect(result.detail).toContain('damaged_refused=false');
  });

  it('is an error when the decrypted text is NOT the text that was encrypted', async () => {
    let calls = 0;
    const wrong = {
      getRandomValues: crypto.getRandomValues.bind(crypto),
      subtle: new Proxy(crypto.subtle, {
        get: (target, name) => {
          if (name === 'decrypt') {
            return async (...args: unknown[]) => {
              calls += 1;
              if (calls === 1) return new Uint8Array(1440).buffer; // the right length, the wrong bytes
              return (target.decrypt as (...a: unknown[]) => Promise<ArrayBuffer>).apply(target, args); // the damaged one is refused by the real tag check
            };
          }
          const member = (target as never)[name] as unknown;
          return typeof member === 'function' ? (member as (...args: unknown[]) => unknown).bind(target) : member;
        },
      }),
    } as unknown as Crypto;
    const result = await probeWebCrypto(wrong);
    expect(result.status).toBe('error');
    expect(result.detail).toContain('aes256gcm_roundtrip=false');
    expect(result.detail).toContain('damaged_refused=true');
  });

  it('is unsupported without crypto.subtle', async () => {
    expect((await probeWebCrypto({} as Crypto)).status).toBe('unsupported');
    expect((await probePbkdf2({} as Crypto)).status).toBe('unsupported');
  });

  it('times each count of rounds of PBKDF2', async () => {
    const result = await probePbkdf2(crypto, [10, 20]);
    expect(result.status).toBe('ok');
    expect(result.detail).toMatch(/^sha256 10=\d+ms; 20=\d+ms$/);
  });

  it('times Argon2id with each setting, in a chunk that loads on demand', async () => {
    const result = await probeArgon2([{ memoryKiB: 1024, iterations: 1 }, { memoryKiB: 2048, iterations: 2 }]);
    expect(result.status).toBe('ok');
    expect(result.detail).toMatch(/^argon2id m1MiB_t1=\d+ms; m2MiB_t2=\d+ms$/);
  });

  it('names the setting that failed and still reports the others', async () => {
    const result = await probeArgon2([{ memoryKiB: 1024, iterations: 1 }, { memoryKiB: 1, iterations: 1 }]);
    expect(result.status).toBe('error');
    expect(result.detail).toMatch(/m1MiB_t1=\d+ms/);
    expect(result.detail).toContain('FAILED(');
  });
});

describe('probeCloudStorage', () => {
  it('writes, reads back, lists and removes a value, and leaves nothing behind', async () => {
    const storage = cloud();
    const result = await probeCloudStorage(app({ CloudStorage: storage }));
    expect(result.status).toBe('ok');
    expect(result.detail).toContain('set=true');
    expect(result.detail).toContain('get=same');
    expect(result.detail).toContain('keys=1');
    expect(result.detail).toContain('after_remove=gone');
    expect(storage.map.size).toBe(0);
  });

  it('is unsupported when the client has no CloudStorage', async () => {
    expect(await probeCloudStorage(app())).toMatchObject({ status: 'unsupported', detail: 'CloudStorage=absent' });
  });

  it('is an error when what was read is not what was written', async () => {
    const result = await probeCloudStorage(app({ CloudStorage: cloud(4096, { getItem: (_k, cb) => cb(null, 'other') }) }));
    expect(result.status).toBe('error');
    expect(result.detail).toContain('get=DIFFERENT');
  });

  it('is an error when the write is refused, and says why', async () => {
    const result = await probeCloudStorage(app({ CloudStorage: cloud(4096, { setItem: (_k, _v, cb) => cb?.('STORAGE_KEY_INVALID') }) }));
    expect(result.status).toBe('error');
    expect(result.detail).toContain('set=STORAGE_KEY_INVALID');
  });

  it('is an error when a removed value is still there', async () => {
    const stuck = cloud();
    stuck.removeItem = (_k, cb) => cb?.(null, true);
    expect((await probeCloudStorage(app({ CloudStorage: stuck }))).detail).toContain('after_remove=STILL_THERE');
  });

  it('is a timeout when Telegram never answers', async () => {
    vi.useFakeTimers();
    const silent = cloud(4096, { setItem: () => undefined });
    const pending = probeCloudStorage(app({ CloudStorage: silent }));
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 10);
    expect(await pending).toMatchObject({ status: 'timeout' });
  });
});

describe('probeCloudLimits', () => {
  it('tells where the wall of the value size is and removes its test key', async () => {
    const storage = cloud(4096);
    const result = await probeCloudLimits(app({ CloudStorage: storage }));
    expect(result.status).toBe('ok');
    expect(result.detail).toBe('1024=accepted; 4096=accepted; 4097=refused(VALUE_INVALID)');
    expect(storage.map.size).toBe(0);
  });

  it('is unsupported without CloudStorage', async () => {
    expect((await probeCloudLimits(app())).status).toBe('unsupported');
  });
});

describe('SecureStorage and DeviceStorage', () => {
  it.each([
    ['SecureStorage', probeSecureStorage, 'secure_storage'],
    ['DeviceStorage', probeDeviceStorage, 'device_storage'],
  ] as const)('%s: writes, reads back, reports canRestore and removes the value', async (name, probe, id) => {
    const storage = keystore();
    const result = await probe(app({ [name]: storage }));
    expect(result).toMatchObject({ id, status: 'ok' });
    expect(result.detail).toContain('get=same');
    expect(result.detail).toContain('canRestore=true');
    expect(result.detail).toContain('after_remove=gone');
    expect(storage.map.size).toBe(0);
  });

  it.each([
    [probeSecureStorage, 'SecureStorage=absent'],
    [probeDeviceStorage, 'DeviceStorage=absent'],
  ] as const)('is unsupported when the client does not have it (%#)', async (probe, detail) => {
    expect(await probe(app())).toMatchObject({ status: 'unsupported', detail });
  });

  it('is an error when the value stays after the removal', async () => {
    const stuck = keystore({ removeItem: (_k, cb) => cb?.(null, true) });
    const result = await probeSecureStorage(app({ SecureStorage: stuck }));
    expect(result.status).toBe('error');
    expect(result.detail).toContain('after_remove=STILL_THERE');
  });
});

describe('biometrics', () => {
  it('starts the manager and describes what the phone can do', async () => {
    const manager = biometrics();
    const result = await probeBiometric(app({ BiometricManager: manager }));
    expect(manager.isInited).toBe(true);
    expect(result.status).toBe('ok');
    expect(result.detail).toContain('available=true');
    expect(result.detail).toContain('type=finger');
  });

  it('is unsupported when there is no manager or the phone has no biometrics', async () => {
    expect(await probeBiometric(app())).toMatchObject({ status: 'unsupported', detail: 'BiometricManager=absent' });
    expect((await probeBiometric(app({ BiometricManager: biometrics({ isBiometricAvailable: false }) }))).status).toBe('unsupported');
  });

  it('asks for access and reports a grant and a refusal', async () => {
    expect(await askBiometricAccess(app({ BiometricManager: biometrics() }))).toMatchObject({ status: 'ok' });
    const refusing = biometrics({ requestAccess: (_p, cb) => cb?.(false) });
    const result = await askBiometricAccess(app({ BiometricManager: refusing }));
    expect(result.status).toBe('denied');
    expect(result.detail).toContain('access_granted=false');
  });

  it('checks a finger and reports a failure', async () => {
    expect(await authenticateBiometric(app({ BiometricManager: biometrics() }))).toMatchObject({ status: 'ok', detail: 'authenticated=true' });
    const failing = biometrics({ authenticate: (_p, cb) => cb?.(false) });
    expect((await authenticateBiometric(app({ BiometricManager: failing }))).status).toBe('denied');
  });

  it('without a manager the two taps say it too', async () => {
    expect((await askBiometricAccess(app())).status).toBe('unsupported');
    expect((await authenticateBiometric(app())).status).toBe('unsupported');
  });
});

describe('the marker that shows what survives a reinstall', () => {
  it.each(['cloud', 'secure', 'device'] as const)('%s: writes a marker, reads the same back and clears it', async (kind) => {
    const stores = { cloud: cloud(), secure: keystore(), device: keystore() };
    const tg = app({ CloudStorage: stores.cloud, SecureStorage: stores.secure, DeviceStorage: stores.device });
    const written = await markerAction(kind, 'write', tg);
    expect(written.status).toBe('ok');
    expect(stores[kind].map.get(MARKER_KEY)).toBe(written.detail);
    for (const other of (['cloud', 'secure', 'device'] as const).filter((entry) => entry !== kind)) expect(stores[other].map.size).toBe(0);
    expect(await markerAction(kind, 'read', tg)).toMatchObject({ status: 'ok', detail: written.detail });
    expect(await markerAction(kind, 'clear', tg)).toMatchObject({ status: 'ok', detail: 'removed' });
    expect(stores[kind].map.size).toBe(0);
  });

  it('an empty read is not an error but "nothing there" (the marker did not survive)', async () => {
    const result = await markerAction('secure', 'read', app({ SecureStorage: keystore() }));
    expect(result).toMatchObject({ status: 'denied', detail: 'empty' });
  });

  it('says so when the storage is absent, refuses, or does not answer', async () => {
    expect(await markerAction('cloud', 'read', app())).toMatchObject({ status: 'unsupported' });
    const refusing = cloud(4096, { setItem: (_k, _v, cb) => cb?.('NOPE') });
    expect(await markerAction('cloud', 'write', app({ CloudStorage: refusing }))).toMatchObject({ status: 'error', detail: 'NOPE' });
    vi.useFakeTimers();
    const pending = markerAction('cloud', 'read', app({ CloudStorage: cloud(4096, { getItem: () => undefined }) }));
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 10);
    expect((await pending).status).toBe('timeout');
  });
});

describe('the report and the runner', () => {
  it('lists every check in its order, says "not run" for the missing, and adds the taps and the markers', () => {
    const report = buildReport(
      [{ id: 'environment', status: 'ok', detail: 'version=9.1', ms: 3 }, { id: 'argon2', status: 'error', detail: 'x' }],
      [{ kind: 'secure', action: 'read', status: 'denied', detail: 'empty' }],
      ['biometric.request_access: ok | access_granted=true'],
      { when: '2026-10-18T10:00:00Z', userAgent: 'UA' },
    );
    const lines = report.split('\n');
    expect(lines[0]).toBe('EN-1 report 2026-10-18T10:00:00Z');
    expect(report).toContain('environment: ok (3 ms) | version=9.1');
    expect(report).toContain('argon2: error | x');
    expect(report).toContain('webcrypto: not run');
    expect(lines.indexOf('environment: ok (3 ms) | version=9.1')).toBeLessThan(lines.indexOf('webcrypto: not run'));
    expect(report).toContain('taps:\nbiometric.request_access: ok | access_granted=true');
    expect(report).toContain('markers:\nsecure.read: denied | empty');
    expect(AUTOMATIC_PROBES).toHaveLength(9);
    expect(new Set(AUTOMATIC_PROBES).size).toBe(9);
  });

  it('runs a probe by its name', async () => {
    expect((await runProbe('environment', undefined)).status).toBe('unsupported');
    expect((await runProbe('secure_storage', app({ SecureStorage: keystore() }))).status).toBe('ok');
    expect((await runProbe('cloud_limits', app({ CloudStorage: cloud() }))).detail).toContain('4097=refused');
  });
});

