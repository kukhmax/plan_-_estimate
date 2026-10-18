/**
 * EN-1 -- the spike of the encryption of the client data (`docs/CLIENT_DATA_ENCRYPTION_PLAN_RU.md`, section 5): what the Telegram of THIS phone really
 * offers for keeping a key of the owner (V2), measured on the phone and not taken from a document. No data of a client is touched: the probes write and
 * read back small test values under the keys `en1_*` and remove them (the markers stay only when the owner asks for them, to see what survives a
 * reinstall or a new phone). Nothing is sent to the server.
 *
 * Every probe answers with a status and a short list of raw values (`key=value`): the report is meant to be read by the developer, so the values are not
 * sentences; the screen names the checks and the statuses in the language of the interface.
 */
import type { TelegramBiometricManager, TelegramCloudStorage, TelegramKeyStorage, TelegramWebApp } from '../types/telegram';

export type ProbeStatus = 'ok' | 'unsupported' | 'error' | 'timeout' | 'denied';

export type ProbeId =
  | 'environment'
  | 'webcrypto'
  | 'pbkdf2'
  | 'argon2'
  | 'cloud_storage'
  | 'cloud_limits'
  | 'secure_storage'
  | 'device_storage'
  | 'biometric';

export interface ProbeResult {
  id: ProbeId;
  status: ProbeStatus;
  /** Raw values, `key=value; key=value`. */
  detail: string;
  /** How long the whole probe took, in milliseconds. */
  ms?: number;
}

/** The checks that need no tap of the owner, in the order they run. */
export const AUTOMATIC_PROBES: readonly ProbeId[] = [
  'environment',
  'webcrypto',
  'pbkdf2',
  'argon2',
  'cloud_storage',
  'cloud_limits',
  'secure_storage',
  'device_storage',
  'biometric',
];

export const TIMEOUT_MS = 8000;
export const KEY_PREFIX = 'en1_';
export const MARKER_KEY = `${KEY_PREFIX}marker`;

export type StorageKind = 'cloud' | 'secure' | 'device';

const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());
const rounded = (value: number) => Math.round(value);
const fail = (id: ProbeId, error: unknown, ms?: number): ProbeResult => ({ id, status: 'error', detail: `error=${describe(error)}`, ms });

export function describe(error: unknown): string {
  if (error instanceof Error) return `${error.name}: ${error.message}`.slice(0, 160);
  return String(error).slice(0, 160);
}

/** Calls an API of Telegram that answers through a callback; a callback that never comes is a timeout (some clients ignore calls they do not know). */
export function viaCallback<T>(start: (done: (error: string | null, value?: T, extra?: unknown) => void) => void, timeoutMs = TIMEOUT_MS): Promise<{ error: string | null; value?: T; extra?: unknown }> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('TIMEOUT')), timeoutMs);
    try {
      start((error, value, extra) => {
        clearTimeout(timer);
        resolve({ error: error ?? null, value, extra });
      });
    } catch (caught) {
      clearTimeout(timer);
      reject(caught);
    }
  });
}

const isTimeout = (error: unknown) => error instanceof Error && error.message === 'TIMEOUT';

async function timed(id: ProbeId, run: () => Promise<Omit<ProbeResult, 'id' | 'ms'>>): Promise<ProbeResult> {
  const started = now();
  try {
    const result = await run();
    return { id, ...result, ms: rounded(now() - started) };
  } catch (caught) {
    const ms = rounded(now() - started);
    if (isTimeout(caught)) return { id, status: 'timeout', detail: `no answer in ${TIMEOUT_MS} ms`, ms };
    return fail(id, caught, ms);
  }
}

export function telegramApp(): TelegramWebApp | undefined {
  return typeof window === 'undefined' ? undefined : window.Telegram?.WebApp;
}

// -- the environment -----------------------------------------------------------------------------------------------------------------------------

