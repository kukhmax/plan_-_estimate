import { ChangeEvent, FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  deleteKnowledgeDocument,
  fetchKnowledgeDocument,
  fetchKnowledgeDocumentFile,
  listKnowledgeDocuments,
  saveKnowledgeDocument,
  sendKnowledgeDocumentToChat,
} from '../api/knowledgeDocuments';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import {
  DOCUMENT_KINDS,
  type DocumentKindValue,
  type KnowledgeDocumentDetail,
  type KnowledgeDocumentInput,
  type KnowledgeDocumentItem,
} from '../types/knowledgeDocument';
import { formatSize } from '../utils/documentFormat';
import { localeTag } from '../utils/locale';
import { Ico } from './Ico';

const CARD = 'pe-card rounded-2xl p-3 shadow-sm';
const INPUT = 'w-full min-h-11 px-3 py-2 text-base rounded-xl border border-slate-300 pe-surface text-slate-900';
const PREVIEW_ROWS = 5;
const SEARCH_DELAY_MS = 250;
const MAX_FILE_BYTES = 10_000_000;

function fill(template: string, values: Record<string, string | number>): string {
  return Object.entries(values).reduce((text, [key, value]) => text.replace(`{${key}}`, String(value)), template);
}

/** In Telegram a file cannot be shown in the window of the application; it is sent to the chat instead. */
function insideTelegram(): boolean {
  return Boolean(window.Telegram?.WebApp?.initData);
}

function useErrorText() {
  const { t } = useI18n();
  const known = t.knowledge_docs.errors as Record<string, string>;
  return (error: unknown, fallback: string): string => {
    const code = error instanceof ApiError ? error.code : undefined;
    return (code && known[code]) || fallback;
  };
}

function KindBadge({ kind }: { kind: DocumentKindValue }) {
  const { t } = useI18n();
  return <span className="inline-block text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 break-words">{t.knowledge_docs.kinds[kind]}</span>;
}

// --- the block on the list of the knowledge base ----------------------------------------------------------------------------------------

interface SectionProps {
  query: string;
  onOpen: (id: string) => void;
  /** Changes when a document was added, changed or deleted on another view, so that the list is read again. */
  refreshKey?: number;
}

/**
 * "Moje dokumenty" (V2-7a): the owner's own documents on the list of the knowledge base, with the button that adds one. The search of the knowledge
 * base filters them as well (the server searches); only five are shown until the owner asks for all.
 */
