import { useEffect, useState } from 'react';
import { ApiError } from '../api/http';
import { StructurePurgePreview, StructurePurgeResult } from '../api/structurePurge';
import { useI18n } from '../hooks/useI18n';
import { formatSize } from '../utils/documentFormat';
import { Ico } from './Ico';

interface ArchiveStructureDeleteProps {
  kind: 'ROOM' | 'SURFACE' | 'INSPECTION';
  /** The name shown in the question (a surface in the current language: "Ściana 1"; an inspection: where it was made). */
  name: string;
  load: () => Promise<StructurePurgePreview>;
  run: () => Promise<StructurePurgeResult>;
  /** The room / surface / inspection is gone: the host takes it out of its list. */
  onDeleted: (result: StructurePurgeResult) => void;
  onCancel: () => void;
}

/**
 * The confirmation of deleting an archived room, surface or inspection for good (archive cleanup AC-4b, AC-7). The server counts what goes (below it,
 * photos and their files) and what holds it (a document that is not archived and still points to it) before anything is asked;
 * nothing is deleted until the owner has read it, ticked "I understand" and confirmed.
 */
export function ArchiveStructureDelete({ kind, name, load, run, onDeleted, onCancel }: ArchiveStructureDeleteProps) {
  const { t } = useI18n();
  const text = t.archive;
  const [preview, setPreview] = useState<StructurePurgePreview | null>(null);
  const [failed, setFailed] = useState<'load' | 'delete' | 'conflict' | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setFailed(null);
    setUnderstood(false);
    load()
      .then((value) => {
        if (!cancelled) setPreview(value);
      })
      .catch(() => {
        if (!cancelled) setFailed('load');
      });
    return () => {
      cancelled = true;
    };
    // `load` is made anew on every render of the host; the panel asks once for the room / surface it was opened for
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, name]);

  const refresh = () => {
    load().then(setPreview).catch(() => setFailed('load'));
  };

  const confirm = async () => {
    if (busy || !understood) return;
    setBusy(true);
    setFailed(null);
    try {
      onDeleted(await run());
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'STRUCTURE_PURGE_CONFLICT') {
        setFailed('conflict');
        setUnderstood(false);
        refresh();
      } else if (caught instanceof ApiError && caught.code === 'STRUCTURE_PURGE_BLOCKED') {
        refresh(); // a document that points to it appeared meanwhile: show it instead of a vague error
      } else {
        setFailed('delete');
      }
      setBusy(false);
    }
  };

  const blocked = preview !== null && preview.blockers.length > 0;
  const lines: string[] = [];
  if (preview) {
    const line = (template: string, count: number) => {
      if (count > 0) lines.push(template.replace('{count}', String(count)));
    };
    line(text.project_delete_surfaces, preview.surfaces);
    line(text.project_delete_openings, preview.openings);
    if (kind !== 'INSPECTION') line(text.project_delete_inspections, preview.inspections);
    line(text.inspection_delete_answers, preview.answers);
    line(text.inspection_delete_findings, preview.findings);
    line(text.inspection_delete_risks, preview.risks);
    line(text.inspection_delete_recommendations, preview.recommendations);
    if (preview.photos > 0) {
      lines.push(
        text.project_delete_photos
          .replace('{count}', String(preview.photos))
          .replace('{files}', String(preview.photo_files))
          .replace('{size}', formatSize(preview.bytes)),
      );
    }
    line(text.project_delete_markers, preview.annotations);
  }
  const title = kind === 'ROOM' ? text.room_delete_title : kind === 'SURFACE' ? text.surface_delete_title : text.inspection_delete_title;
  const intro = (kind === 'ROOM' ? text.room_delete_intro : kind === 'SURFACE' ? text.surface_delete_intro : text.inspection_delete_intro).replace('{name}', name);

  return (
    <div role="alertdialog" aria-label={title} className="space-y-3 rounded-xl border border-red-300 p-3">
      <p className="break-words text-sm font-semibold text-slate-900">{title}</p>
      {preview === null && failed !== 'load' && <p role="status" className="break-words text-sm text-slate-500">{text.client_delete_loading}</p>}
      {preview !== null && (
        <div className="space-y-2 break-words text-sm text-slate-700">
          {blocked ? (
            <div role="alert" className="space-y-1 text-red-700">
              <p className="font-semibold">{text.structure_delete_blocked_title}</p>
              <ul className="list-disc pl-5">
                {preview.blockers.map((blocker) => (
                  <li key={`${blocker.kind}-${blocker.protocol_id}`}>
                    {(text as Record<string, string>)[`structure_blocker_${blocker.kind}`] ?? blocker.kind}
                  </li>
                ))}
              </ul>
              <p>{text.structure_delete_blocked_hint}</p>
            </div>
          ) : (
            <>
              <p>{intro}</p>
              {lines.length > 0 ? (
                <ul aria-label="structure-delete-lines" className="list-disc pl-5">
                  {lines.map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              ) : (
                <p>{kind === 'INSPECTION' ? text.inspection_delete_nothing : text.structure_delete_nothing}</p>
              )}
              {preview.estimate_lines > 0 && (
                <p className="text-slate-500">{text.structure_delete_estimates.replace('{count}', String(preview.estimate_lines))}</p>
              )}
              {preview.may_be_in_backups && <p className="text-slate-500">{text.project_delete_backups}</p>}
              <label className="flex min-h-11 items-start gap-3 font-semibold">
                <input
                  type="checkbox"
                  aria-label="structure-delete-understood"
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
      {failed === 'conflict' && <p role="alert" className="break-words text-sm text-red-700">{text.structure_delete_conflict}</p>}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          aria-label="structure-delete-cancel"
          disabled={busy}
          onClick={onCancel}
          className="w-full min-h-11 rounded-xl bg-blue-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          <Ico>✖️</Ico>{text.client_delete_cancel}
        </button>
        {!blocked && (
          <button
            type="button"
            aria-label="structure-delete-confirm"
            disabled={busy || preview === null || !preview.can_purge || !understood}
            onClick={() => void confirm()}
            className="w-full min-h-11 rounded-xl border border-red-600 bg-red-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
          >
            <Ico>🗑️</Ico>{busy ? text.project_deleting : text.project_delete_confirm}
          </button>
        )}
      </div>
    </div>
  );
}