export async function probeEnvironment(tg: TelegramWebApp | undefined = telegramApp()): Promise<ProbeResult> {
  return timed('environment', async () => {
    if (!tg) return { status: 'unsupported', detail: 'telegram=absent (the page is not open inside Telegram)' };
    const at = (version: string) => (tg.isVersionAtLeast ? String(tg.isVersionAtLeast(version)) : 'n/a');
    const has = (name: keyof TelegramWebApp) => String(tg[name] !== undefined);
    return {
      status: 'ok',
      detail: [
        `version=${tg.version}`,
        `platform=${tg.platform}`,
        `>=6.9=${at('6.9')}`,
        `>=7.2=${at('7.2')}`,
        `>=8.0=${at('8.0')}`,
        `>=9.0=${at('9.0')}`,
        `CloudStorage=${has('CloudStorage')}`,
        `SecureStorage=${has('SecureStorage')}`,
        `DeviceStorage=${has('DeviceStorage')}`,
        `BiometricManager=${has('BiometricManager')}`,
      ].join('; '),
    };
  });
}

// -- WebCrypto, PBKDF2, Argon2 -------------------------------------------------------------------------------------------------------------------

export async function probeWebCrypto(cryptoImpl: Crypto | undefined = globalThis.crypto): Promise<ProbeResult> {
  return timed('webcrypto', async () => {
    if (!cryptoImpl?.subtle) return { status: 'unsupported', detail: 'crypto.subtle=absent' };
    const key = await cryptoImpl.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']);
    const iv = cryptoImpl.getRandomValues(new Uint8Array(12));
    const plain = new TextEncoder().encode('Zażółć gęślą jaźń — test szyfrowania '.repeat(30));
    const cipher = await cryptoImpl.subtle.encrypt({ name: 'AES-GCM', iv }, key, plain);
    const back = new Uint8Array(await cryptoImpl.subtle.decrypt({ name: 'AES-GCM', iv }, key, cipher));
    const same = back.length === plain.length && back.every((byte, index) => byte === plain[index]);
    // a flipped bit must be refused (the tag is checked), or the algorithm is not what it says
    const damaged = new Uint8Array(cipher);
    damaged[0] ^= 1;
    let refused = false;
    try {
      await cryptoImpl.subtle.decrypt({ name: 'AES-GCM', iv }, key, damaged);
    } catch {
      refused = true;
    }
    return { status: same && refused ? 'ok' : 'error', detail: `aes256gcm_roundtrip=${same}; damaged_refused=${refused}; bytes=${plain.length}` };
  });
}

export const PBKDF2_ROUNDS = [100_000, 300_000, 600_000] as const;

export async function probePbkdf2(cryptoImpl: Crypto | undefined = globalThis.crypto, rounds: readonly number[] = PBKDF2_ROUNDS): Promise<ProbeResult> {
  return timed('pbkdf2', async () => {
    if (!cryptoImpl?.subtle) return { status: 'unsupported', detail: 'crypto.subtle=absent' };
    const material = await cryptoImpl.subtle.importKey('raw', new TextEncoder().encode('correct horse battery staple'), 'PBKDF2', false, ['deriveBits']);
    const salt = cryptoImpl.getRandomValues(new Uint8Array(16));
    const parts: string[] = [];
    for (const iterations of rounds) {
      const started = now();
      await cryptoImpl.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations }, material, 256);
      parts.push(`${iterations}=${rounded(now() - started)}ms`);
    }
    return { status: 'ok', detail: `sha256 ${parts.join('; ')}` };
  });
}

export interface Argon2Setting {
  memoryKiB: number;
  iterations: number;
}

/** Light and heavy: the first is what a phone should always manage, the second shows where the memory or the patience of the phone ends. */
export const ARGON2_SETTINGS: readonly Argon2Setting[] = [
  { memoryKiB: 19_456, iterations: 2 },
  { memoryKiB: 65_536, iterations: 3 },
];

