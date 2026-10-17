import { useEffect, useState } from 'react';
import { ApiError } from '../api/http';
import { fetchProjectPurgePreview, ProjectPurgePreview, ProjectPurgeResult, purgeProject } from '../api/projects';
import { useI18n } from '../hooks/useI18n';
import { formatSize } from '../utils/documentFormat';
import { Ico } from './Ico';

interface ArchiveProjectDeleteProps {
  projectId: string;
  projectName: string;
  /** The object is gone: the host takes it out of its list. */
  onDeleted: (result: ProjectPurgeResult) => void;
  onCancel: () => void;
}

/**
 * The confirmation of deleting an archived object for good (archive cleanup AC-5b). The server counts what goes (rooms, surfaces,
 * documents, photos and their files) and what holds the object (an issued / signed document) before anything is asked; nothing is
 * deleted until the owner has read it, ticked "I understand" and confirmed.
 */
export function ArchiveProjectDelete({ projectId, projectName, onDeleted, onCancel }: ArchiveProjectDeleteProps) {
  const { t } = useI18n();
  const text = t.archive;
  const [preview, setPreview] = useState<ProjectPurgePreview | null>(null);
  const [failed, setFailed] = useState<'load' | 'delete' | 'conflict' | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setFailed(null);
    setUnderstood(false);
    fetchProjectPurgePreview(projectId)
      .then((value) => {
        if (!cancelled) setPreview(value);
      })
      .catch(() => {
        if (!cancelled) setFailed('load');
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const confirm = async () => {
    if (busy || !understood) return;
    setBusy(true);
    setFailed(null);
    try {
      onDeleted(await purgeProject(projectId));
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'PROJECT_PURGE_CONFLICT') {
        setFailed('conflict');
        setUnderstood(false);
        fetchProjectPurgePreview(projectId).then(setPreview).catch(() => setFailed('load'));
      } else if (caught instanceof ApiError && caught.code === 'PROJECT_PURGE_BLOCKED') {
        // a document was issued meanwhile: show what holds the object instead of a vague error
        fetchProjectPurgePreview(projectId).then(setPreview).catch(() => setFailed('delete'));
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
    line(text.project_delete_rooms, preview.rooms);
    line(text.project_delete_surfaces, preview.surfaces);
    line(text.project_delete_openings, preview.openings);
    line(text.project_delete_inspections, preview.inspections);
    line(text.project_delete_estimates, preview.estimates);
    line(text.project_delete_documents, preview.documents);
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

  return (
    <div role="alertdialog" aria-label={text.project_delete_title} className="space-y-3 rounded-xl border border-red-300 p-3">
      <p className="break-words text-sm font-semibold text-slate-900">{text.project_delete_title}</p>
      {preview === null && failed !== 'load' && <p role="status" className="break-words text-sm text-slate-500">{text.client_delete_loading}</p>}
      {preview !== null && (
        <div className="space-y-2 break-words text-sm text-slate-700">
          {blocked ? (
            <div role="alert" className="space-y-1 text-red-700">
              <p className="font-semibold">{text.project_delete_blocked_title}</p>
              <ul className="list-disc pl-5">
                {preview.blockers.map((blocker) => (
                  <li key={blocker.protocol_id}>
                    {(text as Record<string, string>)[`project_blocker_${blocker.kind}`] ?? blocker.kind}
                  </li>
                ))}
              </ul>
              <p>{text.project_delete_blocked_hint}</p>
            </div>
          ) : (
            <>
              <p>{text.project_delete_intro.replace('{name}', projectName)}</p>
              {lines.length > 0 ? (
                <ul aria-label="project-delete-lines" className="list-disc pl-5">
                  {lines.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              ) : (
                <p>{text.project_delete_nothing}</p>
              )}
              {preview.sent_documents > 0 && <p className="text-slate-500">{text.project_delete_sent.replace('{count}', String(preview.sent_documents))}</p>}
              {preview.may_be_in_backups && <p className="text-slate-500">{text.project_delete_backups}</p>}
              <label className="flex min-h-11 items-start gap-3 font-semibold">
                <input
                  type="checkbox"
                  aria-label="project-delete-understood"
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
      {failed === 'delete' && <p role="alert" className="break-words text-sm text-red-700">{text.project_delete_error}</p>}
      {failed === 'conflict' && <p role="alert" className="break-words text-sm text-red-700">{text.project_delete_conflict}</p>}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          aria-label="project-delete-cancel"
          disabled={busy}
          onClick={onCancel}
          className="w-full min-h-11 rounded-xl bg-blue-600 px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          <Ico>✖️</Ico>{text.client_delete_cancel}
        </button>
        {!blocked && (
          <button
            type="button"
            aria-label="project-delete-confirm"
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
