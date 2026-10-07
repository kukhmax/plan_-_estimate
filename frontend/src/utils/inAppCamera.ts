// The in-app camera (Stage 14E.10): getUserMedia for the viewfinder and ImageCapture.takePhoto for the still.
// Found on the owner's phone (14E.9): Telegram on Android ignores `capture`, but gives a page the camera; takePhoto returns
// a full-size JPEG with EXIF in ~1 s, while a canvas frame took 14 s and carries no EXIF — so there is no canvas path.
// Found on the same phone (size test): takePhoto picks the *nearest* size the host lists, and that list has no big 4:3 size
// (4624x3472 / 4000x3000 come back as a 3472x3472 square, 3264x2448 as 16:9, only 1920x1440 is a true 4:3). So the still is
// searched for the largest size that really comes back 4:3, and that size is remembered. There is no hardware zoom either
// (no capabilities.zoom even when asked), so zoom is digital: the 4:3 still is cropped around its centre.
import { copyExifUpright, readJpegSize } from './jpegMeta';

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

const FOUR_BY_THREE = 4 / 3;
const FOUR_BY_THREE_TOLERANCE = 0.03; // 4624x3472 (sensor) is 1.332

export const isFourByThree = (size: { width: number; height: number }): boolean => {
  const long = Math.max(size.width, size.height);
  const short = Math.min(size.width, size.height);
  return short > 0 && Math.abs(long / short - FOUR_BY_THREE) <= FOUR_BY_THREE_TOLERANCE;
};

/** Standard 4:3 still sizes, largest first; the host answers with the nearest size it lists, so any 4:3 neighbour will do. */
export const STILL_LADDER: ReadonlyArray<{ width: number; height: number }> = [
  { width: 4000, height: 3000 },
  { width: 3264, height: 2448 },
  { width: 2592, height: 1944 },
  { width: 2048, height: 1536 },
  { width: 1920, height: 1440 },
  { width: 1280, height: 960 },
];

type StillRequest = { imageWidth: number; imageHeight: number } | undefined;

/** The sizes to try, in order: the camera's own maximum (when known), then the ladder below it; no size at all when nothing is known. */
export function stillRequests(session: Pick<CameraSession, 'stillSize'>): StillRequest[] {
  const max = session.stillSize;
  const requests: StillRequest[] = [];
  if (max) requests.push({ imageWidth: max.width, imageHeight: max.height });
  else requests.push(undefined);
  for (const size of STILL_LADDER) {
    if (max && (size.width > max.width || size.height > max.height)) continue;
    if (max && size.width === max.width && size.height === max.height) continue;
    requests.push({ imageWidth: size.width, imageHeight: size.height });
  }
  return requests;
}

const STILL_SIZE_KEY = 'plan-estimate:camera-still-size:v1';
let noFourByThree = false; // this session: the camera has no 4:3 still at all, so the search is not repeated for every shot

/** Forgets what was learned about the camera (tests, and the owner's "try again" after a phone or Telegram update). */
export function resetStillSizeMemory(): void {
  noFourByThree = false;
  try {
    localStorage.removeItem(STILL_SIZE_KEY);
  } catch {
    // storage unavailable: nothing was remembered either
  }
}

function rememberedRequest(): StillRequest {
  try {
    const parsed = JSON.parse(localStorage.getItem(STILL_SIZE_KEY) ?? 'null') as { width?: unknown; height?: unknown } | null;
    if (parsed && Number.isInteger(parsed.width) && Number.isInteger(parsed.height)) {
      return { imageWidth: parsed.width as number, imageHeight: parsed.height as number };
    }
  } catch {
    // corrupt or unavailable storage: the search runs again
  }
  return undefined;
}

function rememberRequest(request: StillRequest): void {
  try {
    if (request) localStorage.setItem(STILL_SIZE_KEY, JSON.stringify({ width: request.imageWidth, height: request.imageHeight }));
  } catch {
    // storage unavailable: the size is searched again next time
  }
}

function forgetRequest(): void {
  try {
    localStorage.removeItem(STILL_SIZE_KEY);
  } catch {
    // nothing to forget
  }
}

