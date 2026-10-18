import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import * as probe from '../security/probe';
import type { MarkerResult, ProbeId, ProbeResult } from '../security/probe';
import { SecurityProbe } from './SecurityProbe';

vi.mock('../security/probe', async (original) => ({
  ...(await original<typeof import('../security/probe')>()),
  runProbe: vi.fn(),
  askBiometricAccess: vi.fn(),
  authenticateBiometric: vi.fn(),
  markerAction: vi.fn(),
}));

const answers: Record<ProbeId, ProbeResult> = {
  environment: { id: 'environment', status: 'ok', detail: 'version=9.1; platform=android', ms: 2 },
  webcrypto: { id: 'webcrypto', status: 'ok', detail: 'aes256gcm_roundtrip=true', ms: 5 },
  pbkdf2: { id: 'pbkdf2', status: 'ok', detail: 'sha256 600000=412ms', ms: 900 },
  argon2: { id: 'argon2', status: 'error', detail: 'argon2id m64MiB_t3=FAILED(oom)', ms: 3000 },
  cloud_storage: { id: 'cloud_storage', status: 'ok', detail: 'set=true; get=same', ms: 120 },
  cloud_limits: { id: 'cloud_limits', status: 'ok', detail: '1024=accepted; 4097=refused', ms: 300 },
  secure_storage: { id: 'secure_storage', status: 'unsupported', detail: 'SecureStorage=absent', ms: 0 },
  device_storage: { id: 'device_storage', status: 'timeout', detail: 'no answer in 8000 ms', ms: 8001 },
  biometric: { id: 'biometric', status: 'denied', detail: 'available=true; access_granted=false', ms: 40 },
};

function renderScreen() {
  return render(<I18nProvider><SecurityProbe /></I18nProvider>);
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(probe.runProbe).mockImplementation(async (id) => answers[id]);
  vi.mocked(probe.askBiometricAccess).mockResolvedValue({ id: 'biometric', status: 'ok', detail: 'access_granted=true' });
  vi.mocked(probe.authenticateBiometric).mockResolvedValue({ id: 'biometric', status: 'denied', detail: 'authenticated=false' });
  vi.mocked(probe.markerAction).mockImplementation(async (kind, action): Promise<MarkerResult> => ({ kind, action, status: 'ok', detail: `${kind}-${action}` }));
});

