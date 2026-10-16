import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { usePhotoUploadQueue } from '../hooks/usePhotoUploadQueue';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import { useConnection } from '../offline/connection';
import { refusalReason } from '../offline/describe';
import type { OutboxOp } from '../offline/opTypes';
import { listOps, removeOp, updateOp } from '../offline/outbox';
import { askForSending, useOutboxCounts, useSyncInfo } from '../offline/outboxState';
import { drainOutbox } from '../offline/sync';
import { formatRecordedDateTime } from '../utils/executionFormat';
import { Ico } from './Ico';
import { PhotoUploadQueueList } from './PhotoUploadQueueList';

const button =
  'min-h-11 px-3 py-2 text-sm rounded-xl border font-semibold break-words disabled:opacity-50';

/**
 * "Synchronizacja" (Stage 19E): everything made on the phone that the server has not got yet — the changes and the photos — and, apart
 * and first, what the server refused ("wymagają uwagi"): nothing is lost silently, each refused change can be sent again or removed.
 */
export function SyncScreen({ onClose }: { onClose: () => void }) {
  const { t, locale } = useI18n();
  const o = t.offline;
  const { pending, failed } = useOutboxCounts();
  const { running } = useSyncInfo();
  const { offline } = useConnection();
  const photos = usePhotoUploadQueue();
  const [ops, setOps] = useState<OutboxOp[]>([]);
  const [confirming, setConfirming] = useState<number | null>(null);

  useTelegramBackButton(true, onClose);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  // the list follows the counts (a change is added, sent, refused or removed)
  const reload = useCallback(() => {
    void listOps().then(setOps);
  }, []);
  useEffect(reload, [reload, pending, failed]);

  const refused = ops.filter((op) => op.status === 'failed');
  const waiting = ops.filter((op) => op.status === 'pending');
  const photoItems = photos.items.filter((item) => item.state !== 'done' && item.state !== 'canceled');
  const photoProblems = photoItems.filter((item) => item.state === 'failed');
  const photoWaiting = photoItems.filter((item) => item.state !== 'failed');
  const attention = refused.length + photoProblems.length;
  const nothing = waiting.length === 0 && photoWaiting.length === 0 && attention === 0;

  const label = (op: OutboxOp) => {
    const kind = (o.kinds as Record<string, string>)[op.kind] ?? op.kind;
    return op.label ? `${kind}: ${op.label}` : kind;
  };
  const madeAt = (op: OutboxOp) => o.sync_made_at.replace('{time}', formatRecordedDateTime(new Date(op.createdAt).toISOString(), locale));

  const retry = async (op: OutboxOp) => {
    if (op.seq === undefined) return;
    await updateOp(op.seq, { status: 'pending', attempts: 0, error: undefined });
    reload();
    askForSending(0);
  };
  const discard = async (op: OutboxOp) => {
    if (op.seq === undefined) return;
    await removeOp(op.seq);
    setConfirming(null);
    reload();
  };
  const syncNow = () => {
    void drainOutbox().finally(reload);
    photos.kick();
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-[var(--tg-theme-bg-color)]" aria-modal="true" role="dialog" aria-label="sync-screen">
      <div className="mx-auto w-full max-w-xl space-y-4 p-4 pb-10">
        <div className="flex items-start justify-between gap-2">
          <h2 className="min-w-0 flex-1 text-lg font-bold text-[var(--tg-theme-text-color)] break-words">
            <Ico>🔄</Ico>
            {o.sync_screen_title}
          </h2>
          <button
            type="button"
            aria-label="sync-close"
            onClick={onClose}
            className={`${button} shrink-0 border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]`}
          >
            <Ico>✖️</Ico>
            {o.sync_close}
          </button>
        </div>

        {offline && (
          <p role="status" aria-label="sync-screen-offline" className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-900 break-words">
            <Ico>📡</Ico>
            {o.sync_offline_note}
          </p>
        )}

        <button
          type="button"
          aria-label="sync-now"
          disabled={offline || running || (pending === 0 && photoWaiting.length === 0)}
          onClick={syncNow}
          className={`${button} w-full border-transparent bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]`}
        >
          <Ico>🔄</Ico>
          {o.sync_now}
        </button>

        {nothing && (
          <p role="status" aria-label="sync-nothing" className="text-sm text-[var(--tg-theme-hint-color)] break-words">
            <Ico>✅</Ico>
            {o.sync_nothing}
          </p>
        )}

        {attention > 0 && (
          <section aria-label="sync-attention" className="space-y-2">
            <h3 className="text-sm font-bold text-red-700 break-words">
              <Ico>⚠️</Ico>
              {o.sync_section_attention.replace('{n}', String(attention))}
            </h3>
            <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{o.sync_attention_hint}</p>
            <ul className="space-y-2">
              {refused.map((op) => (
                <li key={op.seq} aria-label={`sync-refused-${op.seq}`} className="space-y-2 rounded-xl border border-red-300 bg-red-50 p-3">
                  <p className="text-sm font-semibold text-red-900 break-words">{label(op)}</p>
                  <p className="text-xs text-red-800 break-words">{(o as Record<string, unknown>)[refusalReason(op.error)] as string}</p>
                  <p className="text-xs text-red-700 break-words">{madeAt(op)}</p>
                  {confirming === op.seq ? (
                    <div className="space-y-2">
                      <p role="alert" className="text-xs font-semibold text-red-900 break-words">{o.sync_discard_confirm}</p>
                      <div className="flex flex-wrap gap-2">
                        <button type="button" aria-label={`sync-discard-yes-${op.seq}`} onClick={() => void discard(op)} className={`${button} border-red-600 bg-red-600 text-white`}>
                          {o.sync_discard_yes}
                        </button>
                        <button type="button" aria-label={`sync-discard-no-${op.seq}`} onClick={() => setConfirming(null)} className={`${button} border-[var(--tg-control-border-color)] bg-white text-slate-800`}>
                          {t.common.cancel}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      <button type="button" aria-label={`sync-retry-${op.seq}`} onClick={() => void retry(op)} className={`${button} border-red-300 bg-white text-red-800`}>
                        <Ico>🔄</Ico>
                        {o.sync_retry}
                      </button>
                      <button type="button" aria-label={`sync-discard-${op.seq}`} onClick={() => setConfirming(op.seq ?? null)} className={`${button} border-red-300 bg-white text-red-800`}>
                        <Ico>🗑️</Ico>
                        {o.sync_discard}
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {photoProblems.length > 0 && (
              <PhotoUploadQueueList items={photoProblems} onCancel={photos.cancel} onRetry={photos.retry} onRetryAsNew={photos.retryAsNew} onDismiss={photos.dismiss} />
            )}
          </section>
        )}

        {waiting.length > 0 && (
          <section aria-label="sync-waiting" className="space-y-2">
            <h3 className="text-sm font-bold text-[var(--tg-theme-text-color)] break-words">
              <Ico>⏳</Ico>
              {o.sync_section_waiting.replace('{n}', String(waiting.length))}
            </h3>
            <ul className="space-y-2">
              {waiting.map((op) => (
                <li key={op.seq} aria-label={`sync-waiting-${op.seq}`} className="rounded-xl border border-sky-300 bg-sky-50 p-3">
                  <p className="text-sm font-semibold text-sky-900 break-words">{label(op)}</p>
                  <p className="text-xs text-sky-800 break-words">{madeAt(op)}</p>
                </li>
              ))}
            </ul>
          </section>
        )}

        {photoWaiting.length > 0 && (
          <section aria-label="sync-photos" className="space-y-2">
            <h3 className="text-sm font-bold text-[var(--tg-theme-text-color)] break-words">
              <Ico>📷</Ico>
              {o.sync_photos_title.replace('{n}', String(photoWaiting.length))}
            </h3>
            <PhotoUploadQueueList items={photoWaiting} onCancel={photos.cancel} onRetry={photos.retry} onRetryAsNew={photos.retryAsNew} onDismiss={photos.dismiss} />
          </section>
        )}
      </div>
    </div>
  );
}
