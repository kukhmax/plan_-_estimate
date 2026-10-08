import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPhotoReportSummary, issuePhotoReport, listDocuments } from '../api/documents';
import { useI18n } from '../hooks/useI18n';
import type { IssuedDocument, PhotoReportSummary } from '../types/document';
import { documentErrorText } from '../utils/documentErrors';

const POLL_MS = 2500;
const MAX_POLLS = 72; // three minutes

interface ProjectDocumentsProps {
  projectId: string;
}

function formatIssued(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(locale === 'ru' ? 'ru-RU' : 'pl-PL', {
    timeZone: 'Europe/Warsaw',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatSize(bytes: number): string {
  return bytes >= 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

/**
 * Stage 15F.3 — the documents of one object: the photo report (whole, or in parts by room when it is over the photo limit)
 * and the journal of what was sent. Closed by default and loads nothing until opened; a running document is followed until
 * it ends.
 */
export function ProjectDocuments({ projectId }: ProjectDocumentsProps) {
  const { t, locale } = useI18n();
  const text = t.documents;
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [summary, setSummary] = useState<PhotoReportSummary | null>(null);
  const [documents, setDocuments] = useState<IssuedDocument[]>([]);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [withProject, setWithProject] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const [nextSummary, nextList] = await Promise.all([fetchPhotoReportSummary(projectId), listDocuments(projectId)]);
      if (!alive.current) return;
      setSummary(nextSummary);
      setDocuments(nextList.items);
    } catch {
      if (alive.current) setLoadFailed(true);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const pending = documents.some((d) => d.status === 'PENDING');
  useEffect(() => {
    if (!open || !pending) return undefined;
    let polls = 0;
    const timer = window.setInterval(async () => {
      polls += 1;
      try {
        const next = await listDocuments(projectId);
        if (alive.current) setDocuments(next.items);
      } catch {
        // the next poll asks again
      }
      if (polls >= MAX_POLLS) window.clearInterval(timer);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [open, pending, projectId]);

  const selectedCount = (summary?.rooms ?? [])
    .filter((room) => chosen.has(room.room_id))
    .reduce((sum, room) => sum + room.photos, 0) + (withProject ? summary?.project_photos ?? 0 : 0);
  const tooBig = summary !== null && selectedCount > summary.limit;
  // a recommended extra work without a price blocks the report (the server refuses it too): say so instead of failing
  const blocked = (summary?.unpriced_works.length ?? 0) > 0;

  const send = async (part?: { room_ids: string[]; include_project_photos: boolean }) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await issuePhotoReport(projectId, part);
      if (alive.current) {
        const next = await listDocuments(projectId);
        setDocuments(next.items);
      }
    } catch (err) {
      if (alive.current) setError(documentErrorText(text.errors, err));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const toggleRoom = (roomId: string) =>
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(roomId)) next.delete(roomId);
      else next.add(roomId);
      return next;
    });

  const kindLabel = (document: IssuedDocument) => (document.kind === 'ESTIMATE' ? text.kind_estimate : text.kind_photo_report);

  return (
    <article aria-label="project-documents" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="min-w-0 break-words text-sm font-semibold text-slate-900">{text.title}</h3>
        <button
          type="button"
          aria-label="toggle-project-documents"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="min-h-11 px-4 shrink-0 text-sm font-semibold text-slate-800 bg-slate-100 border border-slate-200 rounded-xl hover:bg-slate-200 transition"
        >
          {open ? text.hide : text.show}
        </button>
      </div>

      {open && loading && summary === null && <p role="status" className="text-sm text-slate-600">{text.loading}</p>}

      {open && loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-700 break-words">{text.load_failed}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="w-full min-h-11 text-sm font-semibold text-slate-800 bg-slate-100 border border-slate-200 rounded-xl"
          >
            {text.retry}
          </button>
        </div>
      )}

      {open && summary && (
        <section aria-label="photo-report-card" className="space-y-2">
          <h4 className="text-sm font-semibold text-slate-900 break-words">{text.photo_report}</h4>
          {!summary.has_content ? (
            <p className="text-sm text-slate-600 break-words">{text.nothing}</p>
          ) : (
            <>
              <p className="text-sm text-slate-700 break-words">
                {text.photo_summary.replace('{count}', String(summary.photo_count)).replace('{limit}', String(summary.limit))}
              </p>
              {summary.recommended_count > 0 && (
                <p className="text-sm text-slate-700 break-words">
                  {text.recommended_works.replace('{count}', String(summary.recommended_count))}
                </p>
              )}
              {summary.unpriced_works.length > 0 && (
                <div role="alert" aria-label="unpriced-works" className="text-sm text-red-700 space-y-1">
                  <p className="font-medium break-words">{text.unpriced_title}</p>
                  <ul className="list-disc pl-5 space-y-0.5">
                    {summary.unpriced_works.map((work) => (
                      <li key={work} className="break-words">{work}</li>
                    ))}
                  </ul>
                  <p className="break-words">{text.unpriced_hint}</p>
                </div>
              )}
              {!summary.over_limit ? (
                <button
                  type="button"
                  aria-label="send-photo-report"
                  onClick={() => void send()}
                  disabled={busy || blocked}
                  className="w-full min-h-11 px-3 text-sm font-semibold text-white bg-sky-700 rounded-xl hover:bg-sky-800 disabled:opacity-60 transition break-words"
                >
                  {busy ? text.sending : text.send_pdf}
                </button>
              ) : (
                <div className="space-y-2">
                  <p role="status" className="text-sm text-amber-800 break-words">
                    {text.over_limit.replace('{count}', String(summary.photo_count)).replace('{limit}', String(summary.limit))}
                  </p>
                  <fieldset className="space-y-1">
                    <legend className="text-xs font-medium text-slate-600">{text.choose_rooms}</legend>
                    {summary.rooms.map((room) => (
                      <label key={room.room_id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                        <input
                          type="checkbox"
                          className="h-5 w-5 shrink-0"
                          checked={chosen.has(room.room_id)}
                          onChange={() => toggleRoom(room.room_id)}
                        />
                        <span className="min-w-0 break-words">
                          {text.room_line.replace('{name}', room.name).replace('{count}', String(room.photos))}
                        </span>
                      </label>
                    ))}
                    {summary.project_photos > 0 && (
                      <label className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                        <input
                          type="checkbox"
                          className="h-5 w-5 shrink-0"
                          checked={withProject}
                          onChange={() => setWithProject((value) => !value)}
                        />
                        <span className="min-w-0 break-words">
                          {text.include_project.replace('{count}', String(summary.project_photos))}
                        </span>
                      </label>
                    )}
                  </fieldset>
                  <p className={`text-xs break-words ${tooBig ? 'text-red-700' : 'text-slate-600'}`}>
                    {text.selected_total.replace('{count}', String(selectedCount)).replace('{limit}', String(summary.limit))}
                    {tooBig ? ` — ${text.selection_too_big}` : ''}
                  </p>
                  <button
                    type="button"
                    aria-label="send-photo-report-part"
                    onClick={() => void send({ room_ids: [...chosen], include_project_photos: withProject })}
                    disabled={busy || blocked || tooBig || chosen.size === 0}
                    className="w-full min-h-11 px-3 text-sm font-semibold text-white bg-sky-700 rounded-xl hover:bg-sky-800 disabled:opacity-60 transition break-words"
                  >
                    {busy ? text.sending : text.send_part}
                  </button>
                  {chosen.size === 0 && <p className="text-xs text-slate-500 break-words">{text.no_selection}</p>}
                </div>
              )}
              <p className="text-xs text-slate-500 break-words">{text.chat_hint}</p>
            </>
          )}
          {error && <p role="alert" aria-label="photo-report-error" className="text-sm text-red-700 break-words">{error}</p>}
        </section>
      )}

      {open && !loadFailed && (summary !== null || documents.length > 0) && (
        <section aria-label="document-journal" className="space-y-2">
          <h4 className="text-sm font-semibold text-slate-900 break-words">{text.journal_title}</h4>
          {documents.length === 0 ? (
            <p className="text-sm text-slate-600">{text.journal_empty}</p>
          ) : (
            <ul className="space-y-2">
              {documents.map((document) => (
                <li
                  key={document.id}
                  aria-label={`document-${document.number}`}
                  className="border border-slate-200 rounded-xl p-3 space-y-1"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="min-w-0 break-words text-sm font-medium text-slate-900">{kindLabel(document)}</span>
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
                  <p className="text-xs text-slate-700 break-all">{document.number}</p>
                  <p className="text-xs text-slate-600 break-words">
                    {text.sequence.replace('{n}', String(document.project_seq))} · {formatIssued(document.issued_at, locale)}
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
        </section>
      )}
    </article>
  );
}
