import { useCallback, useEffect, useRef, useState } from 'react';
import { listAllDocuments } from '../api/documents';
import { useI18n } from '../hooks/useI18n';
import type { OwnerDocument } from '../types/document';
import { documentErrorText } from '../utils/documentErrors';
import { documentKindLabel, formatIssued, formatSize } from '../utils/documentFormat';

const PAGE = 30;

/**
 * The journal of everything sent to the owner's chat, over all objects, newest first (Stage 16K.5). Read only: a document
 * is made on the screen of its object; here it is only found again (number, kind, object, date, how it ended).
 */
export function SentDocuments() {
  const { t, locale } = useI18n();
  const text = t.documents;
  const own = t.sentDocuments;
  const [items, setItems] = useState<OwnerDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = useCallback(async (offset: number) => {
    setLoading(true);
    setFailed(false);
    try {
      const page = await listAllDocuments(PAGE, offset);
      if (!alive.current) return;
      setItems((current) => (offset === 0 ? page.items : [...current, ...page.items]));
      setTotal(page.total);
    } catch {
      if (alive.current) setFailed(true);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(0);
  }, [load]);

  return (
    <section aria-label="sent-documents-section" className="w-full mt-4 space-y-3">
      <h2 className="text-lg font-bold text-[var(--tg-theme-text-color)]">{text.journal_title}</h2>
      <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{own.intro}</p>

      <button
        type="button"
        aria-label="sent-documents-refresh"
        disabled={loading}
        onClick={() => void load(0)}
        className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50"
      >
        {own.refresh}
      </button>

      {failed && <p role="alert" className="text-sm text-red-600 break-words">{own.error_load}</p>}
      {loading && items.length === 0 && !failed && <p className="text-sm text-slate-500">{text.loading}</p>}
      {!loading && !failed && items.length === 0 && (
        <p aria-label="sent-documents-empty" className="text-sm text-slate-400 text-center py-6">{own.empty}</p>
      )}

      {items.length > 0 && (
        <ul aria-label="sent-documents-list" className="space-y-2">
          {items.map((document) => (
            <li
              key={document.id}
              aria-label={`document-${document.number}`}
              className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm space-y-1"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="min-w-0 break-words text-sm font-semibold text-slate-900">{documentKindLabel(text, document.kind)}</span>
                <span
                  className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${
                    document.status === 'SENT'
                      ? 'bg-emerald-100 text-emerald-800'
                      : document.status === 'PENDING'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-red-100 text-red-800'
                  }`}
                >
                  {document.status === 'SENT' ? text.status_sent : document.status === 'PENDING' ? text.status_pending : text.status_failed}
                </span>
              </div>
              <p className="text-xs text-slate-700 break-words">
                {own.object} <span className="font-medium">{document.project_name}</span>
              </p>
              <p className="text-xs text-slate-700 break-all">{document.number}</p>
              <p className="text-xs text-slate-600 break-words">
                {formatIssued(document.issued_at, locale)}
                {document.pages ? ` · ${text.pages.replace('{n}', String(document.pages))}` : ''}
                {document.byte_size ? ` · ${formatSize(document.byte_size)}` : ''}
              </p>
              {document.status === 'FAILED' && (
                <p className="text-xs text-red-700 break-words">{documentErrorText(text.errors, document.error_code ?? undefined)}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {items.length > 0 && (
        <p aria-label="sent-documents-shown" className="text-xs text-slate-500 text-center">
          {own.shown.replace('{shown}', String(items.length)).replace('{total}', String(total))}
        </p>
      )}
      {items.length < total && (
        <button
          type="button"
          aria-label="sent-documents-more"
          disabled={loading}
          onClick={() => void load(items.length)}
          className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-blue-600 text-white disabled:opacity-50"
        >
          {own.more}
        </button>
      )}
    </section>
  );
}
