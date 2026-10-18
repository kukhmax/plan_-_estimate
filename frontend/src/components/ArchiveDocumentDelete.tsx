import { useEffect, useState } from 'react';
import { fetchDocumentPurgePreview, purgeArchivedDocument } from '../api/archivedDocuments';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import type { ArchivedDocumentItem, DocumentPurgePreview } from '../types/archivedDocument';
import { archivedDocumentKindLabel } from '../utils/archivedDocumentFormat';
import { Ico } from './Ico';

interface ArchiveDocumentDeleteProps {
  document: ArchivedDocumentItem;
  /** The record is gone: the host takes it out of its list. */
  onDeleted: () => void;
  onCancel: () => void;
}

/**
 * The confirmation of deleting an archived contract / protocol for good (AC-6). The server says what the deletion does (the lines of the
 * journal of sent documents stay; a contract that protocols still refer to is refused) before anything is asked; nothing is deleted until
 * the owner has read it, ticked "I understand" and confirmed.
 */
export function ArchiveDocumentDelete({ document, onDeleted, onCancel }: ArchiveDocumentDeleteProps) {
  const { t } = useI18n();
  const text = t.archive;
  const [preview, setPreview] = useState<DocumentPurgePreview | null>(null);
  const [failed, setFailed] = useState<'load' | 'delete' | 'in_use' | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setPreview(null);
    setFailed(null);
    setUnderstood(false);
    let cancelled = false;
    fetchDocumentPurgePreview(document.kind, document.id)
      .then((value) => {
        if (!cancelled) setPreview(value);
      })
      .catch(() => {
        if (!cancelled) setFailed('load');
      });
    return () => {
      cancelled = true;
    };
  }, [document.kind, document.id]);

  const confirm = async () => {
    if (busy || !understood) return;
    setBusy(true);
    setFailed(null);
    try {
      await purgeArchivedDocument(document.kind, document.id);
      onDeleted();
    } catch (caught) {
      setFailed(caught instanceof ApiError && caught.code === 'DOCUMENT_RECORD_IN_USE' ? 'in_use' : 'delete');
      setUnderstood(false);
      setBusy(false);
    }
  };

  const lines: string[] = [];
  if (preview) {
    if (preview.journal_lines > 0) lines.push(text.document_delete_journal.replace('{count}', String(preview.journal_lines)));
    if (preview.issued) lines.push(text.document_delete_pdf);
  }
  const blocked = preview !== null && preview.dependents > 0;
  const intro = text.document_delete_intro.replace('{name}', `${archivedDocumentKindLabel(text, document.kind)} · ${document.project_name}`);

  return (
    <div role="alertdialog" aria-label={text.document_delete_title} className="space-y-3 rounded-xl border border-red-300 p-3">
      <p className="break-words text-sm font-semibold text-slate-900">{text.document_delete_title}</p>
      {preview === null && failed !== 'load' && <p role="status" className="break-words text-sm text-slate-500">{text.client_delete_loading}</p>}
      {preview !== null && (
        <div className="space-y-2 break-words text-sm text-slate-700">
          <p>{intro}</p>
          {blocked ? (
            <p role="alert" className="text-red-700">{text.document_delete_blocked.replace('{count}', String(preview.dependents))}</p>
          ) : (
            <>
              {lines.length > 0 ? (
                <ul aria-label="document-delete-lines" className="list-disc pl-5">
                  {lines.map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              ) : (
                <p>{text.document_delete_nothing}</p>
              )}
              <label className="flex min-h-11 items-start gap-3 font-semibold">
                <input
                  type="checkbox"
                  aria-label="document-delete-understood"
                  checked={understood}
                  disabled={busy}
                  onChange={(event) => setUnderstood(event.target.checked)}
                  className="mt-0.5 h-6 w-6 shrink-0"
                />
                <span>{text.project_delete_ack}</span>
              </label>
            </>
          )}
        </div>
      )}
      {failed === 'load' && <p role="alert" className="break-words text-sm text-red-700">{text.error_load}</p>}
      {failed === 'delete' && <p role="alert" className="break-words text-sm text-red-700">{text.structure_delete_error}</p>}
      {failed === 'in_use' && <p role="alert" className="break-words text-sm text-red-700">{text.document_delete_in_use}</p>}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          aria-label="document-delete-cancel"
          disabled={busy}
          onClick={onCancel}
          className="w-full min-h-11 rounded-xl bg-blue-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          <Ico>✖️</Ico>{text.client_delete_cancel}
        </button>
        <button
          type="button"
          aria-label="document-delete-confirm"
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