export async function probeArgon2(settings: readonly Argon2Setting[] = ARGON2_SETTINGS): Promise<ProbeResult> {
  return timed('argon2', async () => {
    const { argon2id } = await import('hash-wasm'); // a chunk of its own: the page of the spike pays for it, the rest of the application does not
    const salt = globalThis.crypto.getRandomValues(new Uint8Array(16));
    const parts: string[] = [];
    let failed = false;
    for (const setting of settings) {
      const label = `m${Math.round(setting.memoryKiB / 1024)}MiB_t${setting.iterations}`;
      const started = now();
      try {
        await argon2id({ password: 'correct horse battery staple', salt, parallelism: 1, iterations: setting.iterations, memorySize: setting.memoryKiB, hashLength: 32, outputType: 'hex' });
        parts.push(`${label}=${rounded(now() - started)}ms`);
      } catch (caught) {
        failed = true;
        parts.push(`${label}=FAILED(${describe(caught)})`);
      }
    }
    const allFailed = parts.every((part) => part.includes('FAILED'));
    return { status: allFailed ? 'error' : failed ? 'error' : 'ok', detail: `argon2id ${parts.join('; ')}` };
  });
}

// -- the storages of Telegram --------------------------------------------------------------------------------------------------------------------

/** Writes, reads back, lists (cloud only) and removes one small value; the value read must be the value written. */
export async function probeCloudStorage(tg: TelegramWebApp | undefined = telegramApp()): Promise<ProbeResult> {
  return timed('cloud_storage', async () => {
    const storage = tg?.CloudStorage;
    if (!storage) return { status: 'unsupported', detail: 'CloudStorage=absent' };
    const key = `${KEY_PREFIX}probe`;
    const value = `probe-${Math.random().toString(36).slice(2, 10)}`;
    const marks: string[] = [];
    const set = await viaCallback<boolean>((done) => storage.setItem(key, value, done));
    marks.push(`set=${set.error ?? set.value}`);
    const got = await viaCallback<string>((done) => storage.getItem(key, done));
    marks.push(`get=${got.error ?? (got.value === value ? 'same' : 'DIFFERENT')}`);
    const keys = await viaCallback<string[]>((done) => storage.getKeys(done));
    marks.push(`keys=${keys.error ?? (keys.value ?? []).length}`);
    const removed = await viaCallback<boolean>((done) => storage.removeItem(key, done));
    marks.push(`remove=${removed.error ?? removed.value}`);
    const after = await viaCallback<string>((done) => storage.getItem(key, done));
    marks.push(`after_remove=${after.error ?? (after.value ? 'STILL_THERE' : 'gone')}`);
    const good = !set.error && got.value === value && !removed.error && !after.value;
    return { status: good ? 'ok' : 'error', detail: marks.join('; ') };
  });
}

export const CLOUD_SIZES = [1024, 4096, 4097] as const;

/** How big a value CloudStorage accepts (a wrapped key with its salt fits in a few hundred characters; the check tells where the wall is). */
export async function probeCloudLimits(tg: TelegramWebApp | undefined = telegramApp(), sizes: readonly number[] = CLOUD_SIZES): Promise<ProbeResult> {
  return timed('cloud_limits', async () => {
    const storage = tg?.CloudStorage;
    if (!storage) return { status: 'unsupported', detail: 'CloudStorage=absent' };
    const key = `${KEY_PREFIX}size`;
    const parts: string[] = [];
    for (const size of sizes) {
      const set = await viaCallback<boolean>((done) => storage.setItem(key, 'x'.repeat(size), done));
      parts.push(`${size}=${set.error ? `refused(${set.error})` : set.value === false ? 'refused' : 'accepted'}`);
    }
    await viaCallback<boolean>((done) => storage.removeItem(key, done));
    return { status: 'ok', detail: parts.join('; ') };
  });
}

