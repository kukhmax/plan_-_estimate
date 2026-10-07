import { ChangeEvent, useRef, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { PhotoCaptureSource } from '../types/photo';
import { CameraFailure, inAppCameraSupported } from '../utils/inAppCamera';
import { readExifCaptureTime } from '../utils/jpegExif';
import { CameraCapture } from './CameraCapture';
import { CameraIcon, GalleryIcon } from './PhotoIcons';

// Two buttons (D3): camera (`capture`) and gallery (multi-select), each with its own hidden input. The picked files
// are handed over as a plain array together with the declared source; checks and queueing belong to the queue.

export const PHOTO_ACCEPT = 'image/jpeg,image/png,image/webp';

// Some hosts ignore `capture` — Telegram on Android opens its gallery picker instead of the camera (found on a real
// phone in 14E.7) and hands over a COPY of the picked file, so neither the button nor the file's modification time
// says anything about where the photo came from. The declared source therefore follows the photo itself: a
// camera-button file counts as CAMERA only when its EXIF capture time (written by the camera, read here as device-local
// time) is within this window of "now"; anything older, or without EXIF (screenshots, downloads), is declared GALLERY.
// Still informational, never proof.
export const CAMERA_FRESH_WINDOW_MS = 5 * 60 * 1000;

export function isFreshCapture(captured: Date | null, now: number = Date.now()): boolean {
  return captured !== null && Math.abs(now - captured.getTime()) <= CAMERA_FRESH_WINDOW_MS;
}

async function declaredCameraSource(files: File[]): Promise<PhotoCaptureSource> {
  for (const file of files) {
    if (!isFreshCapture(await readExifCaptureTime(file))) return 'GALLERY';
  }
  return 'CAMERA';
}

// Once the phone refuses the camera (permission denied), the camera button goes straight to the phone's own picker for the
// rest of the session instead of showing the failure on every tap.
let inAppCameraRefused = false;
export function resetInAppCameraRefusal(): void {
  inAppCameraRefused = false;
}

interface PhotoPickerProps {
  onFiles: (files: File[], source: PhotoCaptureSource) => void;
  disabled?: boolean;
}

export function PhotoPicker({ onFiles, disabled = false }: PhotoPickerProps) {
  const { t } = useI18n();
  const cameraRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);
  const [cameraOpen, setCameraOpen] = useState(false);

  const handle = (source: PhotoCaptureSource) => async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = ''; // the same file can be picked again (reset before anything is awaited)
    if (files.length === 0) return;
    onFiles(files, source === 'CAMERA' ? await declaredCameraSource(files) : source);
  };

  const buttonBase =
    'flex min-h-11 w-full min-w-0 items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition disabled:opacity-50';

  return (
    <div className="grid grid-cols-1 gap-2 min-[360px]:grid-cols-2">
      <button
        type="button"
        disabled={disabled}
        onClick={() => (inAppCameraSupported() && !inAppCameraRefused ? setCameraOpen(true) : cameraRef.current?.click())}
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
      {cameraOpen && (
        <CameraCapture
          onDone={(files) => {
            setCameraOpen(false);
            onFiles(files, 'CAMERA'); // taken by the app itself: no guessing from the file
          }}
          onCancel={() => setCameraOpen(false)}
          onUseNativePicker={() => {
            setCameraOpen(false);
            cameraRef.current?.click(); // runs inside the user's tap, so the browser allows the picker
          }}
          onCameraFailed={(failure: CameraFailure) => {
            if (failure === 'denied') inAppCameraRefused = true;
          }}
        />
      )}
    </div>
  );
}
