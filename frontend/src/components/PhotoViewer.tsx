import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  archivePhotoAttachment,
  trashPhotoAttachment,
  untrashPhotoAttachment,
  createPhotoAnnotation,
  deletePhotoAnnotation,
  fetchPhoto,
  fetchPhotoPurgePreview,
  patchPhotoAnnotation,
  patchPhotoAttachment,
  purgePhotoAttachment,
  restorePhotoAttachment,
} from '../api/photos';
import { usePhotoBackRegistration } from '../hooks/PhotoBackContext';
import { useI18n } from '../hooks/useI18n';
import {
  PHOTO_CATEGORIES,
  PhotoAnnotationRead,
  PhotoAttachmentPatch,
  PhotoAttachmentRead,
  PhotoCategory,
  PhotoDetailResponse,
  PhotoListItem,
  PhotoPurgePreview,
} from '../types/photo';
import { formatCapturedAt, formatUploadedAt, isCapturedMuchOlderThanUpload } from '../utils/photoCaption';
import { OUTLINE_POINT_BUDGET, OutlinePoint, outlineFromStroke } from '../utils/outline';
import { PhotoErrorKey, classifyPhotoError } from '../utils/photoErrors';
import { formatSize } from '../utils/documentFormat';
import { hapticNotify } from '../utils/telegramHaptics';
import { PhotoFullscreen } from './PhotoFullscreen';
import { ChevronLeftIcon, ChevronRightIcon, CloseIcon, ExpandIcon, PinIcon } from './PhotoIcons';
import { PointMarkerLayer } from './PointMarkerLayer';
import { PointMarkerPopup } from './PointMarkerPopup';
import { Ico } from './Ico';

// Full-screen sheet (contract §7). Loads the detail for the DISPLAY image (lists carry thumbnails only), edits the
// metadata of THIS attachment (caption / category / report flag), archives or restores it in this context.
// No download, no share, no delete, no original. Closing is guarded: an unsaved caption is saved first.
// A tap on the photo (or the corner button) opens it on the whole screen, where it can be zoomed with two fingers.

export const CAPTION_MAX_LENGTH = 1000;
/** Used until the detail (which names the server's limit) has arrived. */
const DEFAULT_MARKER_LIMIT = 10;
/** Signed links are refetched this long before they expire (contract §7c). */
const URL_REFRESH_MARGIN_MS = 30_000;

/** What the viewer did to the attachment: archive, restore, put it in the trash (AC-1) or take it out of the trash. */
export type PhotoAttachmentChange = 'archived' | 'restored' | 'trashed' | 'untrashed' | 'purged';

interface PhotoViewerProps {
  projectId: string;
  items: readonly PhotoListItem[];
  index: number;
  archivedView: boolean;
  /** Archive cleanup AC-1: the list is the trash (the archived view too). */
  trashView?: boolean;
  captionFor: (item: PhotoListItem) => string;
  onIndexChange: (index: number) => void;
  onClose: () => void;
  onAttachmentUpdated: (attachment: PhotoAttachmentRead) => void;
  /** `detail.storagePending` (only for 'purged'): the files of the deleted photo are removed from the storage by a retry. */
  onAttachmentRemoved: (attachment: PhotoAttachmentRead, action: PhotoAttachmentChange, detail?: { storagePending: boolean }) => void;
  /** The photo vanished meanwhile: the host should refetch its list. */
  onRefresh?: () => void;
  /** The number of point markers on an attachment changed (the grid shows it on the tile). */
  onAnnotationCount?: (attachmentId: string, count: number) => void;
}

interface CachedDetail {
  detail: PhotoDetailResponse;
}

function isFresh(entry: CachedDetail | undefined): entry is CachedDetail {
  if (!entry) return false;
  const expires = entry.detail.urls_expire_at ? Date.parse(entry.detail.urls_expire_at) : NaN;
  return Number.isNaN(expires) || expires - URL_REFRESH_MARGIN_MS > Date.now();
}

const iconButton =
  'flex min-h-11 min-w-11 items-center justify-center rounded-full bg-black/60 text-white disabled:opacity-40';
const secondaryButton =
  'min-h-11 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color)] disabled:opacity-50';
