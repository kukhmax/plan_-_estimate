import { useEffect, useRef, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { useConnection } from '../offline/connection';
import { lastPrepared, prepareProjectOffline, type PrepareProgress } from '../offline/prepareProject';
import { Ico } from './Ico';

const TAGS: Record<string, string> = { pl: 'pl-PL', ru: 'ru-RU' };

interface PrepareOfflineButtonProps {
  projectId: string;
}

type Outcome = { saved: number; failed: number } | null;

/** "Przygotuj do pracy offline" on an object: keeps everything needed on site on the phone, before the signal is lost (Stage 19B). */
export function PrepareOfflineButton({ projectId }: PrepareOfflineButtonProps) {
  const { t, locale } = useI18n();
  const { offline } = useConnection();
  const [progress, setProgress] = useState<PrepareProgress | null>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [last, setLast] = useState<number | null>(null);
  const alive = useRef(true);
  const running = progress !== null;

  useEffect(() => {
    alive.current = true;
    void lastPrepared(projectId).then((note) => alive.current && setLast(note?.at ?? null));
    return () => {
      alive.current = false;
    };
  }, [projectId]);

  const start = async () => {
    setOutcome(null);
    setProgress({ done: 0, total: 0 });
    const result = await prepareProjectOffline(projectId, (next) => alive.current && setProgress(next), () => !alive.current);
    if (!alive.current) return;
    setProgress(null);
    setOutcome(result);
    if (result.failed === 0) setLast(Date.now());
  };

  const fmt = (ms: number) => new Date(ms).toLocaleString(TAGS[locale] ?? locale, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  const o = t.offline;

  return (
    <section aria-label="prepare-offline" className="pe-card rounded-2xl p-3 shadow-sm space-y-2">
      <button
        type="button"
        aria-label="prepare-offline-button"
        disabled={running || offline}
        onClick={() => void start()}
        className="w-full min-h-11 px-4 py-1 text-sm rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 font-semibold hover:bg-emerald-100 transition disabled:opacity-50"
      >
        <Ico>📥</Ico>
        {o.prepare_button}
      </button>
      <p className="text-xs text-slate-500 break-words">{o.prepare_hint}</p>
      {offline && <p className="text-xs text-amber-800 break-words">{o.prepare_needs_connection}</p>}
      {running && (
        <p role="status" aria-label="prepare-progress" className="text-xs font-medium text-slate-700 break-words">
          {o.prepare_running.replace('{done}', String(progress.done)).replace('{total}', String(progress.total))}
        </p>
      )}
      {outcome && outcome.failed === 0 && (
        <p role="status" className="text-xs font-medium text-emerald-700 break-words">{o.prepare_done.replace('{saved}', String(outcome.saved))}</p>
      )}
      {outcome && outcome.failed > 0 && (
        <p role="alert" className="text-xs font-medium text-red-600 break-words">
          {o.prepare_partial.replace('{saved}', String(outcome.saved)).replace('{failed}', String(outcome.failed))}
        </p>
      )}
      {last !== null && !running && <p className="text-xs text-slate-500 break-words">{o.prepare_last.replace('{time}', fmt(last))}</p>}
    </section>
  );
}