describe('SecurityProbe (EN-1)', () => {
  it('shows the nine checks as "not run" before anything is started, and says it touches no client data', () => {
    renderScreen();
    expect(screen.getByRole('heading', { name: 'Test zabezpieczeń (EN-1)' })).toBeInTheDocument();
    expect(screen.getByText(/Nie dotyka danych klientów/)).toBeInTheDocument();
    expect(within(screen.getByLabelText('probe-results')).getAllByRole('listitem')).toHaveLength(9);
    for (const id of probe.AUTOMATIC_PROBES) expect(screen.getByLabelText(`probe-${id}`)).toHaveTextContent('nie uruchomiono');
    expect(probe.runProbe).not.toHaveBeenCalled();
  });

  it('runs every check in its order with the Telegram app of the page, and shows status, values and time of each', async () => {
    renderScreen();
    fireEvent.click(screen.getByLabelText('probe-run-all'));
    await waitFor(() => expect(screen.getByLabelText('probe-status-biometric')).toBeInTheDocument());
    expect(vi.mocked(probe.runProbe).mock.calls.map((call) => call[0])).toEqual([...probe.AUTOMATIC_PROBES]);
    expect(screen.getByLabelText('probe-status-environment')).toHaveTextContent('działa');
    expect(screen.getByLabelText('probe-status-argon2')).toHaveTextContent('błąd');
    expect(screen.getByLabelText('probe-status-secure_storage')).toHaveTextContent('brak');
    expect(screen.getByLabelText('probe-status-device_storage')).toHaveTextContent('brak odpowiedzi');
    expect(screen.getByLabelText('probe-status-biometric')).toHaveTextContent('odmowa / pusto');
    expect(screen.getByLabelText('probe-detail-argon2')).toHaveTextContent('FAILED(oom)');
    expect(screen.getByLabelText('probe-detail-pbkdf2')).toHaveTextContent('600000=412ms');
    expect(screen.getByLabelText('probe-pbkdf2')).toHaveTextContent('900 ms');
  });

  it('keeps the button off while it runs and starts again from a clean table', async () => {
    renderScreen();
    fireEvent.click(screen.getByLabelText('probe-run-all'));
    expect(screen.getByLabelText('probe-run-all')).toBeDisabled();
    await waitFor(() => expect(screen.getByLabelText('probe-run-all')).toBeEnabled());
    fireEvent.click(screen.getByLabelText('probe-run-all'));
    await waitFor(() => expect(screen.getByLabelText('probe-run-all')).toBeEnabled());
    expect(probe.runProbe).toHaveBeenCalledTimes(18);
  });

  it('a second run starts from a clean table: the old answers are gone while the new ones are awaited', async () => {
    renderScreen();
    fireEvent.click(screen.getByLabelText('probe-run-all'));
    await waitFor(() => expect(screen.getByLabelText('probe-run-all')).toBeEnabled());
    expect(screen.getByLabelText('probe-status-argon2')).toHaveTextContent('błąd');
    vi.mocked(probe.runProbe).mockImplementation(() => new Promise<ProbeResult>(() => undefined)); // never answers
    fireEvent.click(screen.getByLabelText('probe-run-all'));
    await waitFor(() => expect(screen.getByLabelText('probe-environment')).toHaveTextContent('liczy…'));
    expect(screen.queryByLabelText('probe-status-argon2')).toBeNull();
    expect(screen.queryByLabelText('probe-status-environment')).toBeNull();
    expect(screen.getByLabelText('probe-argon2')).toHaveTextContent('nie uruchomiono');
  });

  it('the report lists every result and the checks that were not run', async () => {
    renderScreen();
    fireEvent.click(screen.getByLabelText('probe-run-all'));
    await waitFor(() => expect(screen.getByLabelText('probe-run-all')).toBeEnabled());
    const report = (screen.getByLabelText('probe-report') as HTMLTextAreaElement).value;
    expect(report).toContain('environment: ok (2 ms) | version=9.1; platform=android');
    expect(report).toContain('argon2: error (3000 ms) | argon2id m64MiB_t3=FAILED(oom)');
    expect(report).toContain('device_storage: timeout');
  });

  it('asks for the biometric access and checks the finger on a tap, and puts both answers in the report', async () => {
    renderScreen();
    fireEvent.click(screen.getByLabelText('probe-biometric-access'));
    await waitFor(() => expect(screen.getByLabelText('probe-last-tap')).toHaveTextContent('biometric.request_access: ok | access_granted=true'));
    fireEvent.click(screen.getByLabelText('probe-biometric-authenticate'));
    await waitFor(() => expect(screen.getByLabelText('probe-last-tap')).toHaveTextContent('biometric.authenticate: denied | authenticated=false'));
    const report = (screen.getByLabelText('probe-report') as HTMLTextAreaElement).value;
    expect(report).toContain('taps:');
    expect(report).toContain('biometric.request_access: ok | access_granted=true');
    expect(report).toContain('biometric.authenticate: denied | authenticated=false');
  });

  it.each(['cloud', 'secure', 'device'] as const)('%s: the three marker buttons act on that storage only and show the answer', async (kind) => {
    renderScreen();
    for (const action of ['write', 'read', 'clear'] as const) {
      fireEvent.click(screen.getByLabelText(`marker-${kind}-${action}`));
      await waitFor(() => expect(probe.markerAction).toHaveBeenLastCalledWith(kind, action));
      await waitFor(() => expect(screen.getByLabelText(`marker-${kind}-result`)).toHaveTextContent(`${kind}-${action}`));
    }
    expect(probe.markerAction).toHaveBeenCalledTimes(3);
    const report = (screen.getByLabelText('probe-report') as HTMLTextAreaElement).value;
    expect(report).toContain(`markers:\n${kind}.clear: ok | ${kind}-clear`);
  });

  it('copies the report and says so; when the phone refuses it says to copy by hand', async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: write }, configurable: true });
    renderScreen();
    fireEvent.click(screen.getByLabelText('probe-copy'));
    expect(await screen.findByRole('status')).toHaveTextContent('Skopiowano');
    expect(String(write.mock.calls[0][0])).toMatch(/^EN-1 report \d{4}-\d{2}-\d{2}T.*\nua=/);
    expect(String(write.mock.calls[0][0])).toContain('environment: not run');
    write.mockRejectedValue(new Error('denied'));
    fireEvent.click(screen.getByLabelText('probe-copy'));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('ręcznie'));
  });

  it('speaks Russian', () => {
    localStorage.setItem('locale', 'ru');
    renderScreen();
    expect(screen.getByRole('heading', { name: 'Тест защиты (EN-1)' })).toBeInTheDocument();
    expect(screen.getByLabelText('probe-run-all')).toHaveTextContent('Запустить тесты');
    expect(screen.getByLabelText('probe-secure_storage')).toHaveTextContent('SecureStorage (защищённое хранилище)');
    expect(screen.getByLabelText('marker-cloud')).toHaveTextContent('CloudStorage (облако Telegram)');
  });

  it('every button is at least 44 px high and the long values wrap instead of widening the page', () => {
    renderScreen();
    for (const button of screen.getAllByRole('button')) expect(button.className, button.getAttribute('aria-label') ?? '').toContain('min-h-11');
    expect(screen.getByLabelText('probe-report').className).toContain('w-full');
  });
});
