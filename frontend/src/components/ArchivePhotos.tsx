import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchPhotoArchive } from '../api/photos';
import { useI18n } from '../hooks/useI18n';
import { ArchivedPhotoItem, PhotoAttachmentRead } from '../types/photo';
import { classifyPhotoError, PhotoErrorKey } from '../utils/photoErrors';
import { buildCaptionLine, buildLocationPath } from '../utils/photoCaption';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';
import { Ico } from './Ico';
import { PhotoThumbGrid } from './PhotoThumbGrid';
import { PhotoAttachmentChange, PhotoViewer } from './PhotoViewer';

type View = 'archive' | 'trash';

interface ArchivePhotosProps {
  /** The tab is shown; the component stays mounted so the count of the tab is known before it is opened. */
  active: boolean;
  /** Photos in the archive and in the trash (the count of the tab). */
  onTotals: (totals: { archived: number; trashed: number }) => void;
}

const PAGE = 100;

/**
 * The photos of the archive and of the trash across all objects (archive cleanup AC-3a). The same viewer as the photo section of a
 * surface does the work (restore, to the trash, out of the trash, delete for good); this list only finds the photo faster than
 * walking through the object, the room and the surface.
 */
export function ArchivePhotos({ active, onTotals }: ArchivePhotosProps) {
  const { t } = useI18n();
  const text = t.archive;
  const [view, setView] = useState<View>('archive');
  const [items, setItems] = useState<ArchivedPhotoItem[]>([]);
  const [totals, setTotals] = useState({ archived: 0, trashed: 0 });
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<PhotoErrorKey | null>(null);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const token = useRef(0);
  const imageRetryUsed = useRef(false);

  const load = useCallback(
    async (which: View, silent: boolean) => {
      const mine = ++token.current;
      if (!silent) {
        setStatus('loading');
        setError(null);
        imageRetryUsed.current = false;
      }
      try {
        const page = await fetchPhotoArchive(which === 'trash' ? 'trashed' : 'archived', PAGE);
        if (mine !== token.current) return;
        setItems(page.items);
        const next = { archived: page.archived_total, trashed: page.trashed_total };
        setTotals(next);
        onTotals(next);
        setStatus('ready');
      } catch (caught) {
        if (mine !== token.current || silent) return;
        setError(classifyPhotoError(caught).key);
        setStatus('error');
      }
    },
    [onTotals],
  );

  useEffect(() => {
    setViewerIndex(null);
    void load(view, false);
  }, [view, load]);

  const labels = useMemo(
    () => ({ wall: t.surfaces.wall, floor: t.surfaces.floor, ceiling: t.surfaces.ceiling }),
    [t],
  );

  const captionFor = useCallback(
    (item: ArchivedPhotoItem) => {
      const { place } = item;
      const segments: Array<string | null> = [item.project_name, place.room_name];
      if (place.surface_name) {
        segments.push(getSurfaceDisplayName({ name: place.surface_name, surface_type: place.surface_type ?? 'OTHER' }, labels));
      }
      if (place.opening_type) {
        const kind = place.opening_type === 'DOOR' ? t.openings.door : place.opening_type === 'WINDOW' ? t.openings.window : t.openings.other;
        segments.push(place.opening_name ? `${kind} (${place.opening_name})` : kind);
      }
      // a receipt or an invoice: the object, then the settlements, then the record it belongs to (IA-3)
      if (place.payment_title) segments.push(t.payments.title, place.payment_title);
      // the segments the context does not have are left out (an object photo has no room), not shown as unknown
      const known = segments.filter((segment): segment is string => Boolean(segment && segment.trim()));
      return buildCaptionLine(buildLocationPath(known, t.photos.caption), item.asset, t.photos.caption);
    },
    [labels, t],
  );

  const handleImageError = () => {
    if (imageRetryUsed.current) return;
    imageRetryUsed.current = true;
    void load(view, true); // the signed links may have expired: one silent refresh
  };

  const handleUpdated = (attachment: PhotoAttachmentRead) => {
    setItems((previous) => previous.map((entry) => (entry.attachment.id === attachment.id ? { ...entry, attachment } : entry)));
  };

  const handleAnnotationCount = (attachmentId: string, count: number) => {
    setItems((previous) => previous.map((entry) => (entry.attachment.id === attachmentId ? { ...entry, annotation_count: count } : entry)));
  };

  // Every change moves the photo out of the view it was listed in (restore, to the trash, out of the trash, delete).
  const handleRemoved = (attachment: PhotoAttachmentRead, action: PhotoAttachmentChange, detail?: { storagePending: boolean }) => {
    setNote(action === 'purged' && detail?.storagePending ? t.photos.section.purged_pending : null);
    const remaining = items.filter((entry) => entry.attachment.id !== attachment.id);
    setItems(remaining);
    setViewerIndex((current) => (current === null || remaining.length === 0 ? null : Math.min(current, remaining.length - 1)));
    void load(view, true); // the totals of both views and the rest of the list
  };

  const chip = (selected: boolean) =>
    `min-h-11 rounded-full border px-3 py-1.5 text-sm font-medium ${
      selected
        ? 'border-transparent bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]'
        : 'border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]'
    }`;

  if (!active) return null;

  const total = view === 'trash' ? totals.trashed : totals.archived;
  return (
    <div aria-label="archive-photos" className="space-y-3">
      <p className="break-words text-sm text-[var(--tg-theme-hint-color)]">{text.photos_intro}</p>
      <div role="group" aria-label={text.photos_view_group} className="flex flex-wrap gap-2">
        <button type="button" aria-pressed={view === 'archive'} className={chip(view === 'archive')} onClick={() => setView('archive')}>
          {t.photos.section.view_archive} ({totals.archived})
        </button>
        <button type="button" aria-pressed={view === 'trash'} className={chip(view === 'trash')} onClick={() => setView('trash')}>
          {t.photos.section.view_trash} ({totals.trashed})
        </button>
      </div>
      {view === 'trash' && <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">{t.photos.section.trash_hint}</p>}
      {note && <p role="status" className="break-words text-sm text-[var(--tg-theme-hint-color)]">{note}</p>}

      {status === 'loading' && <p className="text-sm text-[var(--tg-theme-hint-color)]">{t.photos.section.loading}</p>}
      {status === 'error' && (
        <div className="space-y-2">
          <p role="alert" className="break-words text-sm text-[var(--tg-theme-destructive-text-color)]">
            {error ? t.photos.errors[error] : text.photos_error}
          </p>
          <button
            type="button"
            aria-label="archive-photos-retry"
            onClick={() => void load(view, false)}
            className="min-h-11 w-full rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color)]"
          >
            <Ico>🔄</Ico>{text.retry}
          </button>
        </div>
      )}
      {status === 'ready' && items.length === 0 && (
        <p aria-label="archive-empty-photos" className="py-6 text-center text-sm text-slate-400">
          {view === 'trash' ? t.photos.section.empty_trash : t.photos.section.empty_archive}
        </p>
      )}
      {status === 'ready' && items.length > 0 && (
        <>
          <PhotoThumbGrid
            items={items}
            captionFor={(item) => captionFor(item as ArchivedPhotoItem)}
            onOpen={setViewerIndex}
            onImageError={handleImageError}
            hasMore={false}
            loadingMore={false}
            onShowMore={() => undefined}
          />
          {total > items.length && (
            <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">
              {text.photos_shown.replace('{shown}', String(items.length)).replace('{total}', String(total))}
            </p>
          )}
        </>
      )}

      {viewerIndex !== null &&
        items[viewerIndex] &&
        createPortal(
          <PhotoViewer
            projectId={items[viewerIndex].project_id}
            items={items}
            index={viewerIndex}
            archivedView
            trashView={view === 'trash'}
            captionFor={(item) => captionFor(item as ArchivedPhotoItem)}
            onIndexChange={setViewerIndex}
            onClose={() => setViewerIndex(null)}
            onAttachmentUpdated={handleUpdated}
            onAnnotationCount={handleAnnotationCount}
            onAttachmentRemoved={handleRemoved}
            onRefresh={() => void load(view, false)}
          />,
          document.body,
        )}
    </div>
  );
}
