import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { usePhotoBackRegistration } from '../hooks/PhotoBackContext';
import { useI18n } from '../hooks/useI18n';
import { CloseIcon } from './PhotoIcons';
import { ZoomableImage } from './ZoomableImage';

// The photo on the whole screen, for looking at small details (the customer is shown defects here): pinch to zoom, drag to
// move, double tap to close in. Telegram's BackButton closes it first (before the viewer under it).

interface PhotoFullscreenProps {
  src: string;
  alt: string;
  counter: string;
  onClose: () => void;
  onImageError: () => void;
}

export function PhotoFullscreen({ src, alt, counter, onClose, onImageError }: PhotoFullscreenProps) {
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
        <span className="rounded-full bg-white/15 px-3 py-1.5 text-xs font-semibold">{counter}</span>
        <button
          ref={closeButton}
          type="button"
          aria-label={t.photos.viewer.fullscreen_close}
          onClick={onClose}
          className="flex min-h-11 min-w-11 items-center justify-center rounded-full bg-white/15"
        >
          <CloseIcon />
        </button>
      </div>
      <div className="min-h-0 flex-1">
        <ZoomableImage src={src} alt={alt} onError={onImageError} onInteract={() => setHintVisible(false)} />
      </div>
      {hintVisible && <p className="shrink-0 break-words px-4 py-2 text-center text-xs text-white/70">{t.photos.viewer.fullscreen_hint}</p>}
    </div>,
    document.body,
  );
}
