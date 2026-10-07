// The in-app camera (Stage 14E.10): getUserMedia for the viewfinder and ImageCapture.takePhoto for the still.
// Found on the owner's phone (14E.9): Telegram on Android ignores `capture`, but gives a page the camera; takePhoto returns
// a full-size JPEG with EXIF in ~1 s, while a canvas frame took 14 s and carries no EXIF — so there is no canvas path.

export interface CameraSession {
  stream: MediaStream;
  track: MediaStreamTrack;
  capture: ImageCaptureLike;
  /** The largest still the camera offers, when it says so; otherwise the host's default size is used. */
  stillSize: { width: number; height: number } | null;
  hasTorch: boolean;
}

export interface ImageCaptureLike {
  takePhoto: (settings?: { imageWidth?: number; imageHeight?: number }) => Promise<Blob>;
  getPhotoCapabilities?: () => Promise<{ imageWidth?: { max?: number }; imageHeight?: { max?: number } }>;
}
type ImageCaptureCtor = new (track: MediaStreamTrack) => ImageCaptureLike;

const imageCaptureCtor = (win: unknown): ImageCaptureCtor | undefined =>
  (win as { ImageCapture?: ImageCaptureCtor }).ImageCapture;

/** The preview does not need the sensor's full size (a big preview only slows the start); the still is asked for separately. */
export const PREVIEW_CONSTRAINTS: MediaStreamConstraints = {
  audio: false,
  video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1440 } },
};

/**
 * Whether this host can run the viewfinder: a secure page with getUserMedia AND ImageCapture. iOS WebViews have no
 * ImageCapture, so they keep the native `capture` file input, which works there.
 */
export function inAppCameraSupported(win: Window & typeof globalThis = window): boolean {
  return (
    win.isSecureContext === true &&
    typeof win.navigator.mediaDevices?.getUserMedia === 'function' &&
    imageCaptureCtor(win) !== undefined
  );
}

/** Why the camera could not start, in terms the screen can act on. */
export type CameraFailure = 'denied' | 'unavailable' | 'busy' | 'unsupported' | 'unknown';

export function classifyCameraError(error: unknown): CameraFailure {
  const name = error && typeof error === 'object' ? String((error as { name?: unknown }).name ?? '') : '';
  if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') return 'denied';
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError' || name === 'OverconstrainedError') return 'unavailable';
  if (name === 'NotReadableError' || name === 'TrackStartError' || name === 'AbortError') return 'busy';
  if (name === 'TypeError' || name === 'NotSupportedError') return 'unsupported';
  return 'unknown';
}

export async function openCamera(win: Window & typeof globalThis = window): Promise<CameraSession> {
  const Ctor = imageCaptureCtor(win);
  if (!Ctor || !win.navigator.mediaDevices?.getUserMedia) throw new DOMException('camera API is not available', 'NotSupportedError');
  const stream = await win.navigator.mediaDevices.getUserMedia(PREVIEW_CONSTRAINTS);
  const track = stream.getVideoTracks()[0];
  if (!track) {
    stream.getTracks().forEach((t) => t.stop());
    throw new DOMException('the stream has no video track', 'NotFoundError');
  }
  const capture = new Ctor(track);
  let stillSize: CameraSession['stillSize'] = null;
  try {
    const photo = await capture.getPhotoCapabilities?.();
    const width = photo?.imageWidth?.max;
    const height = photo?.imageHeight?.max;
    if (width && height) stillSize = { width, height };
  } catch {
    // the host does not report photo capabilities: the default still size is used (the shot itself still works)
    stillSize = null;
  }
  const capabilities = (track.getCapabilities?.() ?? {}) as Record<string, unknown>;
  return { stream, track, capture, stillSize, hasTorch: 'torch' in capabilities };
}

export function closeCamera(session: CameraSession | null): void {
  session?.stream.getTracks().forEach((track) => track.stop());
}

export async function setTorch(session: CameraSession, on: boolean): Promise<void> {
  await session.track.applyConstraints({ advanced: [{ torch: on } as MediaTrackConstraintSet] });
}

const pad = (n: number, width = 2) => String(n).padStart(width, '0');

export function stillFileName(now: Date, index: number): string {
  return `kamera-${pad(now.getFullYear(), 4)}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}-${index}.jpg`;
}

/**
 * One still at the camera's largest size (asked for explicitly: the default followed the preview and gave a 1:1 crop on
 * the owner's phone). If the host refuses the explicit size, one more try with its defaults; then the error is the caller's.
 */
export async function takeStill(session: CameraSession, index: number, now: Date = new Date()): Promise<File> {
  let blob: Blob;
  if (session.stillSize) {
    try {
      blob = await session.capture.takePhoto({ imageWidth: session.stillSize.width, imageHeight: session.stillSize.height });
    } catch {
      blob = await session.capture.takePhoto();
    }
  } else {
    blob = await session.capture.takePhoto();
  }
  if (blob.size === 0) throw new DOMException('the camera returned an empty photo', 'OperationError');
  return new File([blob], stillFileName(now, index), { type: blob.type || 'image/jpeg', lastModified: now.getTime() });
}