const primaryButton =
  'min-h-11 rounded-xl bg-[var(--tg-theme-button-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-button-text-color)] disabled:opacity-50';

export function PhotoViewer({
  projectId,
  items,
  index,
  archivedView,
  trashView = false,
  captionFor,
  onIndexChange,
  onClose,
  onAttachmentUpdated,
  onAttachmentRemoved,
  onRefresh,
  onAnnotationCount,
}: PhotoViewerProps) {
  const { t } = useI18n();
  const item = items[index];
  const attachment = item?.attachment;
  const assetId = item?.asset.id;

  const cache = useRef(new Map<string, CachedDetail>());
  const imageRetried = useRef(new Set<string>());
  const closeButton = useRef<HTMLButtonElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  const [detail, setDetail] = useState<PhotoDetailResponse | null>(null);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadError, setLoadError] = useState<PhotoErrorKey | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);

  const [caption, setCaption] = useState(attachment?.caption ?? '');
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  // Archive cleanup AC-2: the panel "what will be deleted" of the final deletion (opened from the trash view)
  const [purge, setPurge] = useState<{ state: 'loading' | 'ready'; preview: PhotoPurgePreview | null } | null>(null);
  const [error, setError] = useState<PhotoErrorKey | null>(null);
  const [saved, setSaved] = useState(false);

  // Point markers (Stage 14G): placing mode, the marker whose pop-up is open, and the state of the last marker call.
  const [markMode, setMarkMode] = useState(false);
  const [selectedMarkerId, setSelectedMarkerId] = useState<string | null>(null);
  const [markerBusy, setMarkerBusy] = useState(false);
  const [markerError, setMarkerError] = useState<PhotoErrorKey | null>(null);
  // The marker whose contour is being drawn on the full-screen picture (Stage 14G.5), and a refused stroke.
  const [drawingMarkerId, setDrawingMarkerId] = useState<string | null>(null);
  const [strokeTooShort, setStrokeTooShort] = useState(false);

  // ---- detail (display URL) ----
  useEffect(() => {
    if (!assetId) return;
    setImageFailed(false);
    const cached = cache.current.get(assetId);
    if (isFresh(cached)) {
      setDetail(cached.detail);
      setLoadState('ready');
      return;
    }
    let cancelled = false;
    setLoadState('loading');
    setLoadError(null);
    setDetail(null);
    fetchPhoto(projectId, assetId)
      .then((result) => {
        cache.current.set(assetId, { detail: result });
        if (cancelled) return;
        setDetail(result);
        setLoadState('ready');
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        const info = classifyPhotoError(caught);
        if (info.refetch === 'list') {
          onRefresh?.();
          onClose();
          return;
        }
        setLoadError(info.key);
        setLoadState('error');
      });
    return () => {
      cancelled = true;
    };
    // onRefresh / onClose are intentionally not dependencies: a new identity must not refetch the photo.
  }, [projectId, assetId, reloadTick]);

  // A different attachment: no stale messages or confirmation.
  useEffect(() => {
    setConfirmArchive(false);
    setPurge(null);
    setError(null);
    setSaved(false);
    setMarkMode(false);
    setSelectedMarkerId(null);
    setMarkerError(null);
    setDrawingMarkerId(null);
    setStrokeTooShort(false);
  }, [attachment?.id]);

  const attachmentId = attachment?.id;
  // A photo of a receipt or an invoice (PAYMENT) takes no point markers: nothing on it is to be pointed at.
  const markersAllowed = attachment?.context !== 'PAYMENT';
  const markers = useMemo(
    () => (detail && attachmentId && markersAllowed ? detail.annotations.filter((marker) => marker.attachment_id === attachmentId) : []),
    [detail, attachmentId, markersAllowed],
  );

  // The draft follows the stored caption (another attachment, or the saved value coming back).
  useEffect(() => {
    setCaption(attachment?.caption ?? '');
  }, [attachment?.id, attachment?.caption]);

  const dirty = attachment ? caption.trim() !== (attachment.caption ?? '') : false;

  const apply = useCallback(
    async (patch: PhotoAttachmentPatch): Promise<boolean> => {
      if (!attachment) return false;
      setError(null);
      setSaved(false);
      try {
        const updated = await patchPhotoAttachment(projectId, attachment.id, patch);
        onAttachmentUpdated(updated);
        setSaved(true);
        hapticNotify('success');
        return true;
      } catch (caught) {
        const info = classifyPhotoError(caught);
        if (info.refetch === 'list') {
          onRefresh?.();
          onClose();
        } else {
          setError(info.key);
          hapticNotify('error');
        }
        return false;
      }
    },
    [attachment, projectId, onAttachmentUpdated, onRefresh, onClose],
  );

  const saveCaption = useCallback(async (): Promise<boolean> => {
    if (!dirty) return true;
    setSaving(true);
    try {
      const trimmed = caption.trim();
      return await apply({ caption: trimmed === '' ? null : trimmed });
    } finally {
      setSaving(false);
    }
  }, [dirty, caption, apply]);

  // Leaving (close, back, previous / next) saves a pending caption first and stays put when that fails.
  const requestClose = useCallback(async () => {
    if (await saveCaption()) onClose();
  }, [saveCaption, onClose]);

  const go = async (delta: number) => {
    if (await saveCaption()) onIndexChange(index + delta);
  };

  usePhotoBackRegistration(true, () => {
    void requestClose();
  });

  useEffect(() => {
    closeButton.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !fullscreen) void requestClose(); // the full-screen view closes itself first
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [requestClose, fullscreen]);

  // Another photo (or none to show): back to the normal view.
  useEffect(() => {
    setFullscreen(false);
  }, [assetId]);

  if (!item || !attachment) return null;
  const currentAssetId = item.asset.id;

  // ---- point markers ----
  const markerLimit = detail?.annotation_limit ?? DEFAULT_MARKER_LIMIT;
  // An archived attachment (or photo) shows its markers but cannot change them.
  const markersReadOnly = archivedView || attachment.archived_at !== null || item.asset.archived_at !== null;
  const atMarkerLimit = markers.length >= markerLimit;
  const selectedMarker = markers.find((marker) => marker.id === selectedMarkerId) ?? null;
  const imageShown = loadState === 'ready' && !!detail?.display_url && !imageFailed;
  const showMarkerControls = markersAllowed && imageShown && (!markersReadOnly || markers.length > 0);
  const placing = markMode && markersAllowed; // the switch is not offered on a read only photo, and placeMarker refuses it anyway

  const commitMarkers = (forAttachmentId: string, next: PhotoAnnotationRead[]) => {
    if (detail) {
      const merged: PhotoDetailResponse = {
        ...detail,
        annotations: [...detail.annotations.filter((marker) => marker.attachment_id !== forAttachmentId), ...next],
      };
      setDetail(merged);
      cache.current.set(detail.asset.id, { detail: merged });
    }
    onAnnotationCount?.(forAttachmentId, next.length);
  };

  const failMarkerCall = (caught: unknown) => {
    const info = classifyPhotoError(caught);
    if (info.refetch === 'list') {
      onRefresh?.();
      onClose();
      return;
    }
    if (info.key === 'marker_not_found') {
      // Deleted elsewhere: read the photo's markers again.
      setSelectedMarkerId(null);
      cache.current.delete(currentAssetId);
      setReloadTick((tick) => tick + 1);
    }
    setMarkerError(info.key);
    hapticNotify('error');
  };

  const placeMarker = async (x: number, y: number) => {
    if (markerBusy || markersReadOnly || !markersAllowed) return;
    if (atMarkerLimit) {
      setMarkerError('marker_limit');
      hapticNotify('error');
      return;
    }
    setMarkerBusy(true);
    setMarkerError(null);
    try {
      const created = await createPhotoAnnotation(projectId, attachment.id, { x, y });
      commitMarkers(attachment.id, [...markers, created]);
      setSelectedMarkerId(created.id); // the pop-up opens so the marker can be named at once (skippable)
      hapticNotify('success');
    } catch (caught) {
      failMarkerCall(caught);
    } finally {
      setMarkerBusy(false);
    }
  };

  const saveMarkerLabel = async (marker: PhotoAnnotationRead, label: string | null) => {
    setMarkerBusy(true);
    setMarkerError(null);
    try {
      const updated = await patchPhotoAnnotation(projectId, attachment.id, marker.id, { label });
      commitMarkers(
        attachment.id,
        markers.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
      setSelectedMarkerId(null);
      hapticNotify('success');
    } catch (caught) {
      failMarkerCall(caught);
    } finally {
      setMarkerBusy(false);
    }
  };

  // ---- contour around a defect ----
  const drawingMarker = markers.find((marker) => marker.id === drawingMarkerId) ?? null;
  const outlinePointBudget = Math.min(detail?.outline_max_points ?? OUTLINE_POINT_BUDGET, OUTLINE_POINT_BUDGET);

  const startDrawing = (marker: PhotoAnnotationRead) => {
    setSelectedMarkerId(null);
    setMarkerError(null);
    setStrokeTooShort(false);
    setMarkMode(false);
    setDrawingMarkerId(marker.id);
    setFullscreen(true); // drawn on the big picture, where it can be zoomed for accuracy
  };

  const saveOutline = async (marker: PhotoAnnotationRead, outline: OutlinePoint[] | null) => {
    setMarkerBusy(true);
    setMarkerError(null);
    try {
      const updated = await patchPhotoAnnotation(projectId, attachment.id, marker.id, { outline });
      commitMarkers(
        attachment.id,
        markers.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
      setSelectedMarkerId(null);
      setDrawingMarkerId(null);
      hapticNotify('success');
    } catch (caught) {
      failMarkerCall(caught);
    } finally {
      setMarkerBusy(false);
    }
  };

  const onStroke = (stroke: OutlinePoint[]) => {
    if (!drawingMarker || markerBusy) return;
    const outline = outlineFromStroke(stroke, outlinePointBudget);
    if (!outline) {
      setStrokeTooShort(true);
      hapticNotify('error');
      return;
    }
    setStrokeTooShort(false);
    void saveOutline(drawingMarker, outline);
  };

  const deleteMarker = async (marker: PhotoAnnotationRead) => {
    setMarkerBusy(true);
    setMarkerError(null);
    try {
      await deletePhotoAnnotation(projectId, attachment.id, marker.id);
      commitMarkers(
        attachment.id,
        markers.filter((entry) => entry.id !== marker.id),
      );
      setSelectedMarkerId(null);
      hapticNotify('success');
    } catch (caught) {
      failMarkerCall(caught);
    } finally {
      setMarkerBusy(false);
    }
  };

  // A tap on the picture: places a marker while placing, otherwise opens the full-screen view.
  const onPictureClick = (event: React.MouseEvent) => {
    if (!placing) {
      setFullscreen(true);
      return;
    }
    const rect = imageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    if (x >= 0 && x <= 1 && y >= 0 && y <= 1) void placeMarker(x, y);
  };

  const openPurge = async () => {
    if (!attachment) return;
    setError(null);
    setPurge({ state: 'loading', preview: null });
    try {
      const preview = await fetchPhotoPurgePreview(projectId, attachment.id);
      setPurge({ state: 'ready', preview });
    } catch (caught) {
      const info = classifyPhotoError(caught);
      setPurge(null);
      if (info.refetch === 'list') {
        onRefresh?.();
        onClose();
      } else {
        setError(info.key);
        hapticNotify('error');
      }
    }
  };

  const confirmPurge = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await purgePhotoAttachment(projectId, attachment.id);
      hapticNotify('success');
      setPurge(null);
      onAttachmentRemoved(attachment, 'purged', { storagePending: result.storage_pending });
    } catch (caught) {
      const info = classifyPhotoError(caught);
      if (info.refetch === 'list') {
        onRefresh?.();
        onClose();
      } else {
        setError(info.key);
        setPurge(null);
        hapticNotify('error');
      }
    } finally {
      setBusy(false);
    }
  };

  const changeArchiveState = async (action: Exclude<PhotoAttachmentChange, 'purged'>) => {
    setBusy(true);
    setError(null);
    try {
      const updated =
        action === 'archived'
          ? await archivePhotoAttachment(projectId, attachment.id)
          : action === 'restored'
            ? await restorePhotoAttachment(projectId, attachment.id)
            : action === 'trashed'
              ? await trashPhotoAttachment(projectId, attachment.id)
              : await untrashPhotoAttachment(projectId, attachment.id);
      hapticNotify('success');
      onAttachmentRemoved(updated, action);
    } catch (caught) {
      const info = classifyPhotoError(caught);
      if (info.refetch === 'list') {
        onRefresh?.();
        onClose();
      } else {
        setError(info.key);
        setConfirmArchive(false);
        hapticNotify('error');
      }
    } finally {
      setBusy(false);
    }
  };

  const onImageError = () => {
    if (!imageRetried.current.has(currentAssetId)) {
      imageRetried.current.add(currentAssetId); // one refetch of the signed links, then give up (no loop)
      cache.current.delete(currentAssetId);
      setReloadTick((tick) => tick + 1);
      return;
    }
    setImageFailed(true);
  };

  const capturedText = item.asset.captured_at ? formatCapturedAt(item.asset.captured_at) : null;
  const uploadedText = formatUploadedAt(item.asset.uploaded_at);
  const disabled = busy || saving || markerBusy;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.photos.viewer.dialog_label}
      className="fixed inset-0 z-50 flex flex-col bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)]"
    >
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        <div className="relative flex h-[50vh] shrink-0 items-center justify-center bg-black">
          {loadState === 'ready' && detail?.display_url && !imageFailed && (
            <div className="flex h-full w-full items-center justify-center" onClick={onPictureClick}>
              {/* The wrapper is exactly the picture's box, so the marker layer fills it (the box is 50vh high). */}
              <div className="relative max-w-full" style={{ lineHeight: 0 }}>
                <img
                  ref={imageRef}
                  src={detail.display_url}
                  alt={attachment.caption || t.photos.viewer.photo_alt}
                  referrerPolicy="no-referrer"
                  onError={onImageError}
                  className="block max-w-full object-contain"
                  style={{ maxHeight: '50vh' }}
                />
                {markers.length > 0 && (
                  <PointMarkerLayer markers={markers} selectedId={selectedMarkerId} onSelect={(marker) => setSelectedMarkerId(marker.id)} />
                )}
              </div>
            </div>
          )}
          {loadState === 'loading' && <p className="px-4 text-center text-sm text-white">{t.photos.viewer.loading}</p>}
          {(loadState === 'error' || imageFailed || (loadState === 'ready' && !detail?.display_url)) && (
            <div className="flex flex-col items-center gap-3 px-4 text-center">
              <p role="alert" className="break-words text-sm text-white">
                {loadState === 'error' && loadError ? t.photos.errors[loadError] : t.photos.viewer.image_unavailable}
              </p>
              <button
                type="button"
                className={secondaryButton}
                onClick={() => {
                  imageRetried.current.delete(currentAssetId);
                  cache.current.delete(currentAssetId);
                  setReloadTick((tick) => tick + 1);
                }}
              >
                <Ico>🔄</Ico>{t.photos.viewer.retry}
              </button>
            </div>
          )}

          <div className="absolute inset-x-2 top-2 flex items-center justify-between gap-2">
            <span className="rounded-full bg-black/60 px-3 py-1.5 text-xs font-semibold text-white">
              {t.photos.viewer.counter.replace('{current}', String(index + 1)).replace('{total}', String(items.length))}
            </span>
            <button
              ref={closeButton}
              type="button"
              aria-label={t.photos.viewer.close}
              className={iconButton}
              disabled={saving}
              onClick={() => void requestClose()}
            >
              <CloseIcon />
            </button>
          </div>
          {loadState === 'ready' && detail?.display_url && !imageFailed && (
            <button
              type="button"
              aria-label={t.photos.viewer.fullscreen_open}
              className={`${iconButton} absolute bottom-2 right-2`}
              onClick={() => setFullscreen(true)}
            >
              <ExpandIcon />
            </button>
          )}
          <button
            type="button"
            aria-label={t.photos.viewer.previous}
            className={`${iconButton} absolute left-2 top-1/2 -translate-y-1/2`}
            disabled={disabled || index === 0}
            onClick={() => void go(-1)}
          >
            <ChevronLeftIcon />
          </button>
          <button
            type="button"
            aria-label={t.photos.viewer.next}
            className={`${iconButton} absolute right-2 top-1/2 -translate-y-1/2`}
            disabled={disabled || index >= items.length - 1}
            onClick={() => void go(1)}
          >
            <ChevronRightIcon />
          </button>
        </div>

        <div className="space-y-3 p-4">
          {showMarkerControls && (
            <div data-testid="marker-controls" className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                {!markersReadOnly && (
                  <button
                    type="button"
                    aria-pressed={markMode}
                    disabled={disabled || (!markMode && atMarkerLimit)}
                    onClick={() => setMarkMode((on) => !on)}
                    className={`flex min-h-11 min-w-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold disabled:opacity-50 ${
                      markMode
                        ? 'bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]'
                        : 'border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]'
                    }`}
                  >
                    <PinIcon size={16} />
                    <span className="min-w-0 break-words text-left">{markMode ? t.photos.markers.add_done : t.photos.markers.add}</span>
                  </button>
                )}
                <span className="text-xs text-[var(--tg-theme-hint-color)]">
                  {t.photos.markers.count.replace('{count}', String(markers.length)).replace('{max}', String(markerLimit))}
                </span>
              </div>
              {markMode && !markersReadOnly && (
                <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">{t.photos.markers.hint_add}</p>
              )}
              {!markMode && markers.length > 0 && (
                <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">{t.photos.markers.hint_view}</p>
              )}
              {atMarkerLimit && !markersReadOnly && (
                <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">
                  {t.photos.markers.limit_reached.replace('{max}', String(markerLimit))}
                </p>
              )}
              {markerError && !selectedMarker && (
                <p role="alert" className="break-words text-sm font-medium text-[var(--tg-theme-destructive-text-color)]">
                  {t.photos.errors[markerError]}
                </p>
              )}
            </div>
          )}
          <p data-testid="viewer-caption-line" className="break-words text-sm font-medium">
            {captionFor(item)}
          </p>
          <dl className="space-y-0.5 text-xs text-[var(--tg-theme-hint-color)]">
            {capturedText && (
              <div className="flex flex-wrap gap-x-1.5">
                <dt>{t.photos.viewer.captured}:</dt>
                <dd>{capturedText}</dd>
              </div>
            )}
            {uploadedText && (
              <div className="flex flex-wrap gap-x-1.5">
                <dt>{t.photos.viewer.uploaded}:</dt>
                <dd>{uploadedText}</dd>
              </div>
            )}
          </dl>
          {isCapturedMuchOlderThanUpload(item.asset) && (
            <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">{t.photos.viewer.older_hint}</p>
          )}

          <label className="block space-y-1">
            <span className="text-xs font-medium text-[var(--tg-theme-hint-color)]">{t.photos.viewer.caption}</span>
            <textarea
              value={caption}
              maxLength={CAPTION_MAX_LENGTH}
              rows={3}
              disabled={disabled}
              placeholder={t.photos.viewer.caption_placeholder}
              onChange={(event) => {
                setCaption(event.target.value);
                setSaved(false);
              }}
              onBlur={() => {
                void saveCaption();
              }}
              className="min-h-20 w-full rounded-xl border px-3 py-2 text-base"
            />
          </label>
          {dirty && (
            <div className="flex flex-wrap gap-2">
              <button type="button" className={primaryButton} disabled={disabled} onClick={() => void saveCaption()}>
                <Ico>💾</Ico>{t.photos.viewer.save}
              </button>
              <button
                type="button"
                className={secondaryButton}
                disabled={disabled}
                onClick={() => setCaption(attachment.caption ?? '')}
              >
                <Ico>✖️</Ico>{t.photos.viewer.cancel}
              </button>
            </div>
          )}

          <label className="block space-y-1">
            <span className="text-xs font-medium text-[var(--tg-theme-hint-color)]">{t.photos.viewer.category}</span>
            <select
              value={attachment.category}
              disabled={disabled}
              onChange={(event) => {
                void (async () => {
                  setBusy(true);
                  await apply({ category: event.target.value as PhotoCategory });
                  setBusy(false);
                })();
              }}
              className="min-h-11 w-full rounded-xl border px-3 py-2 text-base"
            >
              {PHOTO_CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {t.photos.category[category]}
                </option>
              ))}
            </select>
          </label>

          <label className="flex min-h-11 items-center gap-3">
            <input
              type="checkbox"
              checked={attachment.include_in_report}
              disabled={disabled}
              onChange={(event) => {
                void (async () => {
                  setBusy(true);
                  await apply({ include_in_report: event.target.checked });
                  setBusy(false);
                })();
              }}
              className="h-5 w-5 shrink-0"
            />
            <span className="min-w-0 break-words text-sm">{t.photos.viewer.include_in_report}</span>
          </label>

          {error && (
            <p role="alert" className="break-words text-sm font-medium text-[var(--tg-theme-destructive-text-color)]">
              {t.photos.errors[error]}
            </p>
          )}
          {saved && !error && (
            <p role="status" className="text-xs text-[var(--tg-theme-hint-color)]">
              {t.photos.viewer.saved}
            </p>
          )}

          {archivedView ? (
            <div className="space-y-2">
              <button type="button" className={`${primaryButton} w-full`} disabled={disabled} onClick={() => void changeArchiveState('restored')}>
                <Ico>♻️</Ico>{t.photos.viewer.restore}
              </button>
              {trashView ? (
                purge ? (
                  <div role="alertdialog" aria-label={t.photos.viewer.purge_title} className="space-y-3 rounded-xl border border-red-300 p-3">
                    <p className="break-words text-sm font-semibold">{t.photos.viewer.purge_title}</p>
                    {purge.state === 'loading' || !purge.preview ? (
                      <p role="status" className="break-words text-sm text-[var(--tg-theme-hint-color)]">{t.photos.viewer.purge_loading}</p>
                    ) : (
                      <div className="space-y-2 break-words text-sm">
                        {purge.preview.deletes_files ? (
                          <p>{t.photos.viewer.purge_files.replace('{files}', String(purge.preview.files)).replace('{size}', formatSize(purge.preview.bytes))}</p>
                        ) : (
                          <p>{t.photos.viewer.purge_file_kept}</p>
                        )}
                        {purge.preview.annotations > 0 && (
                          <p>{t.photos.viewer.purge_markers.replace('{count}', String(purge.preview.annotations))}</p>
                        )}
                        {purge.preview.may_be_in_backups && <p className="text-[var(--tg-theme-hint-color)]">{t.photos.viewer.purge_backups}</p>}
                        <p className="text-[var(--tg-theme-hint-color)]">{t.photos.viewer.purge_telegram}</p>
                        {purge.preview.blockers.length > 0 ? (
                          <div role="alert" className="space-y-1 text-[var(--tg-theme-destructive-text-color)]">
                            <p className="font-semibold">{t.photos.viewer.purge_blocked_title}</p>
                            <ul className="list-disc pl-5">
                              {purge.preview.blockers.map((blocker) => (
                                <li key={blocker.protocol_id}>
                                  {(t.photos.viewer as Record<string, string>)[`purge_blocker_${blocker.kind}`] ?? blocker.kind}
                                </li>
                              ))}
                            </ul>
                            <p>{t.photos.viewer.purge_blocked_hint}</p>
                          </div>
                        ) : (
                          <p className="font-semibold">{t.photos.viewer.purge_irreversible}</p>
                        )}
                      </div>
                    )}
                    <div className="flex flex-col gap-2">
                      <button type="button" aria-label="photo-purge-cancel" className={`${primaryButton} w-full`} disabled={busy} onClick={() => setPurge(null)}>
                        <Ico>✖️</Ico>{t.photos.viewer.cancel}
                      </button>
                      <button
                        type="button"
                        aria-label="photo-purge-confirm"
                        className="min-h-11 w-full rounded-xl border border-red-600 bg-red-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
                        disabled={busy || purge.state !== 'ready' || !purge.preview?.can_purge}
                        onClick={() => void confirmPurge()}
                      >
                        <Ico>🗑️</Ico>{t.photos.viewer.purge_confirm}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <button type="button" aria-label="photo-untrash" className={`${secondaryButton} w-full`} disabled={disabled} onClick={() => void changeArchiveState('untrashed')}>
                      <Ico>🗃️</Ico>{t.photos.viewer.untrash}
                    </button>
                    <button type="button" aria-label="photo-purge" className="min-h-11 w-full rounded-xl border border-red-300 px-3 py-2 text-sm font-semibold text-red-700 disabled:opacity-50" disabled={disabled} onClick={() => void openPurge()}>
                      <Ico>🗑️</Ico>{t.photos.viewer.purge}
                    </button>
                  </>
                )
              ) : (
                <>
                  <button type="button" aria-label="photo-trash" className={`${secondaryButton} w-full`} disabled={disabled} onClick={() => void changeArchiveState('trashed')}>
                    <Ico>🗑️</Ico>{t.photos.viewer.trash}
                  </button>
                  <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">{t.photos.viewer.trash_note}</p>
                </>
              )}
            </div>
          ) : confirmArchive ? (
            <div role="alertdialog" aria-label={t.photos.viewer.archive_confirm} className="space-y-2 rounded-xl border border-[var(--tg-control-border-color)] p-3">
              <p className="break-words text-sm">{t.photos.viewer.archive_confirm}</p>
              <div className="flex flex-wrap gap-2">
                <button type="button" className={primaryButton} disabled={disabled} onClick={() => void changeArchiveState('archived')}>
                  <Ico>🗃️</Ico>{t.photos.viewer.archive}
                </button>
                <button type="button" className={secondaryButton} disabled={disabled} onClick={() => setConfirmArchive(false)}>
                  <Ico>✖️</Ico>{t.photos.viewer.cancel}
                </button>
              </div>
            </div>
          ) : (
            <button type="button" className={`${secondaryButton} w-full`} disabled={disabled} onClick={() => setConfirmArchive(true)}>
              <Ico>🗃️</Ico>{t.photos.viewer.archive}
            </button>
          )}
        </div>
      </div>
      {fullscreen && detail?.display_url && !imageFailed && (
        <PhotoFullscreen
          src={detail.display_url}
          alt={attachment.caption || t.photos.viewer.photo_alt}
          counter={t.photos.viewer.counter.replace('{current}', String(index + 1)).replace('{total}', String(items.length))}
          onClose={() => {
            // Back / close while drawing only leaves the drawing; the picture stays
            if (drawingMarker) {
              setDrawingMarkerId(null);
              setStrokeTooShort(false);
            } else {
              setFullscreen(false);
            }
          }}
          onImageError={onImageError}
          markers={markers}
          selectedMarkerId={drawingMarker ? drawingMarker.id : selectedMarkerId}
          onMarkerSelect={(marker) => setSelectedMarkerId(marker.id)}
          canPlaceMarkers={markersAllowed && !markersReadOnly && (markMode || !atMarkerLimit)}
          placing={placing}
          onPlacingChange={setMarkMode}
          onPlace={(x, y) => void placeMarker(x, y)}
          drawing={drawingMarker !== null}
          onStroke={onStroke}
          onCancelDrawing={() => {
            setDrawingMarkerId(null);
            setStrokeTooShort(false);
          }}
          notice={
            strokeTooShort ? t.photos.markers.outline_too_short : markerError && !selectedMarker ? t.photos.errors[markerError] : null
          }
        />
      )}
      {selectedMarker && (
        <PointMarkerPopup
          marker={selectedMarker}
          number={markers.indexOf(selectedMarker) + 1}
          readOnly={markersReadOnly}
          busy={markerBusy}
          error={markerError}
          onSaveLabel={(label) => void saveMarkerLabel(selectedMarker, label)}
          hasOutline={selectedMarker.outline !== null}
          onDrawOutline={() => startDrawing(selectedMarker)}
          onRemoveOutline={() => void saveOutline(selectedMarker, null)}
          onDelete={() => void deleteMarker(selectedMarker)}
          onClose={() => {
            setSelectedMarkerId(null);
            setMarkerError(null);
          }}
        />
      )}
    </div>
  );
}
