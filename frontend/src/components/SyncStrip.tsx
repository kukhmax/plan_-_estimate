import { useEffect, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { useOutboxCounts, useSyncInfo } from '../offline/outboxState';
import { Ico } from './Ico';

const SHOW_SENT_MS = 60_000;

/**
 * What happens to the changes made on the phone (Stage 19C): waiting, being sent, refused by the server, sent. A status strip under the
 * connection strip; it is empty when nothing waits and nothing was sent a moment ago.
 */
export function SyncStrip() {
  const { t } = useI18n();
  const { pending, failed } = useOutboxCounts();
  const { running, lastSent, needsLogin } = useSyncInfo();
  const [now, setNow] = useState(() => Date.now());
  const o = t.offline;

  // "sent" is shown for a minute after the sending
  useEffect(() => {
    if (!lastSent) return;
    setNow(Date.now());
    const timer = setTimeout(() => setNow(Date.now()), SHOW_SENT_MS + 50);
    return () => clearTimeout(timer);
  }, [lastSent]);
  const showSent = lastSent !== null && pending === 0 && now - lastSent.at < SHOW_SENT_MS;

  if (pending === 0 && failed === 0 && !showSent && !needsLogin) return null;
  const line = 'w-full mb-3 rounded-xl border px-3 py-2 text-xs font-medium break-words';
  return (
    <div aria-label="sync-strip" className="w-full">
      {pending > 0 && (
        <p role="status" aria-label="sync-pending" className={`${line} border-sky-300 bg-sky-50 text-sky-900`}>
          <Ico>{running ? '🔄' : '⏳'}</Ico>
          {running ? o.sync_sending : o.sync_pending.replace('{n}', String(pending))}
        </p>
      )}
      {failed > 0 && (
        <p role="alert" aria-label="sync-failed" className={`${line} border-red-300 bg-red-50 text-red-800`}>
          <Ico>⚠️</Ico>
          {o.sync_failed.replace('{n}', String(failed))}
        </p>
      )}
      {needsLogin && (
        <p role="alert" aria-label="sync-login" className={`${line} border-red-300 bg-red-50 text-red-800`}>
          <Ico>🔑</Ico>
          {o.sync_login}
        </p>
      )}
      {showSent && lastSent && (
        <div className={`${line} border-emerald-300 bg-emerald-50 text-emerald-900 flex items-center gap-2 flex-wrap`}>
          <span role="status" aria-label="sync-sent" className="min-w-0 flex-1">
            <Ico>✅</Ico>
            {o.sync_sent.replace('{n}', String(lastSent.count))}
          </span>
          <button
            type="button"
            aria-label="sync-refresh"
            onClick={() => window.location.reload()}
            className="min-h-10 px-3 py-1 text-xs rounded-xl bg-emerald-600 text-white font-semibold"
          >
            <Ico>🔄</Ico>
            {o.sync_refresh}
          </button>
        </div>
      )}
    </div>
  );
}
