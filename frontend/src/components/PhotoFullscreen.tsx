import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { usePhotoBackRegistration } from '../hooks/PhotoBackContext';
import { useI18n } from '../hooks/useI18n';
import { PhotoAnnotationRead } from '../types/photo';
import { OutlinePoint } from '../utils/outline';
import { CloseIcon, PinIcon } from './PhotoIcons';
import { ZoomableImage } from './ZoomableImage';

// The photo on the whole screen, for looking at small details (the customer is shown defects here): pinch to zoom, drag to
// move, double tap to close in. Telegram's BackButton closes it first (before the viewer under it).

interface PhotoFullscreenProps {
  src: string;
  alt: string;
  counter: string;
  onClose: () => void;
  onImageError: () => void;
  /** Point markers of this photo (Stage 14G), drawn over the picture so they follow its zoom. */
  markers?: readonly PhotoAnnotationRead[];
  selectedMarkerId?: string | null;
  onMarkerSelect?: (marker: PhotoAnnotationRead) => void;
  /** Markers can be placed here (an active photo with room left): shows the "add marker" switch. */
  canPlaceMarkers?: boolean;
  placing?: boolean;
  onPlacingChange?: (placing: boolean) => void;
  onPlace?: (x: number, y: number) => void;
  /** Contour drawing (Stage 14G.5): a finger draws a line around a defect; the finished stroke goes to `onStroke`. */
  drawing?: boolean;
  onStroke?: (points: OutlinePoint[]) => void;
  onCancelDrawing?: () => void;
  /** A message under the picture (a refused contour, a failed save). */
  notice?: string | null;
}

export function PhotoFullscreen({
  src,
  alt,
  counter,
  onClose,
  onImageError,
  markers = [],
  selectedMarkerId = null,
  onMarkerSelect,
  canPlaceMarkers = false,
  placing = false,
  onPlacingChange,
  onPlace,
  drawing = false,
  onStroke,
  onCancelDrawing,
  notice = null,
}: PhotoFullscreenProps) {
  const { t } = useI18n();
  const closeButton = useRef<HTMLButtonElement>(null);
  const [hintVisible, setHintVisible] = useState(true);
  usePhotoBackRegistration(true, onClose);

  useEffect(() => {
    closeButton.current?.focus();
  }, []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.photos.viewer.fullscreen_label}
      className="fixed inset-0 z-[60] flex flex-col bg-black text-white"
      style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="flex shrink-0 items-center justify-between gap-2 px-3 py-2">
        <span className="shrink-0 whitespace-nowrap rounded-full bg-white/15 px-3 py-1.5 text-xs font-semibold">{counter}</span>
        <div className="flex min-w-0 items-center gap-2">
          {drawing && onCancelDrawing && (
            <button
              type="button"
              onClick={onCancelDrawing}
              className="flex min-h-11 min-w-0 items-center rounded-full bg-white px-4 text-xs font-semibold text-black"
            >
              <span className="min-w-0 break-words">{t.photos.markers.outline_cancel}</span>
            </button>
          )}
          {!drawing && canPlaceMarkers && onPlacingChange && (
            <button
              type="button"
              aria-pressed={placing}
              onClick={() => onPlacingChange(!placing)}
              className={`flex min-h-11 min-w-0 items-center gap-1.5 rounded-full px-3 text-xs font-semibold ${
                placing ? 'bg-white text-black' : 'bg-white/15 text-white'
              }`}
            >
              <PinIcon size={16} />
              <span className="min-w-0 break-words text-left leading-tight">
                {placing ? t.photos.markers.add_done : t.photos.markers.add}
              </span>
            </button>
          )}
          <button
            ref={closeButton}
            type="button"
            aria-label={t.photos.viewer.fullscreen_close}
            onClick={onClose}
            className="flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full bg-white/15"
          >
            <CloseIcon />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <ZoomableImage
          src={src}
          alt={alt}
          onError={onImageError}
          onInteract={() => setHintVisible(false)}
          markers={markers}
          selectedMarkerId={selectedMarkerId}
          onMarkerSelect={onMarkerSelect}
          placing={placing}
          onPlace={onPlace}
          drawing={drawing}
          onStroke={onStroke}
        />
      </div>
      {notice && (
        <p role="alert" className="shrink-0 break-words px-4 pt-2 text-center text-sm font-medium text-white">
          {notice}
        </p>
      )}
      {drawing ? (
        <p className="shrink-0 break-words px-4 py-2 text-center text-xs text-white/80">{t.photos.markers.outline_hint}</p>
      ) : placing ? (
        <p className="shrink-0 break-words px-4 py-2 text-center text-xs text-white/80">{t.photos.markers.fullscreen_hint_add}</p>
      ) : (
        hintVisible && <p className="shrink-0 break-words px-4 py-2 text-center text-xs text-white/70">{t.photos.viewer.fullscreen_hint}</p>
      )}
    </div>,
    document.body,
  );
}