/** Whether the photo is a 4:3 frame; null when its size cannot be read (then it is trusted, there is nothing to compare). */
async function fourByThreeOrUnknown(blob: Blob): Promise<boolean | null> {
  const size = await readJpegSize(blob).catch(() => null);
  return size ? isFourByThree(size) : null;
}

/**
 * One 4:3 still: the remembered size first; otherwise the largest size of the ladder that comes back 4:3 (non-4:3 answers are
 * dropped). If the camera has no 4:3 still at all, its first (largest) answer is kept. Errors of one size move on to the next.
 */
async function takeFourByThree(session: CameraSession): Promise<Blob> {
  const photo = (request: StillRequest) => (request ? session.capture.takePhoto(request) : session.capture.takePhoto());

  const remembered = noFourByThree ? undefined : rememberedRequest();
  if (remembered) {
    try {
      const blob = await photo(remembered);
      if ((await fourByThreeOrUnknown(blob)) !== false) return blob;
    } catch {
      // the remembered size no longer works: search again below
    }
    forgetRequest();
  }

  let firstAnswer: Blob | null = null;
  if (!noFourByThree) {
    for (const request of stillRequests(session)) {
      let blob: Blob;
      try {
        blob = await photo(request);
      } catch {
        continue;
      }
      if (blob.size === 0) continue;
      const verdict = await fourByThreeOrUnknown(blob);
      if (verdict === null) return blob;
      if (verdict) {
        rememberRequest(request);
        return blob;
      }
      firstAnswer ??= blob;
    }
    noFourByThree = true;
  }
  return firstAnswer ?? photo(undefined);
}

export const MAX_DIGITAL_ZOOM = 3;

export interface CropEnv {
  createImageBitmap: (blob: Blob, options?: ImageBitmapOptions) => Promise<{ width: number; height: number; close?: () => void }>;
  createCanvas: () => {
    width: number;
    height: number;
    getContext: (id: '2d') => { drawImage: (...args: number[] | unknown[]) => void } | null;
    toBlob: (callback: (blob: Blob | null) => void, type?: string, quality?: number) => void;
  };
}

const browserCropEnv = (): CropEnv => ({
  createImageBitmap: (blob, options) => createImageBitmap(blob, options),
  createCanvas: () => document.createElement('canvas') as unknown as ReturnType<CropEnv['createCanvas']>,
});

/** Digital zoom: the middle 1/zoom of the (upright) photo as a new JPEG that keeps the original's EXIF capture time. */
export async function cropCenter(blob: Blob, zoom: number, env: CropEnv = browserCropEnv()): Promise<Blob> {
  const bitmap = await env.createImageBitmap(blob, { imageOrientation: 'from-image' });
  try {
    const width = Math.max(1, Math.round(bitmap.width / zoom));
    const height = Math.max(1, Math.round(bitmap.height / zoom));
    const left = Math.round((bitmap.width - width) / 2);
    const top = Math.round((bitmap.height - height) / 2);
    const canvas = env.createCanvas();
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) throw new DOMException('the canvas has no 2d context', 'NotSupportedError');
    context.drawImage(bitmap, left, top, width, height, 0, 0, width, height);
    const cropped = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((result) => (result ? resolve(result) : reject(new DOMException('the crop could not be encoded', 'EncodingError'))), 'image/jpeg', 0.92),
    );
    return copyExifUpright(blob, cropped);
  } finally {
    bitmap.close?.();
  }
}

/**
 * One still for the series: a full 4:3 frame at the largest size the camera really gives, cropped around the centre when the
 * viewfinder is zoomed in (`zoom` > 1). The error is the caller's.
 */
export async function takeStill(
  session: CameraSession,
  index: number,
  now: Date = new Date(),
  zoom = 1,
  crop: (blob: Blob, zoom: number) => Promise<Blob> = cropCenter,
): Promise<File> {
  let blob = await takeFourByThree(session);
  if (blob.size === 0) throw new DOMException('the camera returned an empty photo', 'OperationError');
  if (zoom > 1.01) blob = await crop(blob, Math.min(zoom, MAX_DIGITAL_ZOOM));
  return new File([blob], stillFileName(now, index), { type: blob.type || 'image/jpeg', lastModified: now.getTime() });
}
