import { useEffect, useState } from 'react';
import { fetchPaymentPurgePreview, purgePayment } from '../api/payments';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import type { ArchivedPaymentItem, PaymentPurgePreview, PaymentPurgeResult } from '../types/payment';
import { formatSize } from '../utils/documentFormat';
import { formatMoney } from '../utils/paymentFormat';
import { Ico } from './Ico';

interface ArchivePaymentDeleteProps {
  payment: ArchivedPaymentItem;
  /** The record is gone: the host takes it out of its list. */
  onDeleted: (result: PaymentPurgeResult) => void;
  onCancel: () => void;
}

/**
 * The confirmation of deleting an archived settlement record for good (IA-7). The server counts what goes (the receipt / invoice photos and
 * their files, the payments that lose the link to a deleted invoice) before anything is asked; nothing is deleted until the owner has read
 * it, ticked "I understand" and confirmed.
 */
export function ArchivePaymentDelete({ payment, onDeleted, onCancel }: ArchivePaymentDeleteProps) {
  const { t } = useI18n();
  const text = t.archive;
  const [preview, setPreview] = useState<PaymentPurgePreview | null>(null);
  const [failed, setFailed] = useState<'load' | 'delete' | 'conflict' | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = () => fetchPaymentPurgePreview(payment.project_id, payment.id).then(setPreview).catch(() => setFailed('load'));

  useEffect(() => {
    setPreview(null);
    setFailed(null);
    setUnderstood(false);
    let cancelled = false;
    fetchPaymentPurgePreview(payment.project_id, payment.id)
      .then((value) => {
        if (!cancelled) setPreview(value);
      })
      .catch(() => {
        if (!cancelled) setFailed('load');
      });
    return () => {
      cancelled = true;
    };
  }, [payment.project_id, payment.id]);

  const confirm = async () => {
    if (busy || !understood) return;
    setBusy(true);
    setFailed(null);
    try {
      onDeleted(await purgePayment(payment.project_id, payment.id));
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'PAYMENT_PURGE_CONFLICT') {
        setFailed('conflict');
        setUnderstood(false);
        void load();
      } else {
        setFailed('delete');
      }
      setBusy(false);
    }
  };

  const lines: string[] = [];
  if (preview) {
    if (preview.photos > 0) {
      lines.push(
        text.project_delete_photos
          .replace('{count}', String(preview.photos))
          .replace('{files}', String(preview.photo_files))
          .replace('{size}', formatSize(preview.bytes)),
      );
    }
    if (preview.annotations > 0) lines.push(text.project_delete_markers.replace('{count}', String(preview.annotations)));
    if (preview.tied_payments > 0) lines.push(text.payment_delete_tied.replace('{count}', String(preview.tied_payments)));
  }
  const intro = text.payment_delete_intro.replace('{name}', `${payment.title} (${formatMoney(payment.amount_gross)})`);

  return (
    <div role="alertdialog" aria-label={text.payment_delete_title} className="space-y-3 rounded-xl border border-red-300 p-3">
      <p className="break-words text-sm font-semibold text-slate-900">{text.payment_delete_title}</p>
      {preview === null && failed !== 'load' && <p role="status" className="break-words text-sm text-slate-500">{text.client_delete_loading}</p>}
      {preview !== null && (
        <div className="space-y-2 break-words text-sm text-slate-700">
          <p>{intro}</p>
          {lines.length > 0 ? (
            <ul aria-label="payment-delete-lines" className="list-disc pl-5">
              {lines.map((entry) => (
                <li key={entry}>{entry}</li>
              ))}
            </ul>
          ) : (
            <p>{text.payment_delete_nothing}</p>
          )}
          {preview.may_be_in_backups && <p className="text-slate-500">{text.project_delete_backups}</p>}
          <label className="flex min-h-11 items-start gap-3 font-semibold">
            <input
              type="checkbox"
              aria-label="payment-delete-understood"
              checked={understood}
              disabled={busy}
              onChange={(event) => setUnderstood(event.target.checked)}
              className="mt-0.5 h-6 w-6 shrink-0"
            />
            <span>{text.project_delete_ack}</span>
          </label>
        </div>
      )}
      {failed === 'load' && <p role="alert" className="break-words text-sm text-red-700">{text.error_load}</p>}
      {failed === 'delete' && <p role="alert" className="break-words text-sm text-red-700">{text.structure_delete_error}</p>}
      {failed === 'conflict' && <p role="alert" className="break-words text-sm text-red-700">{text.structure_delete_conflict}</p>}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          aria-label="payment-delete-cancel"
          disabled={busy}
          onClick={onCancel}
          className="w-full min-h-11 rounded-xl bg-blue-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          <Ico>✖️</Ico>{text.client_delete_cancel}
        </button>
        <button
          type="button"
          aria-label="payment-delete-confirm"
          disabled={busy || preview === null || !preview.can_purge || !understood}
          onClick={() => void confirm()}
          className="w-full min-h-11 rounded-xl border border-red-600 bg-red-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          <Ico>🗑️</Ico>{busy ? text.project_deleting : text.project_delete_confirm}
        </button>
      </div>
    </div>
  );
}
