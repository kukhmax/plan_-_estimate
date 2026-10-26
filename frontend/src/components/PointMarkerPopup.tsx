import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { usePhotoBackRegistration } from '../hooks/PhotoBackContext';
import { useI18n } from '../hooks/useI18n';
import { MAX_MARKER_LABEL_LENGTH, PhotoAnnotationRead } from '../types/photo';
import { PhotoErrorKey } from '../utils/photoErrors';
import { cmText, isPhotoUtility, parseDistance, PHOTO_UTILITIES, UTILITY_COLORS } from '../utils/photoUtilities';
import { Ico } from './Ico';

// The window a tap on a marker opens (owner decision 2026-10-08: the label is shown in a pop-up): the label, edited in
// place, and the way to delete the marker. A bottom sheet, so it never hides the marker's neighbourhood on a phone and
// its controls are within a thumb's reach. A marker of an archived photo is only shown (no input, no delete).
// Rendered in a portal above the full-screen picture; Telegram's BackButton closes it first.

export interface MarkerChanges {
  label?: string | null;
  utility?: string | null;
  depth_cm?: number | null;
  from_floor_cm?: number | null;
  from_corner_cm?: number | null;
}

const DISTANCES = [
  ['depth_cm', 'popup_depth'],
  ['from_floor_cm', 'popup_from_floor'],
  ['from_corner_cm', 'popup_from_corner'],
] as const;

interface PointMarkerPopupProps {
  marker: PhotoAnnotationRead;
  number: number;
  readOnly: boolean;
  busy: boolean;
  error: PhotoErrorKey | null;
  /** Only the fields that changed (the label, the type of the utility, the distances in cm). */
  onSave: (changes: MarkerChanges) => void;
  /** The marker has a contour around the defect (Stage 14G.5). */
  hasOutline: boolean;
  onDrawOutline: () => void;
  onRemoveOutline: () => void;
  onDelete: () => void;
  onClose: () => void;
}

const chipClass = 'flex min-h-11 items-center gap-2 rounded-xl border px-3 py-2 text-sm text-[var(--tg-theme-text-color)] disabled:opacity-50';