export function KnowledgeDocumentsSection({ query, onOpen, refreshKey = 0 }: SectionProps) {
  const { t } = useI18n();
  const text = t.knowledge_docs;
  const [items, setItems] = useState<KnowledgeDocumentItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [all, setAll] = useState(false);
  const [sheet, setSheet] = useState(false);
  const request = useRef(0);

  const load = useCallback(async (q: string) => {
    const mine = ++request.current;
    try {
      const data = await listKnowledgeDocuments(q);
      if (mine === request.current) {
        setItems(data.items);
        setFailed(false);
      }
    } catch {
      if (mine === request.current) setFailed(true);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(query), query ? SEARCH_DELAY_MS : 0);
    return () => window.clearTimeout(timer);
  }, [query, refreshKey, load]);

  const shown = items === null ? [] : query || all ? items : items.slice(0, PREVIEW_ROWS);

  return (
    <div aria-label="knowledge-documents" className="space-y-2">
      <h3 className="text-sm font-bold text-slate-700">
        {text.title}
        {items !== null && <span aria-label="knowledge-documents-count" className="ml-2 font-normal text-slate-500">{fill(text.count, { count: items.length })}</span>}
      </h3>
      <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{text.intro}</p>
      <button
        type="button"
        aria-label="knowledge-document-add"
        onClick={() => setSheet(true)}
        className="w-full min-h-12 px-4 text-sm font-semibold rounded-xl bg-blue-600 text-white hover:bg-blue-700"
      >
        <Ico>➕</Ico>{text.add}
      </button>
      {failed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-600 break-words">{text.error_load}</p>
          <button type="button" aria-label="knowledge-documents-retry" onClick={() => void load(query)} className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl border border-slate-300 text-slate-800">
            <Ico>🔄</Ico>{text.retry}
          </button>
        </div>
      )}
      {!failed && items === null && <p className="text-sm text-slate-500">{text.loading}</p>}
      {!failed && items !== null && items.length === 0 && (
        <p aria-label="knowledge-documents-empty" className="text-sm text-slate-400 text-center py-3 break-words">{query ? text.empty_search : text.empty}</p>
      )}
      {shown.length > 0 && (
        <ul aria-label="knowledge-documents-list" className="space-y-2">
          {shown.map((doc) => (
            <li key={doc.id}>
              <button
                type="button"
                aria-label={`knowledge-document-${doc.id}`}
                onClick={() => onOpen(doc.id)}
                className={`${CARD} w-full min-h-14 text-left space-y-1 hover:bg-slate-50`}
              >
                <span className="block text-sm font-semibold text-slate-900 break-words">{doc.title}</span>
                <span className="flex flex-wrap items-center gap-1.5">
                  <KindBadge kind={doc.kind} />
                  {doc.file_name && <span aria-hidden="true" title={doc.file_name} className="text-sm">📎</span>}
                  {doc.source_url && <span aria-hidden="true" className="text-sm">🔗</span>}
                  {doc.has_text && <span aria-hidden="true" className="text-sm">📝</span>}
                  {doc.tags.map((tag) => (
                    <span key={tag} className="text-[11px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-800 break-all">{tag}</span>
                  ))}
                </span>
                {doc.snippet && <span className="block text-xs text-slate-500 break-words line-clamp-2">{doc.snippet}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {!query && !all && items !== null && items.length > PREVIEW_ROWS && (
        <button type="button" aria-label="knowledge-documents-all" onClick={() => setAll(true)} className="w-full min-h-11 px-3 text-sm font-medium rounded-xl border border-slate-300 text-slate-800 hover:bg-slate-50">
          {t.documents.show} ({items.length})
        </button>
      )}
      {sheet && (
        <KnowledgeDocumentSheet
          existing={null}
          onClose={() => setSheet(false)}
          onSaved={(doc) => {
            setSheet(false);
            void load(query);
            onOpen(doc.id);
          }}
        />
      )}
    </div>
  );
}

// --- the window that adds or changes a document ------------------------------------------------------------------------------------------

interface SheetProps {
  existing: KnowledgeDocumentDetail | null;
  onClose: () => void;
  onSaved: (doc: KnowledgeDocumentDetail) => void;
}

function inputOf(existing: KnowledgeDocumentDetail | null): KnowledgeDocumentInput {
  return {
    title: existing?.title ?? '',
    kind: existing?.kind ?? 'OTHER',
    source_url: existing?.source_url ?? '',
    doc_date: existing?.doc_date ?? '',
    when_to_use: existing?.when_to_use ?? '',
    body: existing?.body ?? '',
    tags: existing?.tags.join(', ') ?? '',
    file: null,
    remove_file: false,
  };
}

/**
 * The window "Dodaj dokument" / "Zmiana dokumentu": name, kind, link, a file (a PDF or a photo of a page), the text, the date, "when to use" and
 * tags. One form; the server checks everything and answers with a code that is said here in words. A portal over the screen, so the submit
 * is stopped before it reaches a form that holds the component.
 */
export function KnowledgeDocumentSheet({ existing, onClose, onSaved }: SheetProps) {
  const { t } = useI18n();
  const text = t.knowledge_docs;
  const errorText = useErrorText();
  const [input, setInput] = useState<KnowledgeDocumentInput>(() => inputOf(existing));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useTelegramBackButton(true, onClose);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const set = <K extends keyof KnowledgeDocumentInput>(key: K, value: KnowledgeDocumentInput[K]) => setInput((current) => ({ ...current, [key]: value }));

  const choose = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    event.target.value = '';
    if (file && file.size > MAX_FILE_BYTES) {
      setError(text.errors.FILE_TOO_LARGE);
      return;
    }
    setError(null);
    setInput((current) => ({ ...current, file, remove_file: false }));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (saving) return;
    if (!input.title.trim()) {
      setError(text.errors.TITLE_REQUIRED);
      return;
    }
    const keepsFile = input.file !== null || (existing?.file_name != null && !input.remove_file);
    if (!input.body.trim() && !input.source_url.trim() && !keepsFile) {
      setError(text.errors.CONTENT_REQUIRED);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      onSaved(await saveKnowledgeDocument(existing?.id ?? null, input));
    } catch (failure) {
      setError(errorText(failure, text.save_failed));
    } finally {
      setSaving(false);
    }
  };

  const currentFile = existing?.file_name && !input.remove_file && !input.file ? existing : null;

  return createPortal(
    <div role="dialog" aria-modal="true" aria-label={existing ? text.form_edit_title : text.form_add_title} className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50">
      <form
        aria-label="knowledge-document-form"
        onSubmit={submit}
        noValidate
        className="pe-card w-full max-w-lg rounded-t-2xl sm:rounded-2xl p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-xl space-y-3 max-h-[92vh] overflow-y-auto"
      >
        <h4 className="font-semibold text-slate-900 break-words">{existing ? text.form_edit_title : text.form_add_title}</h4>

        <div className="space-y-1">
          <label htmlFor="kd-title" className="block text-xs font-medium text-slate-600">{text.fields.title}</label>
          <input id="kd-title" aria-label="knowledge-document-title" value={input.title} maxLength={200} placeholder={text.placeholders.title} onChange={(e) => set('title', e.target.value)} className={INPUT} />
        </div>

        <div className="space-y-1">
          <label htmlFor="kd-kind" className="block text-xs font-medium text-slate-600">{text.fields.kind}</label>
          <select id="kd-kind" aria-label="knowledge-document-kind" value={input.kind} onChange={(e) => set('kind', e.target.value as DocumentKindValue)} className={INPUT}>
            {DOCUMENT_KINDS.map((kind) => (
              <option key={kind} value={kind}>{text.kinds[kind]}</option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <label htmlFor="kd-url" className="block text-xs font-medium text-slate-600">{text.fields.source_url}</label>
          <input id="kd-url" aria-label="knowledge-document-url" type="url" inputMode="url" autoComplete="off" value={input.source_url} maxLength={1000} placeholder={text.placeholders.source_url} onChange={(e) => set('source_url', e.target.value)} className={INPUT} />
        </div>

        <div className="space-y-1">
          <span className="block text-xs font-medium text-slate-600">{text.fields.file}</span>
          {input.file && <p className="text-sm text-slate-800 break-all">{fill(text.file_chosen, { name: input.file.name })}</p>}
          {currentFile && <p className="text-sm text-slate-800 break-all">{fill(text.file_current, { name: currentFile.file_name ?? '', size: formatSize(currentFile.file_size ?? 0) })}</p>}
          <input ref={fileInput} aria-label="knowledge-document-file" type="file" accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png" onChange={choose} className="hidden" />
          <div className="flex flex-col gap-2">
            <button type="button" aria-label="knowledge-document-file-pick" onClick={() => fileInput.current?.click()} className="w-full min-h-11 px-3 text-sm font-medium rounded-xl border border-slate-300 text-slate-800 hover:bg-slate-50">
              <Ico>📎</Ico>{input.file || currentFile ? text.file_replace : text.file_choose}
            </button>
            {(input.file || currentFile) && (
              <button
                type="button"
                aria-label="knowledge-document-file-remove"
                onClick={() => setInput((current) => ({ ...current, file: null, remove_file: Boolean(existing?.file_name) }))}
                className="w-full min-h-11 px-3 text-sm font-medium rounded-xl border border-red-200 text-red-700 hover:bg-red-50"
              >
                {text.file_remove}
              </button>
            )}
          </div>
          <p className="text-xs text-slate-500 break-words">{text.file_limit}</p>
        </div>

        <div className="space-y-1">
          <label htmlFor="kd-body" className="block text-xs font-medium text-slate-600">{text.fields.body}</label>
          <textarea id="kd-body" aria-label="knowledge-document-body" rows={6} value={input.body} maxLength={100000} placeholder={text.placeholders.body} onChange={(e) => set('body', e.target.value)} className={`${INPUT} resize-y`} />
        </div>

        <div className="space-y-1">
          <label htmlFor="kd-date" className="block text-xs font-medium text-slate-600">{text.fields.doc_date}</label>
          <input id="kd-date" aria-label="knowledge-document-date" type="date" value={input.doc_date} onChange={(e) => set('doc_date', e.target.value)} className={INPUT} />
        </div>

        <div className="space-y-1">
          <label htmlFor="kd-when" className="block text-xs font-medium text-slate-600">{text.fields.when_to_use}</label>
          <textarea id="kd-when" aria-label="knowledge-document-when" rows={2} value={input.when_to_use} maxLength={1000} placeholder={text.placeholders.when_to_use} onChange={(e) => set('when_to_use', e.target.value)} className={`${INPUT} resize-y`} />
        </div>

        <div className="space-y-1">
          <label htmlFor="kd-tags" className="block text-xs font-medium text-slate-600">{text.fields.tags}</label>
          <input id="kd-tags" aria-label="knowledge-document-tags" value={input.tags} maxLength={400} autoComplete="off" placeholder={text.placeholders.tags} onChange={(e) => set('tags', e.target.value)} className={INPUT} />
        </div>

        {error && <p role="alert" className="text-sm text-red-600 font-medium break-words">{error}</p>}
        <div className="flex flex-col-reverse gap-2">
          <button type="button" aria-label="knowledge-document-cancel" onClick={onClose} className="w-full min-h-11 px-3 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50">
            <Ico>✖️</Ico>{t.common.cancel}
          </button>
          <button type="submit" aria-label="knowledge-document-save" disabled={saving} className="w-full min-h-12 px-3 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 disabled:opacity-50">
            <Ico>💾</Ico>{saving ? t.common.saving : t.common.save}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}

// --- one document ------------------------------------------------------------------------------------------------------------------------

interface CardProps {
  id: string;
  /** The document was deleted: the screen goes back to the list. */
  onDeleted: () => void;
  /** The document was changed: the list is read again when the screen goes back. */
  onChanged: () => void;
}

export function KnowledgeDocumentCard({ id, onDeleted, onChanged }: CardProps) {
  const { t, locale } = useI18n();
  const text = t.knowledge_docs;
  const errorText = useErrorText();
  const [doc, setDoc] = useState<KnowledgeDocumentDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [image, setImage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setFailed(false);
    try {
      setDoc(await fetchKnowledgeDocument(id));
    } catch {
      setFailed(true);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(
    () => () => {
      if (image) URL.revokeObjectURL(image);
    },
    [image],
  );

  if (failed) {
    return (
      <div className="space-y-2">
        <p role="alert" className="text-sm text-red-600 break-words">{text.error_load}</p>
        <button type="button" aria-label="knowledge-document-retry" onClick={() => void load()} className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-blue-600 text-white">
          <Ico>🔄</Ico>{text.retry}
        </button>
      </div>
    );
  }
  if (!doc) return <p className="text-sm text-slate-500">{text.loading}</p>;

  const isImage = doc.file_mime?.startsWith('image/') ?? false;
  const inTelegram = insideTelegram();

  const openFile = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const blob = await fetchKnowledgeDocumentFile(doc.id);
      const url = URL.createObjectURL(blob);
      if (isImage) {
        setImage(url);
      } else {
        window.open(url, '_blank', 'noopener');
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }
    } catch (failure) {
      setMessage({ kind: 'error', text: errorText(failure, text.file_open_failed) });
    } finally {
      setBusy(false);
    }
  };

  const sendFile = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await sendKnowledgeDocumentToChat(doc.id);
      setMessage({ kind: 'ok', text: text.sent });
    } catch (failure) {
      const known = t.documents.errors as Record<string, string>;
      const code = failure instanceof ApiError ? failure.code : undefined;
      setMessage({ kind: 'error', text: (code && (known[code] ?? (text.errors as Record<string, string>)[code])) || text.send_failed });
    } finally {
      setBusy(false);
    }
  };

  const openLink = () => {
    if (!doc.source_url) return;
    if (window.Telegram?.WebApp?.openLink) window.Telegram.WebApp.openLink(doc.source_url);
    else window.open(doc.source_url, '_blank', 'noopener');
  };

  const remove = async () => {
    setBusy(true);
    try {
      await deleteKnowledgeDocument(doc.id);
      onChanged();
      onDeleted();
    } catch (failure) {
      setConfirming(false);
      setMessage({ kind: 'error', text: errorText(failure, text.delete_failed) });
    } finally {
      setBusy(false);
    }
  };

  const BTN = 'w-full min-h-11 px-3 text-sm font-medium rounded-xl border border-slate-300 text-slate-800 hover:bg-slate-50 disabled:opacity-50';

  return (
    <article aria-label="knowledge-document-card" className="space-y-3">
      <h2 className="text-lg font-bold text-slate-900 break-words">{doc.title}</h2>
      <div className="flex flex-wrap items-center gap-1.5">
        <KindBadge kind={doc.kind} />
        {doc.tags.map((tag) => (
          <span key={tag} className="text-[11px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-800 break-all">{tag}</span>
        ))}
      </div>
      {doc.doc_date && (
        <p className="text-xs text-slate-500">{fill(text.date_label, { date: new Date(`${doc.doc_date}T00:00:00`).toLocaleDateString(localeTag(locale)) })}</p>
      )}
      {doc.when_to_use && (
        <div className={`${CARD} space-y-1`}>
          <p className="text-xs font-semibold text-slate-600">{text.when_label}</p>
          <p className="text-sm text-slate-800 whitespace-pre-line break-words">{doc.when_to_use}</p>
        </div>
      )}

      {(doc.source_url || doc.file_name) && (
        <div className="space-y-2">
          {doc.source_url && (
            <>
              <p className="text-xs text-slate-500 break-all">{doc.source_url}</p>
              <button type="button" aria-label="knowledge-document-open-link" onClick={openLink} className={BTN}>
                <Ico>🔗</Ico>{text.open_link}
              </button>
            </>
          )}
          {doc.file_name && (
            <>
              <p className="text-sm text-slate-800 break-all">📎 {doc.file_name}{doc.file_size ? ` (${formatSize(doc.file_size)})` : ''}</p>
              {(isImage || !inTelegram) && (
                <button type="button" aria-label="knowledge-document-open-file" disabled={busy} onClick={() => void openFile()} className={BTN}>
                  <Ico>📄</Ico>{text.open_file}
                </button>
              )}
              <button type="button" aria-label="knowledge-document-send" disabled={busy} onClick={() => void sendFile()} className={BTN}>
                <Ico>📨</Ico>{text.send_chat}
              </button>
              <p className="text-xs text-slate-500 break-words">{text.send_chat_hint}</p>
            </>
          )}
        </div>
      )}
      {image && (
        <div className="space-y-2">
          <img aria-label="knowledge-document-image" src={image} alt={doc.file_name ?? ''} className="w-full rounded-xl border border-slate-200" />
          <button type="button" aria-label="knowledge-document-image-close" onClick={() => setImage(null)} className={BTN}>{text.file_close}</button>
        </div>
      )}

      {doc.body && (
        <div className={`${CARD} space-y-1`}>
          <p className="text-xs font-semibold text-slate-600">{text.text_label}</p>
          <p aria-label="knowledge-document-body-text" className="text-sm text-slate-800 whitespace-pre-wrap break-words">{doc.body}</p>
        </div>
      )}

      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm font-medium break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>{message.text}</p>
      )}

      <div className="flex flex-col gap-2 pt-1">
        <button type="button" aria-label="knowledge-document-edit" onClick={() => setEditing(true)} className={BTN}>
          <Ico>✏️</Ico>{text.edit}
        </button>
        {!confirming ? (
          <button type="button" aria-label="knowledge-document-delete" onClick={() => setConfirming(true)} className="w-full min-h-11 px-3 text-sm font-medium rounded-xl border border-red-200 text-red-700 hover:bg-red-50">
            {text.delete}
          </button>
        ) : (
          <div role="alertdialog" aria-label="knowledge-document-delete-confirm" className="rounded-xl border border-red-200 bg-red-50 p-3 space-y-2">
            <p className="text-sm font-semibold text-red-800 break-words">{text.delete_title}</p>
            <p className="text-xs text-red-800 break-words">{fill(text.delete_text, { name: doc.title })}</p>
            <button type="button" aria-label="knowledge-document-delete-yes" disabled={busy} onClick={() => void remove()} className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl bg-red-600 text-white disabled:opacity-50">
              {text.delete_yes}
            </button>
            <button type="button" aria-label="knowledge-document-delete-no" onClick={() => setConfirming(false)} className="w-full min-h-11 px-3 text-sm rounded-xl border border-slate-300 text-slate-700 pe-surface">
              {t.common.cancel}
            </button>
          </div>
        )}
      </div>

      {editing && (
        <KnowledgeDocumentSheet
          existing={doc}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setEditing(false);
            setDoc(saved);
            setImage(null);
            onChanged();
          }}
        />
      )}
    </article>
  );
}
