import { useI18n } from '../hooks/useI18n';
import { Ico } from './Ico';

/**
 * "Czeka na wysłanie": a record the phone made (or changed) that the server has not accepted yet (Stage 19E). Nothing is drawn for a
 * record the server knows.
 */
export function PendingMark({ record, id }: { record: { _pending?: boolean } | null | undefined; id?: string }) {
  const { t } = useI18n();
  if (!record?._pending) return null;
  return (
    <span
      aria-label={id ? `pending-mark-${id}` : 'pending-mark'}
      className="shrink-0 text-[11px] px-2 py-0.5 rounded-full bg-sky-100 text-sky-900 font-medium break-words"
    >
      <Ico>⏳</Ico>
      {t.offline.pending_mark}
    </span>
  );
}