export function PointMarkerPopup({
  marker,
  number,
  readOnly,
  busy,
  error,
  onSave,
  hasOutline,
  onDrawOutline,
  onRemoveOutline,
  onDelete,
  onClose,
}: PointMarkerPopupProps) {
  const { t } = useI18n();
  const [label, setLabel] = useState(marker.label ?? '');
  const [utility, setUtility] = useState<string | null>(marker.utility ?? null);
  const startText = (value: number | null | undefined) => (value === null || value === undefined ? '' : cmText(value));
  const [distances, setDistances] = useState<Record<(typeof DISTANCES)[number][0], string>>({
    depth_cm: startText(marker.depth_cm),
    from_floor_cm: startText(marker.from_floor_cm),
    from_corner_cm: startText(marker.from_corner_cm),
  });
  const closeButton = useRef<HTMLButtonElement>(null);
  usePhotoBackRegistration(true, onClose);

  useEffect(() => {
    setLabel(marker.label ?? '');
    setUtility(marker.utility ?? null);
    setDistances({ depth_cm: startText(marker.depth_cm), from_floor_cm: startText(marker.from_floor_cm), from_corner_cm: startText(marker.from_corner_cm) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marker.id, marker.label, marker.utility, marker.depth_cm, marker.from_floor_cm, marker.from_corner_cm]);
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
  // what differs from the stored marker: only that is sent; a distance that is not a number from 0 to 1000 blocks saving
  const changes: MarkerChanges = {};
  if (trimmed !== (marker.label ?? '')) changes.label = trimmed === '' ? null : trimmed;
  if (utility !== (marker.utility ?? null)) changes.utility = utility;
  const invalid: string[] = [];
  for (const [field] of DISTANCES) {
    const parsed = parseDistance(distances[field]);
    if (parsed === undefined) invalid.push(field);
    else if (parsed !== (marker[field] ?? null)) changes[field] = parsed;
  }
  const dirty = Object.keys(changes).length > 0;
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
          <div className="space-y-1">
            <p data-testid="marker-label-text" className="break-words text-sm">
              {marker.label ?? t.photos.markers.popup_no_label}
            </p>
            {isPhotoUtility(marker.utility) && (
              <p data-testid="marker-utility-text" className="break-words text-sm font-semibold" style={{ color: UTILITY_COLORS[marker.utility] }}>
                {t.photos.markers.utility[marker.utility]}
              </p>
            )}
            {DISTANCES.map(([field, key]) =>
              marker[field] === null || marker[field] === undefined ? null : (
                <p key={field} className="break-words text-sm">
                  {t.photos.markers[key]}: {cmText(marker[field] as number)}
                </p>
              ),
            )}
          </div>
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
            <div role="radiogroup" aria-label={t.photos.markers.utility_label} className="space-y-1 pt-2">
              <span className="block text-xs font-medium text-[var(--tg-theme-hint-color)]">{t.photos.markers.utility_label}</span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  role="radio"
                  aria-checked={utility === null}
                  aria-label="marker-utility-none"
                  disabled={busy}
                  onClick={() => setUtility(null)}
                  className={`${chipClass} ${utility === null ? 'border-[var(--tg-theme-button-color)] font-semibold' : 'border-[var(--tg-control-border-color)]'}`}
                >
                  <span className="min-w-0 break-words text-left">{t.photos.markers.utility_none}</span>
                </button>
                {PHOTO_UTILITIES.map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    role="radio"
                    aria-checked={utility === kind}
                    aria-label={`marker-utility-${kind}`}
                    disabled={busy}
                    onClick={() => setUtility(kind)}
                    className={`${chipClass} ${utility === kind ? 'font-semibold' : 'border-[var(--tg-control-border-color)]'}`}
                    style={utility === kind ? { borderColor: UTILITY_COLORS[kind] } : undefined}
                  >
                    <span aria-hidden="true" className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: UTILITY_COLORS[kind] }} />
                    <span className="min-w-0 break-words text-left">{t.photos.markers.utility[kind]}</span>
                  </button>
                ))}
              </div>
            </div>
            {utility !== null && (
              <div className="space-y-2 pt-2">
                {DISTANCES.map(([field, key]) => (
                  <label key={field} className="block space-y-1">
                    <span className="text-xs font-medium text-[var(--tg-theme-hint-color)]">{t.photos.markers[key]}</span>
                    <input
                      type="text"
                      inputMode="decimal"
                      aria-label={`marker-${field}`}
                      value={distances[field]}
                      disabled={busy}
                      onChange={(event) => setDistances({ ...distances, [field]: event.target.value })}
                      className="min-h-11 w-full rounded-xl border px-3 py-2 text-base"
                    />
                    {invalid.includes(field) && (
                      <span role="alert" className="block break-words text-xs text-[var(--tg-theme-destructive-text-color)]">
                        {t.photos.markers.distance_error}
                      </span>
                    )}
                  </label>
                ))}
              </div>
            )}
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
                disabled={busy || !dirty || invalid.length > 0}
                onClick={() => onSave(changes)}
                className="min-h-11 w-full rounded-xl bg-[var(--tg-theme-button-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-button-text-color)] disabled:opacity-50"
              >
                <Ico>💾</Ico>{t.photos.markers.popup_save}
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
                  <Ico>🗑️</Ico>{t.photos.markers.outline_remove}
                </button>
              )}
              <button
                type="button"
                disabled={busy}
                onClick={onDelete}
                className="min-h-11 w-full rounded-xl border border-[var(--tg-control-border-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] disabled:opacity-50"
              >
                <Ico>🗑️</Ico>{t.photos.markers.popup_delete}
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
            <Ico>✖️</Ico>{t.photos.markers.popup_close}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