async function probeKeyStorage(id: 'secure_storage' | 'device_storage', storage: TelegramKeyStorage | undefined, name: string): Promise<ProbeResult> {
  return timed(id, async () => {
    if (!storage) return { status: 'unsupported', detail: `${name}=absent` };
    const key = `${KEY_PREFIX}probe`;
    const value = `probe-${Math.random().toString(36).slice(2, 10)}`;
    const marks: string[] = [];
    const set = await viaCallback<boolean>((done) => storage.setItem(key, value, done));
    marks.push(`set=${set.error ?? set.value}`);
    const got = await viaCallback<string>((done) => storage.getItem(key, done));
    marks.push(`get=${got.error ?? (got.value === value ? 'same' : 'DIFFERENT')}`);
    if (got.extra !== undefined) marks.push(`canRestore=${String(got.extra)}`);
    const removed = await viaCallback<boolean>((done) => storage.removeItem(key, done));
    marks.push(`remove=${removed.error ?? removed.value}`);
    const after = await viaCallback<string>((done) => storage.getItem(key, done));
    marks.push(`after_remove=${after.error ?? (after.value ? 'STILL_THERE' : 'gone')}`);
    const good = !set.error && got.value === value && !removed.error && !after.value;
    return { status: good ? 'ok' : 'error', detail: marks.join('; ') };
  });
}

export const probeSecureStorage = (tg: TelegramWebApp | undefined = telegramApp()) => probeKeyStorage('secure_storage', tg?.SecureStorage, 'SecureStorage');
export const probeDeviceStorage = (tg: TelegramWebApp | undefined = telegramApp()) => probeKeyStorage('device_storage', tg?.DeviceStorage, 'DeviceStorage');

// -- the biometrics --------------------------------------------------------------------------------------------------------------------------------

function describeBiometrics(manager: TelegramBiometricManager): string {
  return [
    `available=${manager.isBiometricAvailable}`,
    `type=${manager.biometricType}`,
    `access_requested=${manager.isAccessRequested}`,
    `access_granted=${manager.isAccessGranted}`,
    `token_saved=${manager.isBiometricTokenSaved}`,
  ].join('; ');
}

/** The part that needs no tap: starts the manager and says what the phone can do. Asking for access and checking the finger are separate buttons. */
export async function probeBiometric(tg: TelegramWebApp | undefined = telegramApp()): Promise<ProbeResult> {
  return timed('biometric', async () => {
    const manager = tg?.BiometricManager;
    if (!manager) return { status: 'unsupported', detail: 'BiometricManager=absent' };
    if (!manager.isInited) await viaCallback<void>((done) => manager.init(() => done(null)));
    return { status: manager.isBiometricAvailable ? 'ok' : 'unsupported', detail: describeBiometrics(manager) };
  });
}

/** Needs a tap of the owner (the phone shows its own question). */
export async function askBiometricAccess(tg: TelegramWebApp | undefined = telegramApp(), reason = 'EN-1: test'): Promise<ProbeResult> {
  return timed('biometric', async () => {
    const manager = tg?.BiometricManager;
    if (!manager) return { status: 'unsupported', detail: 'BiometricManager=absent' };
    if (!manager.isInited) await viaCallback<void>((done) => manager.init(() => done(null)));
    const answer = await viaCallback<boolean>((done) => manager.requestAccess({ reason }, (granted) => done(null, granted)), 60_000);
    return { status: answer.value ? 'ok' : 'denied', detail: `access_granted=${String(answer.value)}; ${describeBiometrics(manager)}` };
  });
}

/** Needs a tap and a finger / a face. */
export async function authenticateBiometric(tg: TelegramWebApp | undefined = telegramApp(), reason = 'EN-1: test'): Promise<ProbeResult> {
  return timed('biometric', async () => {
    const manager = tg?.BiometricManager;
    if (!manager) return { status: 'unsupported', detail: 'BiometricManager=absent' };
    if (!manager.isInited) await viaCallback<void>((done) => manager.init(() => done(null)));
    const answer = await viaCallback<boolean>((done) => manager.authenticate({ reason }, (success) => done(null, success)), 60_000);
    return { status: answer.value ? 'ok' : 'denied', detail: `authenticated=${String(answer.value)}` };
  });
}

