import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchPhotos } from '../api/photos';
import { useI18n } from '../hooks/useI18n';
import { subscribePhotoUploadDone, usePhotoUploadQueue } from '../hooks/usePhotoUploadQueue';
import { PhotoCountScope } from '../hooks/usePhotoCounts';
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
  /** room / surface / opening id for the matching context; the inspection for INSPECTION, the finding row for FINDING; omitted for PROJECT. */
  targetId?: string;
  /** INSPECTION only: the checklist question a section documents; without it the section is the whole inspection's. */
  questionId?: string;
  /** FINDING only: the finding's lineage — the section lists the photos of every row of it and uploads to `targetId`. */
  lineageId?: string;
  /** WORK only (`targetId` = the surface): one planned work of its plan; without it the section lists every execution photo of the surface. */
  occurrenceKey?: string;
  /** WORK only: the category the host suggests for NEW photos (Realizacja derives it from the work's status); the viewer can change it. */
  defaultCategory?: PhotoCategory;
  /** WORK without `occurrenceKey`: keys to leave out (the plan's current works), so the section lists only DETACHED evidence. */
  excludeKeys?: ReadonlySet<string>;
  /** The room a SURFACE section belongs to; travels with each upload so the room's total can follow. */
  roomId?: string;
  /**
   * Whether this section offers the picker and shows the upload queue. Photos are ADDED only on surfaces; the object's
   * and a room's sections (PROJECT / ROOM) list every photo below them for viewing and editing only. Default: no.
   */
  allowUpload?: boolean;
  /** Location text of the caption line: fixed for a surface card, a resolver for the aggregated lists. */
  locationLabel: string | ((attachment: PhotoAttachmentRead) => string);
  /**
   * Count correction for archive / restore done in the viewer (the attachment's own context and target; the room when
   * this section knows it). Upload completions are NOT reported here: the host counts them once, whether or not a
   * section is open.
   */
  onCountAdjust?: (context: PhotoContext, targetId: string | undefined, delta: number, roomId?: string, scope?: PhotoCountScope) => void;
}

function buildTarget(
  projectId: string,
  context: PhotoContext,
  targetId: string | undefined,
  roomId: string | undefined,
  questionId: string | undefined,
  lineageId: string | undefined,
  occurrenceKey: string | undefined,
  category: PhotoCategory | undefined,
): PhotoTarget {
  return {
    projectId,
    context,
    inspectionId: context === 'INSPECTION' ? targetId : undefined,
    questionId: context === 'INSPECTION' ? questionId : undefined,
    findingId: context === 'FINDING' ? targetId : undefined,
    lineageId: context === 'FINDING' ? lineageId : undefined,
    // Not sent for a SURFACE (the server needs only its own id); it lets the host keep the room's total in step.
    roomId: context === 'ROOM' ? targetId : roomId,
    surfaceId: context === 'SURFACE' || context === 'WORK' ? targetId : undefined,
    openingId: context === 'OPENING' ? targetId : undefined,
    occurrenceKey: context === 'WORK' ? occurrenceKey : undefined,
    category: context === 'WORK' ? category : undefined,
  };
}

