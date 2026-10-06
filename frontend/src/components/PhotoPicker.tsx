import { ChangeEvent, useRef } from 'react';
import { useI18n } from '../hooks/useI18n';
import { PhotoCaptureSource } from '../types/photo';
import { CameraIcon, GalleryIcon } from './PhotoIcons';

// Two buttons (D3): camera (`capture`) and gallery (multi-select), each with its own hidden input. The picked files
// are handed over as a plain array together with the declared source; checks and queueing belong to the queue.

export const PHOTO_ACCEPT = 'image/jpeg,image/png,image/webp';

// Some hosts ignore `capture` — Telegram on Android opens its gallery picker instead of the camera (found on a real
// phone in 14E.7) — so the camera button cannot promise a camera photo. The declared source therefore follows the
// file: a camera-button file counts as CAMERA only when it was modified within this window of "now" (a photo taken
// a moment ago); anything older is declared GALLERY. Still informational, never proof.
export const CAMERA_FRESH_WINDOW_MS = 5 * 60 * 1000;

export function looksFreshlyTaken(file: File, now: number = Date.now()): boolean {
  return file.lastModified > 0 && Math.abs(now - file.lastModified) <= CAMERA_FRESH_WINDOW_MS;
}

interface PhotoPickerProps {
  onFiles: (files: File[], source: PhotoCaptureSource) => void;
  disabled?: boolean;
}

export function PhotoPicker({ onFiles, disabled = false }: PhotoPickerProps) {
  const { t } = useI18n();
  const cameraRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);

  const handle = (source: PhotoCaptureSource) => (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = ''; // the same file can be picked again
    if (files.length === 0) return;
    const declared: PhotoCaptureSource =
      source === 'CAMERA' && !files.every((file) => looksFreshlyTaken(file)) ? 'GALLERY' : source;
    onFiles(files, declared);
  };

  const buttonBase =
    'flex min-h-11 w-full min-w-0 items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition disabled:opacity-50';

  return (
    <div className="grid grid-cols-1 gap-2 min-[360px]:grid-cols-2">
      <button
        type="button"
        disabled={disabled}
        onClick={() => cameraRef.current?.click()}
        className={`${buttonBase} bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]`}
      >
        <CameraIcon />
        <span className="min-w-0 break-words">{t.photos.picker.take_photo}</span>
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => galleryRef.current?.click()}
        className={`${buttonBase} border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]`}
      >
        <GalleryIcon />
        <span className="min-w-0 break-words">{t.photos.picker.from_gallery}</span>
      </button>
      <input
        ref={cameraRef}
        type="file"
        accept={PHOTO_ACCEPT}
        capture="environment"
        className="hidden"
        tabIndex={-1}
        data-testid="photo-input-camera"
        onChange={handle('CAMERA')}
      />
      <input
        ref={galleryRef}
        type="file"
        accept={PHOTO_ACCEPT}
        multiple
        className="hidden"
        tabIndex={-1}
        data-testid="photo-input-gallery"
        onChange={handle('GALLERY')}
      />
    </div>
  );
}
