import { useCallback, useEffect, useRef, useState } from 'react';
import {
  archivePhotoAttachment,
  fetchPhoto,
  patchPhotoAttachment,
  restorePhotoAttachment,
} from '../api/photos';
import { usePhotoBackRegistration } from '../hooks/PhotoBackContext';
import { useI18n } from '../hooks/useI18n';
import {
  PHOTO_CATEGORIES,
  PhotoAttachmentPatch,
  PhotoAttachmentRead,
  PhotoCategory,
  PhotoDetailResponse,
  PhotoListItem,
} from '../types/photo';
import { formatCapturedAt, formatUploadedAt, isCapturedMuchOlderThanUpload } from '../utils/photoCaption';
import { PhotoErrorKey, classifyPhotoError } from '../utils/photoErrors';
import { hapticNotify } from '../utils/telegramHaptics';
import { ChevronLeftIcon, ChevronRightIcon, CloseIcon } from './PhotoIcons';

// Full-screen sheet (contract §7). Loads the detail for the DISPLAY image (lists carry thumbnails only), edits the
// metadata of THIS attachment (caption / category / report flag), archives or restores it in this context.
// No download, no share, no delete, no original. Closing is guarded: an unsaved caption is saved first.

export const CAPTION_MAX_LENGTH = 1000;
/** Signed links are refetched this long before they expire (contract §7c). */
const URL_REFRESH_MARGIN_MS = 30_000;

interface PhotoViewerProps {
  projectId: string;
  items: readonly PhotoListItem[];
  index: number;
  archivedView: boolean;
  captionFor: (item: PhotoListItem) => string;
  onIndexChange: (index: number) => void;
  onClose: () => void;
  onAttachmentUpdated: (attachment: PhotoAttachmentRead) => void;
  onAttachmentRemoved: (attachment: PhotoAttachmentRead, action: 'archived' | 'restored') => void;
  /** The photo vanished meanwhile: the host should refetch its list. */
  onRefresh?: () => void;
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
  captionFor,
  onIndexChange,
  onClose,
  onAttachmentUpdated,
  onAttachmentRemoved,
  onRefresh,
}: PhotoViewerProps) {
  const { t } = useI18n();
  const item = items[index];
  const attachment = item?.attachment;
  const assetId = item?.asset.id;

  const cache = useRef(new Map<string, CachedDetail>());
  const imageRetried = useRef(new Set<string>());
  const closeButton = useRef<HTMLButtonElement>(null);

  const [detail, setDetail] = useState<PhotoDetailResponse | null>(null);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadError, setLoadError] = useState<PhotoErrorKey | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  const [caption, setCaption] = useState(attachment?.caption ?? '');
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [error, setError] = useState<PhotoErrorKey | null>(null);
  const [saved, setSaved] = useState(false);

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
    setError(null);
    setSaved(false);
  }, [attachment?.id]);

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
      if (event.key === 'Escape') void requestClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [requestClose]);

  if (!item || !attachment) return null;
  const currentAssetId = item.asset.id;

  const changeArchiveState = async (action: 'archived' | 'restored') => {
    setBusy(true);
    setError(null);
    try {
      const updated =
        action === 'archived'
          ? await archivePhotoAttachment(projectId, attachment.id)
          : await restorePhotoAttachment(projectId, attachment.id);
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
  const disabled = busy || saving;

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
            <img
              src={detail.display_url}
              alt={attachment.caption || t.photos.viewer.photo_alt}
              referrerPolicy="no-referrer"
              onError={onImageError}
              className="max-h-full max-w-full object-contain"
            />
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
                {t.photos.viewer.retry}
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
                {t.photos.viewer.save}
              </button>
              <button
                type="button"
                className={secondaryButton}
                disabled={disabled}
                onClick={() => setCaption(attachment.caption ?? '')}
              >
                {t.photos.viewer.cancel}
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
            <button type="button" className={`${primaryButton} w-full`} disabled={disabled} onClick={() => void changeArchiveState('restored')}>
              {t.photos.viewer.restore}
            </button>
          ) : confirmArchive ? (
            <div role="alertdialog" aria-label={t.photos.viewer.archive_confirm} className="space-y-2 rounded-xl border border-[var(--tg-control-border-color)] p-3">
              <p className="break-words text-sm">{t.photos.viewer.archive_confirm}</p>
              <div className="flex flex-wrap gap-2">
                <button type="button" className={primaryButton} disabled={disabled} onClick={() => void changeArchiveState('archived')}>
                  {t.photos.viewer.archive}
                </button>
                <button type="button" className={secondaryButton} disabled={disabled} onClick={() => setConfirmArchive(false)}>
                  {t.photos.viewer.cancel}
                </button>
              </div>
            </div>
          ) : (
            <button type="button" className={`${secondaryButton} w-full`} disabled={disabled} onClick={() => setConfirmArchive(true)}>
              {t.photos.viewer.archive}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
