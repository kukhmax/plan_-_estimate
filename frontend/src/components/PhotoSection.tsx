import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchPhotos } from '../api/photos';
import { useI18n } from '../hooks/useI18n';
import { subscribePhotoUploadDone, usePhotoUploadQueue } from '../hooks/usePhotoUploadQueue';
import { usePhotoStorage } from '../hooks/usePhotoStorage';
import {
  PHOTO_CATEGORIES,
  PhotoAttachmentRead,
  PhotoCaptureSource,
  PhotoCategory,
  PhotoContext,
  PhotoListItem,
  PhotoListParams,
  PhotoTarget,
} from '../types/photo';
import { buildCaptionLine } from '../utils/photoCaption';
import { PhotoErrorKey, classifyPhotoError } from '../utils/photoErrors';
import { attachmentTarget, targetIdOf } from '../utils/photoTarget';
import { MAX_FILES_PER_SELECTION, QueueItem } from '../utils/photoUploadQueue';
import { PhotoPicker } from './PhotoPicker';
import { PhotoThumbGrid } from './PhotoThumbGrid';
import { PhotoUploadQueueList } from './PhotoUploadQueueList';
import { PhotoViewer } from './PhotoViewer';

// The reusable photo section (contract §3, §7): expanded INLINE inside its card by the host (the host owns the
// corner `PhotoEntryButton` and mounts this component only while expanded, so nothing is fetched while collapsed).
// PROJECT lists every photo of the object (C-3); ROOM / SURFACE / OPENING list their own.

export const PHOTO_PAGE_SIZE = 30;

interface PhotoSectionProps {
  projectId: string;
  context: PhotoContext;
  /** room / surface / opening id for the matching context; omitted for PROJECT. */
  targetId?: string;
  /** Location text of the caption line: fixed for a leaf card, a resolver for the project-wide list. */
  locationLabel: string | ((attachment: PhotoAttachmentRead) => string);
  /**
   * Count correction for archive / restore done in the viewer (the attachment's own context and target).
   * Upload completions are NOT reported here: the host counts them once, whether or not a section is open.
   */
  onCountAdjust?: (context: PhotoContext, targetId: string | undefined, delta: number) => void;
}

function buildTarget(projectId: string, context: PhotoContext, targetId: string | undefined): PhotoTarget {
  return {
    projectId,
    context,
    roomId: context === 'ROOM' ? targetId : undefined,
    surfaceId: context === 'SURFACE' ? targetId : undefined,
    openingId: context === 'OPENING' ? targetId : undefined,
  };
}

