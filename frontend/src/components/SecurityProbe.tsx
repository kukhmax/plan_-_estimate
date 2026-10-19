import { useRef, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import {
  AUTOMATIC_PROBES,
  askBiometricAccess,
  authenticateBiometric,
  buildReport,
  markerAction,
  runProbe,
  telegramApp,
  type MarkerResult,
  type ProbeId,
  type ProbeResult,
  type ProbeStatus,
  type StorageKind,
} from '../security/probe';
import { Ico } from './Ico';

const STATUS_STYLE: Record<ProbeStatus, string> = {
  ok: 'bg-emerald-100 text-emerald-800',
  unsupported: 'bg-slate-200 text-slate-700',
  error: 'bg-red-100 text-red-800',
  timeout: 'bg-amber-100 text-amber-800',
  denied: 'bg-amber-100 text-amber-800',
};
const STATUS_ICON: Record<ProbeStatus, string> = { ok: '✅', unsupported: '➖', error: '❌', timeout: '⏱️', denied: '⚠️' };
const STORAGES: StorageKind[] = ['cloud', 'secure', 'device'];

const button = 'w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-slate-300 pe-surface text-slate-900 hover:bg-slate-50 disabled:opacity-50 transition break-words';
const primary = 'w-full min-h-11 px-3 text-sm font-semibold rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition break-words';

/**
 * EN-1 -- the test page of the encryption spike: it asks THIS phone what its Telegram can keep and how fast it computes, with no data of a client
 * (see `security/probe.ts`). The owner runs it, copies the report and sends it; V2 (the key of the owner) is designed from that, not from a document.
 */
export function SecurityProbe() {
  const { t } = useI18n();
  const text = t.securityProbe;
  const [results, setResults] = useState<Partial<Record<ProbeId, ProbeResult>>>({});
  const [running, setRunning] = useState<ProbeId | 'all' | null>(null);
  const [markers, setMarkers] = useState<Partial<Record<StorageKind, MarkerResult>>>({});
  const [notes, setNotes] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [copyNote, setCopyNote] = useState<string | null>(null);
  const alive = useRef(true);

  const runAll = async () => {
    if (running) return;
    setRunning('all');
    setResults({});
    const tg = telegramApp();
    for (const id of AUTOMATIC_PROBES) {
      setRunning(id);
      const result = await runProbe(id, tg);
      if (!alive.current) return;
      setResults((current) => ({ ...current, [id]: result }));
    }
    setRunning(null);
  };

  const tap = async (key: string, label: string, run: () => Promise<ProbeResult>) => {
    if (busy) return;
    setBusy(key);
    const result = await run();
    setNotes((current) => [...current, `${label}: ${result.status} | ${result.detail}`]);
    setBusy(null);
  };

  const marker = async (kind: StorageKind, action: MarkerResult['action']) => {
    if (busy) return;
    setBusy(`${kind}-${action}`);
    const result = await markerAction(kind, action);
    setMarkers((current) => ({ ...current, [kind]: result }));
    setBusy(null);
  };

  const report = buildReport(
    Object.values(results) as ProbeResult[],
    Object.values(markers) as MarkerResult[],
    notes,
    { when: new Date().toISOString(), userAgent: typeof navigator === 'undefined' ? '' : navigator.userAgent },
  );

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(report);
      setCopyNote(text.copied);
    } catch {
      setCopyNote(text.copy_manual);
    }
  };

  const statusWord = (status: ProbeStatus) => text.status[status];
  const lastTap = notes.length > 0 ? notes[notes.length - 1] : null;

  return (
    <section aria-label="security-probe" className="w-full mt-4 space-y-3">
      <h2 className="text-lg font-bold text-[var(--tg-theme-text-color)]">{text.title}</h2>
      <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{text.intro}</p>

      <button type="button" aria-label="probe-run-all" disabled={running !== null} onClick={() => void runAll()} className={primary}>
        <Ico>▶️</Ico>{running !== null ? text.running : text.run_all}
      </button>

      <ul aria-label="probe-results" className="space-y-2">
        {AUTOMATIC_PROBES.map((id) => {
          const result = results[id];
          return (
            <li key={id} aria-label={`probe-${id}`} className="pe-card rounded-2xl p-3 shadow-sm space-y-1">
              <div className="flex items-start justify-between gap-2">
                <span className="min-w-0 break-words text-sm font-semibold text-slate-900">{text.checks[id]}</span>
                {result ? (
                  <span aria-label={`probe-status-${id}`} className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_STYLE[result.status]}`}>
                    {STATUS_ICON[result.status]} {statusWord(result.status)}
                  </span>
                ) : (
                  <span className="shrink-0 text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 font-medium">
                    {running === id ? text.running_one : text.not_run}
                  </span>
                )}
              </div>
              {result && (
                <>
                  <p aria-label={`probe-detail-${id}`} className="text-xs text-slate-700 break-all">{result.detail}</p>
                  {result.ms !== undefined && <p className="text-xs text-slate-500">{result.ms} ms</p>}
                </>
              )}
            </li>
          );
        })}
      </ul>

      <div className="pe-card rounded-2xl p-3 shadow-sm space-y-2">
        <p className="text-sm font-semibold text-slate-900 break-words">{text.biometric_title}</p>
        <p className="text-xs text-slate-600 break-words">{text.biometric_hint}</p>
        <button type="button" aria-label="probe-biometric-access" disabled={busy !== null} onClick={() => void tap('access', 'biometric.request_access', () => askBiometricAccess())} className={button}>
          <Ico>🔐</Ico>{text.biometric_access}
        </button>
        <button type="button" aria-label="probe-biometric-authenticate" disabled={busy !== null} onClick={() => void tap('auth', 'biometric.authenticate', () => authenticateBiometric())} className={button}>
          <Ico>🖐️</Ico>{text.biometric_authenticate}
        </button>
        {lastTap && <p aria-label="probe-last-tap" className="text-xs text-slate-700 break-all">{lastTap}</p>}
      </div>

      <div className="pe-card rounded-2xl p-3 shadow-sm space-y-3">
        <p className="text-sm font-semibold text-slate-900 break-words">{text.markers_title}</p>
        <p className="text-xs text-slate-600 break-words">{text.markers_hint}</p>
        {STORAGES.map((kind) => (
          <div key={kind} aria-label={`marker-${kind}`} className="space-y-2 border-t border-slate-100 pt-2">
            <p className="text-sm font-medium text-slate-900 break-words">{text.storage[kind]}</p>
            <button type="button" aria-label={`marker-${kind}-write`} disabled={busy !== null} onClick={() => void marker(kind, 'write')} className={button}>{text.marker_write}</button>
            <button type="button" aria-label={`marker-${kind}-read`} disabled={busy !== null} onClick={() => void marker(kind, 'read')} className={button}>{text.marker_read}</button>
            <button type="button" aria-label={`marker-${kind}-clear`} disabled={busy !== null} onClick={() => void marker(kind, 'clear')} className={button}>{text.marker_clear}</button>
            {markers[kind] && (
              <p aria-label={`marker-${kind}-result`} className="text-xs text-slate-700 break-all">
                {STATUS_ICON[markers[kind]!.status]} {text.marker_action[markers[kind]!.action]}: {statusWord(markers[kind]!.status)} — {markers[kind]!.detail}
              </p>
            )}
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <p className="text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">{text.report_title}</p>
        <textarea
          aria-label="probe-report"
          readOnly
          value={report}
          rows={10}
          className="w-full border border-slate-200 rounded-xl px-3 py-2 text-xs font-mono text-slate-900 pe-surface"
        />
        <button type="button" aria-label="probe-copy" onClick={() => void copy()} className={button}>
          <Ico>📋</Ico>{text.copy}
        </button>
        {copyNote && <p role="status" className="text-sm text-emerald-700 break-words">{copyNote}</p>}
      </div>
    </section>
  );
}
