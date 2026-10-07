// Diagnostics for an in-app camera (Stage 14E.9 spike): what does THIS host (Telegram on this phone) really give a page?
// Pure helpers that describe the environment, a started video track and two kinds of still. Nothing here uploads,
// stores or sends anything; every outcome — success or failure — becomes a line of text for the report.

import { readExifCaptureTime } from './jpegExif';

export interface ProbePreset {
  id: 'max' | 'fhd' | 'hd';
  width: number;
  height: number;
}

export const PROBE_PRESETS: readonly ProbePreset[] = [
  { id: 'max', width: 4096, height: 3072 },
  { id: 'fhd', width: 1920, height: 1080 },
  { id: 'hd', width: 1280, height: 720 },
];

export function buildConstraints(preset: ProbePreset): MediaStreamConstraints {
  return {
    audio: false,
    video: { facingMode: { ideal: 'environment' }, width: { ideal: preset.width }, height: { ideal: preset.height } },
  };
}

export function describeError(error: unknown): string {
  // By shape, not `instanceof Error`: a DOMException from getUserMedia is not always an Error in a WebView, and its
  // message is exactly what the diagnosis needs.
  if (error && typeof error === 'object') {
    const { name, message } = error as { name?: unknown; message?: unknown };
    if (typeof name === 'string' && name) return typeof message === 'string' && message ? `${name}: ${message}` : name;
    if (typeof message === 'string' && message) return message;
  }
  return String(error);
}

interface ImageCaptureLike {
  takePhoto: () => Promise<Blob>;
  getPhotoCapabilities?: () => Promise<unknown>;
}
type ImageCaptureCtor = new (track: MediaStreamTrack) => ImageCaptureLike;

function imageCaptureCtor(win: unknown): ImageCaptureCtor | undefined {
  return (win as { ImageCapture?: ImageCaptureCtor }).ImageCapture;
}

export function describeEnvironment(win: Window & typeof globalThis): string[] {
  const telegram = (win as unknown as { Telegram?: { WebApp?: { platform?: string; version?: string; colorScheme?: string } } }).Telegram?.WebApp;
  return [
    `secureContext=${String(win.isSecureContext)} mediaDevices=${String(Boolean(win.navigator.mediaDevices))} ` +
      `getUserMedia=${String(typeof win.navigator.mediaDevices?.getUserMedia === 'function')} ImageCapture=${String(Boolean(imageCaptureCtor(win)))} ` +
      `createImageBitmap=${String(typeof win.createImageBitmap === 'function')}`,
    `telegram platform=${telegram?.platform ?? '-'} version=${telegram?.version ?? '-'} scheme=${telegram?.colorScheme ?? '-'}`,
    `screen=${win.screen?.width ?? '?'}x${win.screen?.height ?? '?'} dpr=${win.devicePixelRatio ?? '?'}`,
    `ua=${win.navigator.userAgent}`,
  ];
}

export async function describePermission(win: Window & typeof globalThis): Promise<string> {
  if (!win.navigator.permissions?.query) return 'permissions API: not available';
  try {
    const status = await win.navigator.permissions.query({ name: 'camera' as PermissionName });
    return `permission camera=${status.state}`;
  } catch (error) {
    return `permission camera: ${describeError(error)}`;
  }
}

export async function describeDevices(devices: Pick<MediaDevices, 'enumerateDevices'> | undefined): Promise<string> {
  if (!devices?.enumerateDevices) return 'devices: enumerateDevices not available';
  try {
    const all = await devices.enumerateDevices();
    const video = all.filter((d) => d.kind === 'videoinput');
    return `devices: videoinput=${video.length} (labels ${video.some((d) => d.label) ? 'visible' : 'hidden'})`;
  } catch (error) {
    return `devices: ${describeError(error)}`;
  }
}

function range(value: unknown): string {
  if (value && typeof value === 'object' && 'min' in value && 'max' in value) {
    const r = value as { min: number; max: number };
    return `${r.min}..${r.max}`;
  }
  return '-';
}

export function describeTrack(track: MediaStreamTrack): string[] {
  const settings = track.getSettings?.() ?? {};
  const caps = (track.getCapabilities?.() ?? {}) as Record<string, unknown>;
  return [
    `settings: ${settings.width ?? '?'}x${settings.height ?? '?'} @${settings.frameRate ?? '?'} facing=${settings.facingMode ?? '-'} state=${track.readyState}`,
    `capabilities: width ${range(caps.width)} height ${range(caps.height)} zoom ${range(caps.zoom)} torch=${String('torch' in caps)}`,
  ];
}

export interface StillResult {
  method: 'takePhoto' | 'canvas';
  ok: boolean;
  line: string;
  blob?: Blob;
}

const megabytes = (bytes: number) => `${(bytes / 1048576).toFixed(2)} MB`;

async function describeBlob(blob: Blob): Promise<string> {
  let size = 'size n/a';
  if (typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(blob);
      size = `${bitmap.width}x${bitmap.height}`;
      bitmap.close?.();
    } catch (error) {
      size = `decode failed (${describeError(error)})`;
    }
  }
  let exif = 'exif=?';
  try {
    const taken = await readExifCaptureTime(blob);
    exif = taken ? `exif=${taken.toISOString()}` : 'exif=none';
  } catch (error) {
    exif = `exif read failed (${describeError(error)})`;
  }
  return `${blob.type || 'no type'} ${megabytes(blob.size)} ${size} ${exif}`;
}

export async function captureWithImageCapture(track: MediaStreamTrack, win: unknown = window): Promise<StillResult> {
  const Ctor = imageCaptureCtor(win);
  if (!Ctor) return { method: 'takePhoto', ok: false, line: 'takePhoto: ImageCapture is not available' };
  const started = performance.now();
  try {
    const blob = await new Ctor(track).takePhoto();
    const took = Math.round(performance.now() - started);
    return { method: 'takePhoto', ok: true, blob, line: `takePhoto ok in ${took} ms: ${await describeBlob(blob)}` };
  } catch (error) {
    return { method: 'takePhoto', ok: false, line: `takePhoto failed: ${describeError(error)}` };
  }
}

export async function captureFromVideo(video: HTMLVideoElement): Promise<StillResult> {
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (!width || !height) return { method: 'canvas', ok: false, line: 'canvas: the video has no frame yet' };
  const started = performance.now();
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) return { method: 'canvas', ok: false, line: 'canvas: no 2d context' };
  context.drawImage(video, 0, 0, width, height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
  if (!blob) return { method: 'canvas', ok: false, line: 'canvas: toBlob returned nothing' };
  const took = Math.round(performance.now() - started);
  return { method: 'canvas', ok: true, blob, line: `canvas ok in ${took} ms: ${await describeBlob(blob)}` };
}