export function PhotoSection({ projectId, context, targetId, locationLabel, onCountAdjust }: PhotoSectionProps) {
  const { t } = useI18n();
  const projectWide = context === 'PROJECT';
  const storage = usePhotoStorage();
  const queue = usePhotoUploadQueue(projectId);

  const [archived, setArchived] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<PhotoCategory | null>(null);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [items, setItems] = useState<PhotoListItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadError, setLoadError] = useState<PhotoErrorKey | null>(null);
  const [moreError, setMoreError] = useState<PhotoErrorKey | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [pickerNote, setPickerNote] = useState<string | null>(null);

  const requestToken = useRef(0);
  const imageRetryUsed = useRef(false);
  const urlsExpireAt = useRef<number | null>(null);

  const listParams = useCallback(
    (cursor?: string): PhotoListParams => ({
      ...(projectWide
        ? {}
        : {
            context,
            roomId: context === 'ROOM' ? targetId : undefined,
            surfaceId: context === 'SURFACE' ? targetId : undefined,
            openingId: context === 'OPENING' ? targetId : undefined,
          }),
      archived,
      category: categoryFilter ?? undefined,
      limit: PHOTO_PAGE_SIZE,
      cursor,
    }),
    [projectWide, context, targetId, archived, categoryFilter],
  );

  const rememberExpiry = (iso: string | null) => {
    const parsed = iso ? Date.parse(iso) : NaN;
    urlsExpireAt.current = Number.isNaN(parsed) ? null : parsed;
  };

  /** `silent` keeps what is on screen (link refresh, upload completion); otherwise it is a fresh first load. */
  const load = useCallback(
    async (silent: boolean) => {
      const token = ++requestToken.current;
      if (!silent) {
        setStatus('loading');
        setLoadError(null);
        setMoreError(null);
        imageRetryUsed.current = false;
      }
      try {
        const page = await fetchPhotos(projectId, listParams());
        if (token !== requestToken.current) return;
        setItems(page.items);
        setNextCursor(page.next_cursor);
        rememberExpiry(page.urls_expire_at);
        setStatus('ready');
      } catch (caught) {
        if (token !== requestToken.current || silent) return;
        setLoadError(classifyPhotoError(caught).key);
        setStatus('error');
      }
    },
    [projectId, listParams],
  );

  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  }, [load]);

  useEffect(() => {
    void load(false);
  }, [load]);

  const showMore = async () => {
    if (!nextCursor || loadingMore) return;
    const token = requestToken.current;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const page = await fetchPhotos(projectId, listParams(nextCursor));
      if (token !== requestToken.current) return;
      setItems((previous) => {
        const known = new Set(previous.map((entry) => entry.attachment.id));
        return [...previous, ...page.items.filter((entry) => !known.has(entry.attachment.id))];
      });
      setNextCursor(page.next_cursor);
      rememberExpiry(page.urls_expire_at);
    } catch (caught) {
      const info = classifyPhotoError(caught);
      if (info.code === 'PHOTO_CURSOR_INVALID') void load(false); // stale cursor: start over (contract §6)
      else setMoreError(info.key);
    } finally {
      setLoadingMore(false);
    }
  };

  // Signed links expire (default 300 s): coming back to the app after they did refreshes the list (contract §7b).
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      const expiry = urlsExpireAt.current;
      if (expiry !== null && Date.now() > expiry) void loadRef.current(true);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, []);

  // A thumbnail failed to load: refetch the links ONCE per fresh load (never a loop on a genuinely broken image).
  const handleImageError = () => {
    if (imageRetryUsed.current) return;
    imageRetryUsed.current = true;
    void load(true);
  };

  const isRelevant = useCallback(
    (item: QueueItem) =>
      item.target.projectId === projectId &&
      (projectWide || (item.target.context === context && targetIdOf(item.target) === targetId)),
    [projectId, projectWide, context, targetId],
  );

  const { dismiss } = queue;
  useEffect(
    () =>
      subscribePhotoUploadDone((item) => {
        if (!isRelevant(item)) return;
        void (async () => {
          await loadRef.current(true);
          dismiss(item.id); // the photo is in the grid now: the transient row can go
        })();
      }),
    [isRelevant, dismiss],
  );

  const visibleQueue = useMemo(() => queue.items.filter(isRelevant), [queue.items, isRelevant]);

  const handleFiles = (files: File[], source: PhotoCaptureSource) => {
    const result = queue.enqueue(files, buildTarget(projectId, context, targetId), source);
    setPickerNote(
      result.ignored > 0 ? t.photos.picker.too_many_selected.replace('{count}', String(MAX_FILES_PER_SELECTION)) : null,
    );
  };

  const captionFor = useCallback(
    (item: PhotoListItem) =>
      buildCaptionLine(
        typeof locationLabel === 'function' ? locationLabel(item.attachment) : locationLabel,
        item.asset,
        t.photos.caption,
      ),
    [locationLabel, t],
  );

  const handleAttachmentUpdated = (attachment: PhotoAttachmentRead) => {
    setItems((previous) =>
      previous.map((entry) => (entry.attachment.id === attachment.id ? { ...entry, attachment } : entry)),
    );
  };

  const handleAttachmentRemoved = (attachment: PhotoAttachmentRead, action: 'archived' | 'restored') => {
    const remaining = items.filter((entry) => entry.attachment.id !== attachment.id);
    setItems(remaining);
    const { context: attachmentContext, targetId: attachmentTargetId } = attachmentTarget(attachment);
    onCountAdjust?.(attachmentContext, attachmentTargetId, action === 'archived' ? -1 : 1);
    setViewerIndex((current) => {
      if (current === null || remaining.length === 0) return null;
      return Math.min(current, remaining.length - 1);
    });
  };

  const mediaUnavailable = storage.status === 'ready' && !storage.mediaAvailable;
  const canUpload = storage.status === 'ready' && storage.uploadsEnabled && storage.mediaAvailable;
  const uploadsOffNote =
    storage.status === 'ready' && storage.mediaAvailable && !storage.uploadsEnabled
      ? storage.state === 'FULL'
        ? t.photos.storage.full
        : t.photos.section.uploads_off_note
      : null;

  const chip = (selected: boolean) =>
    `min-h-11 rounded-full border px-3 py-1.5 text-sm font-medium ${
      selected
        ? 'border-transparent bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]'
        : 'border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]'
    }`;

  return (
    <section aria-label={t.photos.section.title} className="min-w-0 space-y-3">
      {canUpload && <PhotoPicker onFiles={handleFiles} />}
      {canUpload && storage.state === 'WARNING' && (
        <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">{t.photos.storage.warning}</p>
      )}
      {uploadsOffNote && <p className="break-words text-sm text-[var(--tg-theme-hint-color)]">{uploadsOffNote}</p>}
      {pickerNote && (
        <p role="status" className="break-words text-xs text-[var(--tg-theme-hint-color)]">
          {pickerNote}
        </p>
      )}

      <PhotoUploadQueueList
        items={visibleQueue}
        onCancel={queue.cancel}
        onRetry={queue.retry}
        onRetryAsNew={queue.retryAsNew}
        onDismiss={queue.dismiss}
      />

      {mediaUnavailable ? (
        <p className="break-words text-sm text-[var(--tg-theme-hint-color)]">{t.photos.section.media_unavailable_note}</p>
      ) : (
        <div className="space-y-3">
          {archived && (
            <h4 className="text-sm font-semibold text-[var(--tg-theme-text-color)]">{t.photos.section.archive_view_title}</h4>
          )}
          {status === 'loading' && (
            <p role="status" className="text-sm text-[var(--tg-theme-hint-color)]">
              {t.photos.section.loading}
            </p>
          )}
          {status === 'error' && (
            <div className="space-y-2">
              <p role="alert" className="break-words text-sm text-[var(--tg-theme-destructive-text-color)]">
                {loadError ? t.photos.errors[loadError] : t.photos.section.load_error}
              </p>
              <button
                type="button"
                onClick={() => void load(false)}
                className="min-h-11 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color)]"
              >
                {t.photos.section.retry}
              </button>
            </div>
          )}
          {status === 'ready' && items.length === 0 && (
            <p className="text-sm text-[var(--tg-theme-hint-color)]">
              {archived ? t.photos.section.empty_archive : t.photos.section.empty}
            </p>
          )}
          {status === 'ready' && items.length > 0 && (
            <PhotoThumbGrid
              items={items}
              captionFor={captionFor}
              onOpen={setViewerIndex}
              onImageError={handleImageError}
              hasMore={nextCursor !== null}
              loadingMore={loadingMore}
              onShowMore={() => void showMore()}
              groupByDay={projectWide}
            />
          )}
          {moreError && (
            <p role="alert" className="break-words text-sm text-[var(--tg-theme-destructive-text-color)]">
              {t.photos.errors[moreError]}
            </p>
          )}
        </div>
      )}

      {!mediaUnavailable && (
        <div className="space-y-2">
          <button
            type="button"
            aria-expanded={optionsOpen}
            aria-label={t.photos.section.options_toggle}
            onClick={() => setOptionsOpen((open) => !open)}
            className="min-h-11 rounded-xl px-2 py-2 text-sm font-semibold text-[var(--tg-theme-link-color)]"
          >
            {t.photos.section.options} {optionsOpen ? '▴' : '▾'}
          </button>
          {optionsOpen && (
            <div className="space-y-3">
              <button
                type="button"
                aria-pressed={archived}
                onClick={() => setArchived((value) => !value)}
                className="min-h-11 w-full rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color)]"
              >
                {archived ? t.photos.section.hide_archive : t.photos.section.show_archive}
              </button>
              {projectWide && (
                <div role="group" aria-label={t.photos.viewer.category} className="flex flex-wrap gap-2">
                  <button type="button" aria-pressed={categoryFilter === null} className={chip(categoryFilter === null)} onClick={() => setCategoryFilter(null)}>
                    {t.photos.section.filter_all}
                  </button>
                  {PHOTO_CATEGORIES.map((category) => (
                    <button
                      key={category}
                      type="button"
                      aria-pressed={categoryFilter === category}
                      className={chip(categoryFilter === category)}
                      onClick={() => setCategoryFilter(category)}
                    >
                      {t.photos.category[category]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {viewerIndex !== null && items[viewerIndex] && (
        <PhotoViewer
          projectId={projectId}
          items={items}
          index={viewerIndex}
          archivedView={archived}
          captionFor={captionFor}
          onIndexChange={setViewerIndex}
          onClose={() => setViewerIndex(null)}
          onAttachmentUpdated={handleAttachmentUpdated}
          onAttachmentRemoved={handleAttachmentRemoved}
          onRefresh={() => void load(false)}
        />
      )}
    </section>
  );
}