export function PhotoSection({
  projectId,
  context,
  targetId,
  questionId,
  lineageId,
  occurrenceKey,
  defaultCategory,
  excludeKeys,
  roomId,
  allowUpload = false,
  locationLabel,
  onCountAdjust,
}: PhotoSectionProps) {
  const { t } = useI18n();
  // The object and a room list everything below them; the other sections list their own target only.
  const aggregated = context === 'PROJECT' || context === 'ROOM';
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
      ...(context === 'PROJECT'
        ? { siteOnly: true } // the object-wide list keeps showing the site photos; inspection evidence lives in the inspection
        : context === 'ROOM'
          ? { inRoomId: targetId }
          : context === 'INSPECTION'
            ? { context, inspectionId: targetId, questionId }
            : context === 'FINDING'
              ? lineageId
                ? { lineageId }
                : { context, findingId: targetId }
              : context === 'WORK'
                ? { context, surfaceId: targetId, occurrenceKey }
                : {
                    context,
                    surfaceId: context === 'SURFACE' ? targetId : undefined,
                    openingId: context === 'OPENING' ? targetId : undefined,
                  }),
      archived,
      category: categoryFilter ?? undefined,
      limit: PHOTO_PAGE_SIZE,
      cursor,
    }),
    [context, targetId, questionId, lineageId, occurrenceKey, archived, categoryFilter],
  );

  // Execution evidence of works that left the plan: the plan's current keys are left out. A page that is empty after
  // that is skipped (the next one is read) so the grid never stops at an empty page while more evidence exists.
  const readPage = useCallback(
    async (cursor?: string) => {
      let next = cursor;
      for (let guard = 0; ; guard += 1) {
        const page = await fetchPhotos(projectId, listParams(next));
        const kept = excludeKeys
          ? page.items.filter((entry) => !entry.attachment.occurrence_key || !excludeKeys.has(entry.attachment.occurrence_key))
          : page.items;
        if (kept.length > 0 || !page.next_cursor || guard >= 9) return { ...page, items: kept };
        next = page.next_cursor;
      }
    },
    [projectId, listParams, excludeKeys],
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
        const page = await readPage();
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
    [readPage],
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
      const page = await readPage(nextCursor);
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
      (context === 'PROJECT' ||
        (context === 'ROOM'
          ? item.target.roomId === targetId
          : context === 'INSPECTION'
            ? item.target.context === 'INSPECTION' &&
              item.target.inspectionId === targetId &&
              (questionId === undefined || item.target.questionId === questionId)
            : context === 'FINDING'
              ? item.target.context === 'FINDING' &&
                (lineageId ? item.target.lineageId === lineageId : item.target.findingId === targetId)
              : context === 'WORK'
                ? item.target.context === 'WORK' &&
                  item.target.surfaceId === targetId &&
                  (occurrenceKey === undefined || item.target.occurrenceKey === occurrenceKey)
                : item.target.context === context && targetIdOf(item.target) === targetId)),
    [projectId, context, targetId, questionId, lineageId, occurrenceKey],
  );

  const { dismiss } = queue;
  useEffect(
    () =>
      subscribePhotoUploadDone((item) => {
        if (!isRelevant(item)) return;
        void (async () => {
          await loadRef.current(true);
          // The photo is in the grid now: the transient row can go — but only the section that shows the queue rows
          // removes them (an aggregated section reloads its list and leaves the rows to the surface's own section).
          if (allowUpload) dismiss(item.id);
        })();
      }),
    [isRelevant, dismiss, allowUpload],
  );

  const visibleQueue = useMemo(
    () => (allowUpload ? queue.items.filter(isRelevant) : []),
    [queue.items, isRelevant, allowUpload],
  );

  const handleFiles = (files: File[], source: PhotoCaptureSource) => {
    const result = queue.enqueue(
      files,
      buildTarget(projectId, context, targetId, roomId, questionId, lineageId, occurrenceKey, defaultCategory),
      source,
    );
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
    const {
      context: attachmentContext,
      targetId: attachmentTargetId,
      questionId: attachmentQuestionId,
      occurrenceKey: attachmentOccurrenceKey,
    } = attachmentTarget(attachment);
    onCountAdjust?.(
      attachmentContext,
      attachmentTargetId,
      action === 'archived' ? -1 : 1,
      context === 'ROOM' ? targetId : roomId,
      {
        questionId: attachmentQuestionId,
        lineageId: context === 'FINDING' ? lineageId : undefined,
        occurrenceKey: attachmentOccurrenceKey,
      },
    );
    setViewerIndex((current) => {
      if (current === null || remaining.length === 0) return null;
      return Math.min(current, remaining.length - 1);
    });
  };

  const mediaUnavailable = storage.status === 'ready' && !storage.mediaAvailable;
  const canUpload = allowUpload && storage.status === 'ready' && storage.uploadsEnabled && storage.mediaAvailable;
  const uploadsOffNote =
    allowUpload && storage.status === 'ready' && storage.mediaAvailable && !storage.uploadsEnabled
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
    <section
      aria-label={t.photos.section.title}
      // Its own surface: host cards are often a fixed white, so the theme text colours need a theme background.
      className="min-w-0 space-y-3 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] p-3 text-[var(--tg-theme-text-color)]"
    >
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
              {archived
                ? t.photos.section.empty_archive
                : aggregated
                  ? t.photos.section.empty_aggregated
                  : t.photos.section.empty}
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
              groupByDay={aggregated}
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
              {aggregated && (
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

      {/* A portal: the full-screen sheet must not inherit the card's spacing (`space-y-*` shifted it by 12 px), its
          stacking context or its clipping. */}
      {viewerIndex !== null &&
        items[viewerIndex] &&
        createPortal(
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
          />,
          document.body,
        )}
    </section>
  );
}
