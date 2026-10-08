import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { usePhotoBackRegistration } from '../hooks/PhotoBackContext';
import { useI18n } from '../hooks/useI18n';
import { MAX_MARKER_LABEL_LENGTH, PhotoAnnotationRead } from '../types/photo';
import { PhotoErrorKey } from '../utils/photoErrors';

// The window a tap on a marker opens (owner decision 2026-10-08: the label is shown in a pop-up): the label, edited in
// place, and the way to delete the marker. A bottom sheet, so it never hides the marker's neighbourhood on a phone and
// its controls are within a thumb's reach. A marker of an archived photo is only shown (no input, no delete).
// Rendered in a portal above the full-screen picture; Telegram's BackButton closes it first.

interface PointMarkerPopupProps {
  marker: PhotoAnnotationRead;
  number: number;
  readOnly: boolean;
  busy: boolean;
  error: PhotoErrorKey | null;
  onSaveLabel: (label: string | null) => void;
  /** The marker has a contour around the defect (Stage 14G.5). */
  hasOutline: boolean;
  onDrawOutline: () => void;
  onRemoveOutline: () => void;
  onDelete: () => void;
  onClose: () => void;
}

export function PointMarkerPopup({
  marker,
  number,
  readOnly,
  busy,
  error,
  onSaveLabel,
  hasOutline,
  onDrawOutline,
  onRemoveOutline,
  onDelete,
  onClose,
}: PointMarkerPopupProps) {
  const { t } = useI18n();
  const [label, setLabel] = useState(marker.label ?? '');
  const closeButton = useRef<HTMLButtonElement>(null);
  usePhotoBackRegistration(true, onClose);

  useEffect(() => {
    setLabel(marker.label ?? '');
  }, [marker.id, marker.label]);
  useEffect(() => {
    closeButton.current?.focus();
  }, []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopImmediatePropagation(); // the viewer under the pop-up must not close as well
        onClose();
      }
    };
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [onClose]);

  const trimmed = label.trim();
  const dirty = trimmed !== (marker.label ?? '');
  const title = t.photos.markers.popup_title.replace('{number}', String(number));

  return createPortal(
    <div className="fixed inset-0 z-[70] flex flex-col justify-end bg-black/40" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
        className="max-h-[80vh] space-y-3 overflow-y-auto rounded-t-2xl bg-[var(--tg-theme-bg-color)] p-4 text-[var(--tg-theme-text-color)]"
        style={{ paddingBottom: 'max(1rem, env(safe-area-inset-bottom))' }}
      >
        <h3 className="break-words text-base font-semibold">{title}</h3>
        {readOnly ? (
          <p data-testid="marker-label-text" className="break-words text-sm">
            {marker.label ?? t.photos.markers.popup_no_label}
          </p>
        ) : (
          <div className="space-y-1">
            <label className="block space-y-1">
              <span className="text-xs font-medium text-[var(--tg-theme-hint-color)]">{t.photos.markers.popup_label}</span>
              <input
                type="text"
                value={label}
                maxLength={MAX_MARKER_LABEL_LENGTH}
                disabled={busy}
                placeholder={t.photos.markers.popup_placeholder}
                onChange={(event) => setLabel(event.target.value)}
                className="min-h-11 w-full rounded-xl border px-3 py-2 text-base"
              />
            </label>
            <span className="block text-right text-xs text-[var(--tg-theme-hint-color)]">
              {t.photos.markers.popup_counter
                .replace('{count}', String(label.length))
                .replace('{max}', String(MAX_MARKER_LABEL_LENGTH))}
            </span>
          </div>
        )}
        {error && (
          <p role="alert" className="break-words text-sm font-medium text-[var(--tg-theme-destructive-text-color)]">
            {t.photos.errors[error]}
          </p>
        )}
        <div className="flex flex-col gap-2">
          {!readOnly && (
            <>
              <button
                type="button"
                disabled={busy || !dirty}
                onClick={() => onSaveLabel(trimmed === '' ? null : trimmed)}
                className="min-h-11 w-full rounded-xl bg-[var(--tg-theme-button-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-button-text-color)] disabled:opacity-50"
              >
                {t.photos.markers.popup_save}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={onDrawOutline}
                className="min-h-11 w-full rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color)] disabled:opacity-50"
              >
                {hasOutline ? t.photos.markers.outline_redraw : t.photos.markers.outline_draw}
              </button>
              {hasOutline && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={onRemoveOutline}
                  className="min-h-11 w-full rounded-xl border border-[var(--tg-control-border-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] disabled:opacity-50"
                >
                  {t.photos.markers.outline_remove}
                </button>
              )}
              <button
                type="button"
                disabled={busy}
                onClick={onDelete}
                className="min-h-11 w-full rounded-xl border border-[var(--tg-control-border-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] disabled:opacity-50"
              >
                {t.photos.markers.popup_delete}
              </button>
            </>
          )}
          <button
            ref={closeButton}
            type="button"
            disabled={busy}
            onClick={onClose}
            className="min-h-11 w-full rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color)] disabled:opacity-50"
          >
            {t.photos.markers.popup_close}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
