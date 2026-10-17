import { useEffect, useState } from 'react';
import { ClientDeletePreview, deleteClient, fetchClientDeletePreview } from '../api/clients';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import { Ico } from './Ico';

interface ArchiveClientDeleteProps {
  clientId: string;
  clientName: string;
  /** The client is gone: the host takes it out of its list. */
  onDeleted: () => void;
  onCancel: () => void;
}

/**
 * The confirmation of deleting an archived client for good (archive cleanup AC-5a). The server counts what blocks it (the
 * client's objects, archived ones included) before anything is asked; nothing is deleted until the owner confirms.
 */
export function ArchiveClientDelete({ clientId, clientName, onDeleted, onCancel }: ArchiveClientDeleteProps) {
  const { t } = useI18n();
  const text = t.archive;
  const [preview, setPreview] = useState<ClientDeletePreview | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setFailed(false);
    fetchClientDeletePreview(clientId)
      .then((value) => {
        if (!cancelled) setPreview(value);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const confirm = async () => {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      await deleteClient(clientId);
      onDeleted();
    } catch (caught) {
      // an object appeared meanwhile: show the blocked state instead of a vague error
      if (caught instanceof ApiError && caught.code === 'CLIENT_HAS_PROJECTS') {
        const projects = (caught.detail as { projects?: number } | undefined)?.projects ?? 1;
        setPreview({ client_id: clientId, archived: true, projects, can_delete: false });
      } else {
        setFailed(true);
      }
      setBusy(false);
    }
  };

  const blocked = preview !== null && preview.projects > 0;
  return (
    <div role="alertdialog" aria-label={text.client_delete_title} className="space-y-3 rounded-xl border border-red-300 p-3">
      <p className="break-words text-sm font-semibold text-slate-900">{text.client_delete_title}</p>
      {preview === null && !failed && <p role="status" className="break-words text-sm text-slate-500">{text.client_delete_loading}</p>}
      {preview !== null && (
        <div className="space-y-2 break-words text-sm text-slate-700">
          {blocked ? (
            <p role="alert" className="text-red-700">{text.client_delete_blocked.replace('{count}', String(preview.projects))}</p>
          ) : (
            <>
              <p>{text.client_delete_text.replace('{name}', clientName)}</p>
              <p className="font-semibold">{text.client_delete_irreversible}</p>
            </>
          )}
        </div>
      )}
      {failed && <p role="alert" className="break-words text-sm text-red-700">{text.client_delete_error}</p>}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          aria-label="client-delete-cancel"
          disabled={busy}
          onClick={onCancel}
          className="w-full min-h-11 rounded-xl bg-blue-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          <Ico>✖️</Ico>{text.client_delete_cancel}
        </button>
        {!blocked && (
          <button
            type="button"
            aria-label="client-delete-confirm"
            disabled={busy || preview === null || !preview.can_delete}
            onClick={() => void confirm()}
            className="w-full min-h-11 rounded-xl border border-red-600 bg-red-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
          >
            <Ico>🗑️</Ico>{busy ? text.client_deleting : text.client_delete_confirm}
          </button>
        )}
      </div>
    </div>
  );
}
