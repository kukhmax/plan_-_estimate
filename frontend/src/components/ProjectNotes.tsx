import { FormEvent, useCallback, useEffect, useState } from 'react';
import { createProjectNote, deleteProjectNote, fetchProjectNotes, updateProjectNote } from '../api/projectNotes';
import { useI18n } from '../hooks/useI18n';
import { MAX_NOTE_LENGTH, type ProjectNote } from '../types/projectNote';
import { localizeApiError } from '../utils/apiErrors';
import { formatNoteTime } from '../utils/noteFormat';
import { Ico } from './Ico';
import { PendingMark } from './PendingMark';

interface ProjectNotesProps {
  projectId: string;
}

/**
 * The notes of an object (Stage 18): a field to write one, the list newest first with the day and the time each was written.
 * A note is changed in place and removed after a second tap; nothing here sends a message or leaves the application.
 */
export function ProjectNotes({ projectId }: ProjectNotesProps) {
  const { t, locale } = useI18n();
  const text = t.notes;
  const [notes, setNotes] = useState<ProjectNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [draft, setDraft] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      setNotes((await fetchProjectNotes(projectId)).items);
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const fail = (err: unknown, fallback: string) => {
    const localized = localizeApiError(err, t);
    setMessage({ kind: 'error', text: localized && !localized.startsWith('Request failed') ? localized : fallback });
  };

  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || draft.trim() === '') return;
    setBusy(true);
    setMessage(null);
    try {
      const created = await createProjectNote(projectId, draft);
      setNotes((current) => [created, ...current]);
      setDraft('');
      setMessage({ kind: 'ok', text: text.saved });
    } catch (err) {
      fail(err, text.save_error);
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (note: ProjectNote) => {
    setEditingId(note.id);
    setEditText(note.body);
    setConfirmId(null);
    setMessage(null);
  };

  const saveEdit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || editingId === null || editText.trim() === '') return;
    setBusy(true);
    setMessage(null);
    try {
      const changed = await updateProjectNote(projectId, editingId, editText);
      setNotes((current) => current.map((note) => (note.id === changed.id ? changed : note)));
      setEditingId(null);
      setMessage({ kind: 'ok', text: text.saved });
    } catch (err) {
      fail(err, text.save_error);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (noteId: string) => {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    try {
      await deleteProjectNote(projectId, noteId);
      setNotes((current) => current.filter((note) => note.id !== noteId));
      setConfirmId(null);
      setMessage({ kind: 'ok', text: text.deleted });
    } catch (err) {
      fail(err, text.delete_error);
    } finally {
      setBusy(false);
    }
  };

  const counter = (used: number) => text.count.replace('{used}', String(used)).replace('{max}', String(MAX_NOTE_LENGTH));
  const field = 'w-full border border-slate-200 rounded-xl px-3 py-2 text-base text-slate-900 pe-surface min-h-24';
  const primary = 'w-full min-h-11 px-4 py-1 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50';
  const secondary = 'flex-1 min-h-11 px-3 py-1 text-sm rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium hover:bg-slate-50';

  return (
    <section aria-label="project-notes" className="space-y-3">
      <form aria-label="note-form" onSubmit={add} className="pe-card rounded-2xl p-4 shadow-sm space-y-2">
        <textarea
          aria-label="note-input"
          value={draft}
          maxLength={MAX_NOTE_LENGTH}
          placeholder={text.placeholder}
          onChange={(event) => setDraft(event.target.value)}
          className={field}
        />
        <p className="text-xs text-slate-500">{counter(draft.length)}</p>
        <button type="submit" aria-label="note-add" disabled={busy || draft.trim() === ''} className={primary}>
          <Ico>{busy && editingId === null ? '⏳' : '➕'}</Ico>{busy && editingId === null ? t.common.saving : text.add}
        </button>
      </form>

      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>
          {message.text}
        </p>
      )}

      {loading && <p className="text-sm text-slate-500 text-center py-3">{text.loading}</p>}
      {!loading && loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-600 break-words">{text.load_error}</p>
          <button type="button" aria-label="notes-retry" onClick={() => void load()} className={primary}><Ico>🔄</Ico>{text.retry}</button>
        </div>
      )}
      {!loading && !loadFailed && notes.length === 0 && (
        <p aria-label="notes-empty" className="text-sm text-slate-500 text-center py-4">{text.empty}</p>
      )}

      {!loading && !loadFailed && notes.length > 0 && (
        <ul aria-label="notes-list" className="space-y-2">
          {notes.map((note) => (
            <li key={note.id} aria-label={`note-${note.id}`} className="pe-card rounded-2xl p-4 shadow-sm space-y-2">
              <PendingMark record={note} id={note.id} />
              <p aria-label={`note-time-${note.id}`} className="text-xs font-semibold text-slate-500">
                {formatNoteTime(note.created_at, locale)}
                {note.updated_at !== note.created_at && formatNoteTime(note.updated_at, locale) !== formatNoteTime(note.created_at, locale) && (
                  <span className="font-normal"> · {text.edited.replace('{date}', formatNoteTime(note.updated_at, locale))}</span>
                )}
              </p>
              {editingId === note.id ? (
                <form aria-label={`note-edit-form-${note.id}`} onSubmit={saveEdit} className="space-y-2">
                  <textarea
                    aria-label={`note-edit-input-${note.id}`}
                    value={editText}
                    maxLength={MAX_NOTE_LENGTH}
                    onChange={(event) => setEditText(event.target.value)}
                    className={field}
                  />
                  <p className="text-xs text-slate-500">{counter(editText.length)}</p>
                  <div className="flex gap-2">
                    <button type="button" aria-label={`note-edit-cancel-${note.id}`} onClick={() => setEditingId(null)} className={secondary}>
                      <Ico>✖️</Ico>{t.common.cancel}
                    </button>
                    <button
                      type="submit"
                      aria-label={`note-edit-save-${note.id}`}
                      disabled={busy || editText.trim() === ''}
                      className="flex-1 min-h-11 px-3 py-1 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 disabled:opacity-50"
                    >
                      <Ico>💾</Ico>{t.common.save}
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <p aria-label={`note-body-${note.id}`} className="text-sm text-slate-900 whitespace-pre-wrap break-words">{note.body}</p>
                  {confirmId === note.id ? (
                    <div className="space-y-2">
                      <p className="text-sm font-semibold text-slate-800 break-words">{text.confirm_delete}</p>
                      <div className="flex gap-2">
                        <button type="button" aria-label={`note-delete-cancel-${note.id}`} onClick={() => setConfirmId(null)} className={secondary}>
                          <Ico>✖️</Ico>{t.common.cancel}
                        </button>
                        <button
                          type="button"
                          aria-label={`note-delete-confirm-${note.id}`}
                          disabled={busy}
                          onClick={() => void remove(note.id)}
                          className="flex-1 min-h-11 px-3 py-1 text-sm bg-red-600 text-white font-semibold rounded-xl hover:bg-red-700 disabled:opacity-50"
                        >
                          <Ico>🗑️</Ico>{text.confirm_yes}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <button type="button" aria-label={`note-edit-${note.id}`} onClick={() => startEdit(note)} className={secondary}>
                        <Ico>✏️</Ico>{text.edit}
                      </button>
                      <button
                        type="button"
                        aria-label={`note-delete-${note.id}`}
                        onClick={() => {
                          setConfirmId(note.id);
                          setMessage(null);
                        }}
                        className={secondary}
                      >
                        <Ico>🗑️</Ico>{text.delete}
                      </button>
                    </div>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
