import { useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { documentErrorText } from '../utils/documentErrors';
import { Ico } from './Ico';

interface JournalRowDeleteProps {
  /** What the owner sees in the question: the kind and the number of the document. */
  name: string;
  /** Deletes the row; rejects with the error of the server. */
  run: () => Promise<void>;
  /** The row is gone: the host takes it out of its list. */
  onDeleted: () => void;
  onCancel: () => void;
}

/**
 * The question before a row of the journal of the sent documents is deleted (DJ-1). It says what goes (the line of the journal) and what stays
 * (the document itself and the PDF in the chat with the bot); nothing is deleted until the owner has ticked "I understand" and confirmed.
 */
export function JournalRowDelete({ name, run, onDeleted, onCancel }: JournalRowDeleteProps) {
  const { t } = useI18n();
  const text = t.documents;
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    if (busy || !understood) return;
    setBusy(true);
    setError(null);
    try {
      await run();
      onDeleted();
    } catch (caught) {
      setError(documentErrorText(text.errors, caught));
      setBusy(false);
    }
  };

  return (
    <div role="alertdialog" aria-label={text.journal_delete_title} className="space-y-3 rounded-xl border border-red-300 p-3">
      <p className="break-words text-sm font-semibold text-slate-900">{text.journal_delete_title}</p>
      <p className="break-words text-sm text-slate-700">{text.journal_delete_intro.replace('{name}', name)}</p>
      <label className="flex min-h-11 items-start gap-3 text-sm font-semibold text-slate-700">
        <input
          type="checkbox"
          aria-label="journal-delete-understood"
          checked={understood}
          disabled={busy}
          onChange={(event) => setUnderstood(event.target.checked)}
          className="mt-0.5 h-6 w-6 shrink-0"
        />
        <span className="break-words">{text.journal_delete_ack}</span>
      </label>
      {error && <p role="alert" className="break-words text-sm text-red-700">{error}</p>}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          aria-label="journal-delete-cancel"
          disabled={busy}
          onClick={onCancel}
          className="w-full min-h-11 rounded-xl bg-blue-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          <Ico>✖️</Ico>{t.common.cancel}
        </button>
        <button
          type="button"
          aria-label="journal-delete-confirm"
          disabled={busy || !understood}
          onClick={() => void confirm()}
          className="w-full min-h-11 rounded-xl border border-red-600 bg-red-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          <Ico>🗑️</Ico>{busy ? t.archive.project_deleting : t.archive.project_delete_confirm}
        </button>
      </div>
    </div>
  );
}
