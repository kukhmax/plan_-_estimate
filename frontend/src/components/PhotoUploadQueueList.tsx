import { useI18n } from '../hooks/useI18n';
import { QueueItem } from '../utils/photoUploadQueue';

// One row per queued file: local preview, name, state / progress / localized error, and the allowed actions.
// Vertical stacking: the text block first, the action buttons wrap on their own line (never squeezed beside a name).

interface PhotoUploadQueueListProps {
  items: readonly QueueItem[];
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
  onRetryAsNew: (id: string) => void;
  onDismiss: (id: string) => void;
}

const actionClass =
  'min-h-11 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color)]';

export function PhotoUploadQueueList({ items, onCancel, onRetry, onRetryAsNew, onDismiss }: PhotoUploadQueueListProps) {
  const { t } = useI18n();
  if (items.length === 0) return null;

  const statusText = (item: QueueItem): string => {
    switch (item.state) {
      case 'queued':
        return t.photos.queue.waiting;
      case 'uploading':
        return t.photos.queue.uploading.replace('{percent}', String(Math.round(item.progress * 100)));
      case 'processing':
        return t.photos.queue.processing;
      case 'done':
        return t.photos.queue.done;
      case 'canceled':
        return t.photos.queue.canceled;
      default:
        return item.error ? t.photos.errors[item.error.key] : t.photos.queue.failed;
    }
  };

  return (
    <ul aria-label={t.photos.queue.title} className="space-y-2">
      {items.map((item) => {
        const active = item.state === 'queued' || item.state === 'uploading' || item.state === 'processing';
        const failed = item.state === 'failed';
        return (
          <li
            key={item.id}
            data-state={item.state}
            className="space-y-2 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] p-2.5"
          >
            <div className="flex min-w-0 items-start gap-2.5">
              {item.previewUrl ? (
                <img
                  src={item.previewUrl}
                  alt={t.photos.queue.preview_alt}
                  className="h-14 w-14 shrink-0 rounded-lg object-cover"
                />
              ) : (
                <div aria-hidden className="h-14 w-14 shrink-0 rounded-lg bg-[var(--tg-theme-bg-color)]" />
              )}
              <div className="min-w-0 flex-1 space-y-1">
                <p className="break-all text-xs text-[var(--tg-theme-hint-color)]">{item.file.name}</p>
                <p
                  role={failed ? 'alert' : 'status'}
                  className={`break-words text-sm ${
                    failed ? 'font-medium text-[var(--tg-theme-destructive-text-color)]' : 'text-[var(--tg-theme-text-color)]'
                  }`}
                >
                  {statusText(item)}
                </p>
                {(item.state === 'uploading' || item.state === 'processing') && (
                  <div
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(item.progress * 100)}
                    className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--tg-control-border-color)]"
                  >
                    <div
                      className="h-full rounded-full bg-[var(--tg-theme-accent-text-color)]"
                      style={{ width: `${Math.round(item.progress * 100)}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {active && (
                <button type="button" className={actionClass} onClick={() => onCancel(item.id)}>
                  {t.photos.queue.cancel}
                </button>
              )}
              {failed && item.error?.retryable && (
                <button type="button" className={actionClass} onClick={() => onRetry(item.id)}>
                  {t.photos.queue.retry}
                </button>
              )}
              {failed && item.error?.retryAsNew && (
                <button type="button" className={actionClass} onClick={() => onRetryAsNew(item.id)}>
                  {t.photos.queue.retry_as_new}
                </button>
              )}
              {!active && (
                <button type="button" className={actionClass} onClick={() => onDismiss(item.id)}>
                  {t.photos.queue.dismiss}
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
