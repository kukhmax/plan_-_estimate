import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPhotoReportSummary, issuePhotoReport, listDocuments } from '../api/documents';
import { useI18n } from '../hooks/useI18n';
import { ProductionPlanSection, TechCardSection } from './TechCardSection';
import type { IssuedDocument, PhotoReportSummary, UnpricedWork } from '../types/document';
import { documentErrorText } from '../utils/documentErrors';
import { priceItemLabel } from '../utils/executionFormat';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';

const POLL_MS = 2500;
const MAX_POLLS = 72; // three minutes

interface ProjectDocumentsProps {
  projectId: string;
  /** Leads to the inspection that holds a recommendation the owner has to decide (Stage 15H.1). */
  onOpenInspection: (work: UnpricedWork) => void;
  /** Leads to the current estimate, or to the list of estimates when the object has none yet. */
  onOpenEstimate: (estimateId: string | null) => void;
}

const OPEN_KEY = 'pe.documents.open.';

/** A per-viewer convenience only: the card stays open when the owner comes back from the place it led to. */
function wasOpen(projectId: string): boolean {
  try {
    return window.sessionStorage.getItem(OPEN_KEY + projectId) === '1';
  } catch {
    return false;
  }
}

function rememberOpen(projectId: string, open: boolean): void {
  try {
    if (open) window.sessionStorage.setItem(OPEN_KEY + projectId, '1');
    else window.sessionStorage.removeItem(OPEN_KEY + projectId);
  } catch {
    // storage may be blocked; the card then simply starts closed
  }
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
export function ProjectDocuments({ projectId, onOpenInspection, onOpenEstimate }: ProjectDocumentsProps) {
  const { t, locale } = useI18n();
  const text = t.documents;
  const [open, setOpen] = useState(() => wasOpen(projectId));
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
  const blocked = (summary?.unpriced_items.length ?? 0) > 0;

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

  const surfaceLabels = { wall: t.surfaces.wall, floor: t.surfaces.floor, ceiling: t.surfaces.ceiling };
  const reasonText = (work: UnpricedWork): string => {
    switch (work.reason) {
      case 'PENDING':
        return text.reason_pending;
      case 'NO_ESTIMATE':
        return text.reason_no_estimate;
      case 'NO_PRICE':
        return text.reason_no_price;
      default:
        // accepted, but accepting never touches an estimate: a draft is updated, a settled one gets a new version
        return summary?.estimate_status === 'DRAFT' ? text.reason_not_in_estimate_draft : text.reason_not_in_estimate_final;
    }
  };
  const actionText = (work: UnpricedWork): string =>
    work.reason === 'PENDING' ? text.action_open_inspection : work.reason === 'NO_ESTIMATE' ? text.action_open_estimates : text.action_open_estimate;
  const openUnpriced = (work: UnpricedWork) => {
    if (work.reason === 'PENDING') onOpenInspection(work);
    else onOpenEstimate(work.reason === 'NO_ESTIMATE' ? null : summary?.estimate_id ?? null);
  };

  const kindLabels: Record<IssuedDocument['kind'], string> = {
    ESTIMATE: text.kind_estimate,
    PHOTO_REPORT: text.kind_photo_report,
    TECH_CARD: text.kind_tech_card,
    PRODUCTION_PLAN: text.kind_production_plan,
    CONTRACT: text.kind_contract,
    HANDOVER_PROTOCOL: text.kind_handover,
    CONCEALED_WORKS_PROTOCOL: text.kind_concealed,
    FINAL_PROTOCOL: text.kind_final,
    DECISION_PROTOCOL: text.kind_decision,
    DOWNTIME_NOTICE: text.kind_downtime_notice,
    DOWNTIME_PROTOCOL: text.kind_downtime_protocol,
  };
  const kindLabel = (document: IssuedDocument) => kindLabels[document.kind];
  const reloadJournal = async () => {
    try {
      const next = await listDocuments(projectId);
      if (alive.current) setDocuments(next.items);
    } catch {
      // the journal is read again with the next poll or the next opening
    }
  };

  return (
    <article aria-label="project-documents" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="min-w-0 break-words text-sm font-semibold text-slate-900">{text.title}</h3>
        <button
          type="button"
          aria-label="toggle-project-documents"
          aria-expanded={open}
          onClick={() => {
            rememberOpen(projectId, !open);
            setOpen((value) => !value);
          }}
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

      {open && !loadFailed && <TechCardSection projectId={projectId} onIssued={() => void reloadJournal()} />}
      {open && !loadFailed && <ProductionPlanSection projectId={projectId} onIssued={() => void reloadJournal()} />}

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
              {summary.unpriced_items.length > 0 && (
                <div role="alert" aria-label="unpriced-works" className="space-y-2">
                  <p className="text-sm font-semibold text-red-700 break-words">{text.unpriced_title}</p>
                  <p className="text-xs text-slate-600 break-words">{text.unpriced_tap}</p>
                  <ul className="space-y-2">
                    {summary.unpriced_items.map((work) => (
                      <li key={`${work.surface_id}-${work.work_code}`}>
                        <button
                          type="button"
                          aria-label={`unpriced-work-${work.work_code}`}
                          onClick={() => openUnpriced(work)}
                          className="w-full min-h-11 text-left bg-red-50 border border-red-200 rounded-xl px-3 py-2 space-y-1 hover:bg-red-100 active:bg-red-100 transition"
                        >
                          <span className="block text-sm font-semibold text-slate-900 break-words">
                            {priceItemLabel(t, { display_name: work.work_display_name, name_key: work.work_name_key, code: work.work_code }, work.work_code)}
                          </span>
                          <span className="block text-xs text-slate-700 break-words">
                            {work.room_name} › {getSurfaceDisplayName({ name: work.surface_name, surface_type: work.surface_type }, surfaceLabels)}
                          </span>
                          <span className="block text-xs text-red-800 break-words">{reasonText(work)}</span>
                          <span className="flex items-center justify-between gap-2 text-xs font-semibold text-blue-700">
                            <span className="min-w-0 break-words">{actionText(work)}</span>
                            <span aria-hidden="true" className="shrink-0 text-base leading-none">›</span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
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