// -- the marker (what survives a reinstall or a new phone) ---------------------------------------------------------------------------------------

function storageOf(tg: TelegramWebApp | undefined, kind: StorageKind): TelegramCloudStorage | TelegramKeyStorage | undefined {
  return kind === 'cloud' ? tg?.CloudStorage : kind === 'secure' ? tg?.SecureStorage : tg?.DeviceStorage;
}

export interface MarkerResult {
  kind: StorageKind;
  action: 'write' | 'read' | 'clear';
  status: ProbeStatus;
  /** The marker as it was read (`read`), the value written (`write`), or a raw detail. */
  detail: string;
}

/** The owner writes a marker now, then reinstalls Telegram or opens the page on another phone and reads it: the table of what survives. */
export async function markerAction(kind: StorageKind, action: MarkerResult['action'], tg: TelegramWebApp | undefined = telegramApp()): Promise<MarkerResult> {
  const storage = storageOf(tg, kind);
  if (!storage) return { kind, action, status: 'unsupported', detail: 'absent' };
  try {
    if (action === 'write') {
      const value = new Date().toISOString();
      const done = await viaCallback<boolean>((cb) => storage.setItem(MARKER_KEY, value, cb));
      return { kind, action, status: done.error ? 'error' : 'ok', detail: done.error ?? value };
    }
    if (action === 'read') {
      const got = await viaCallback<string>((cb) => storage.getItem(MARKER_KEY, cb));
      if (got.error) return { kind, action, status: 'error', detail: got.error };
      return { kind, action, status: got.value ? 'ok' : 'denied', detail: got.value ? got.value : 'empty' };
    }
    const removed = await viaCallback<boolean>((cb) => storage.removeItem(MARKER_KEY, cb));
    return { kind, action, status: removed.error ? 'error' : 'ok', detail: removed.error ?? 'removed' };
  } catch (caught) {
    return { kind, action, status: isTimeout(caught) ? 'timeout' : 'error', detail: isTimeout(caught) ? `no answer in ${TIMEOUT_MS} ms` : describe(caught) };
  }
}

// -- running them all and the report -----------------------------------------------------------------------------------------------------------

export type ProbeRunner = (tg: TelegramWebApp | undefined) => Promise<ProbeResult>;

const RUNNERS: Record<ProbeId, ProbeRunner> = {
  environment: (tg) => probeEnvironment(tg),
  webcrypto: () => probeWebCrypto(),
  pbkdf2: () => probePbkdf2(),
  argon2: () => probeArgon2(),
  cloud_storage: (tg) => probeCloudStorage(tg),
  cloud_limits: (tg) => probeCloudLimits(tg),
  secure_storage: (tg) => probeSecureStorage(tg),
  device_storage: (tg) => probeDeviceStorage(tg),
  biometric: (tg) => probeBiometric(tg),
};

export function runProbe(id: ProbeId, tg: TelegramWebApp | undefined = telegramApp()): Promise<ProbeResult> {
  return RUNNERS[id](tg);
}

/** One block of plain text the owner copies into the chat: the table of what works on this phone. */
export function buildReport(results: ProbeResult[], markers: MarkerResult[], notes: string[], context: { when: string; userAgent: string }): string {
  const lines = [`EN-1 report ${context.when}`, `ua=${context.userAgent.slice(0, 140)}`, ''];
  for (const id of AUTOMATIC_PROBES) {
    const result = results.find((entry) => entry.id === id);
    lines.push(result ? `${id}: ${result.status}${result.ms !== undefined ? ` (${result.ms} ms)` : ''} | ${result.detail}` : `${id}: not run`);
  }
  if (notes.length > 0) lines.push('', 'taps:', ...notes);
  if (markers.length > 0) {
    lines.push('', 'markers:');
    for (const marker of markers) lines.push(`${marker.kind}.${marker.action}: ${marker.status} | ${marker.detail}`);
  }
  return lines.join('\n');
}
