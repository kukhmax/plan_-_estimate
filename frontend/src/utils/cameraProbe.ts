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

export async function describeBlob(blob: Blob): Promise<string> {
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

// ---- Stage 14E.10 follow-up: why was the still square, and is there a zoom? ----------------------------------------------
// The first viewfinder asked for the largest still the camera announced and still got 3472x3472. These probes try a ladder of
// explicit sizes, an exact-size video stream and the zoom (which Chrome only exposes after a PTZ request) and print what came out.

type PhotoSettingsLike = { imageWidth?: number; imageHeight?: number };
type PhotoCaptureLike = {
  takePhoto: (settings?: PhotoSettingsLike) => Promise<Blob>;
  getPhotoCapabilities?: () => Promise<Record<string, unknown>>;
};
type PhotoCaptureCtor = new (track: MediaStreamTrack) => PhotoCaptureLike;

export const SIZE_LADDER: ReadonlyArray<{ width: number; height: number }> = [
  { width: 4624, height: 3472 },
  { width: 4000, height: 3000 },
  { width: 3264, height: 2448 },
  { width: 2560, height: 1920 },
  { width: 1920, height: 1440 },
];

function rangeText(value: unknown): string {
  if (value && typeof value === 'object') {
    const r = value as { min?: number; max?: number; step?: number; current?: number };
    return `${r.min ?? '?'}..${r.max ?? '?'} step ${r.step ?? '?'}`;
  }
  return '-';
}

export async function describePhotoCapabilities(capture: PhotoCaptureLike): Promise<string[]> {
  if (!capture.getPhotoCapabilities) return ['photoCapabilities: getPhotoCapabilities is not available'];
  try {
    const caps = await capture.getPhotoCapabilities();
    return [
      `photoCapabilities: imageWidth ${rangeText(caps.imageWidth)} | imageHeight ${rangeText(caps.imageHeight)}`,
      `photoCapabilities: fillLightMode=${JSON.stringify(caps.fillLightMode ?? null)} redEye=${String(caps.redEyeReduction ?? '-')}`,
    ];
  } catch (error) {
    return [`photoCapabilities failed: ${describeError(error)}`];
  }
}

async function dimsOf(blob: Blob): Promise<string> {
  if (typeof createImageBitmap !== 'function') return 'size n/a';
  try {
    const bitmap = await createImageBitmap(blob);
    const text = `${bitmap.width}x${bitmap.height}`;
    bitmap.close?.();
    return text;
  } catch (error) {
    return `decode failed (${describeError(error)})`;
  }
}

/** takePhoto with the default settings, then with each size of the ladder; one line per attempt. */
export async function runSizeLadder(track: MediaStreamTrack, win: unknown = window): Promise<string[]> {
  const Ctor = (win as { ImageCapture?: PhotoCaptureCtor }).ImageCapture;
  if (!Ctor) return ['sizes: ImageCapture is not available'];
  const capture = new Ctor(track);
  const lines = await describePhotoCapabilities(capture);
  const attempts: Array<{ label: string; settings?: PhotoSettingsLike }> = [
    { label: 'default' },
    ...SIZE_LADDER.map((s) => ({ label: `${s.width}x${s.height}`, settings: { imageWidth: s.width, imageHeight: s.height } })),
  ];
  for (const attempt of attempts) {
    const started = performance.now();
    try {
      const blob = await capture.takePhoto(attempt.settings);
      lines.push(`ask ${attempt.label} -> got ${await dimsOf(blob)} ${megabytes(blob.size)} in ${Math.round(performance.now() - started)} ms`);
    } catch (error) {
      lines.push(`ask ${attempt.label} -> failed: ${describeError(error)}`);
    }
  }
  return lines;
}

/** A separate stream asked for the zoom (this triggers Chrome's PTZ request); reports the range and whether it can be set. */
export async function probeZoom(win: Window & typeof globalThis = window): Promise<string[]> {
  const devices = win.navigator.mediaDevices;
  if (!devices?.getUserMedia) return ['zoom: getUserMedia is not available'];
  let stream: MediaStream | null = null;
  try {
    stream = await devices.getUserMedia({
      audio: false,
      video: { facingMode: { ideal: 'environment' }, zoom: true } as unknown as MediaTrackConstraints,
    });
    const track = stream.getVideoTracks()[0];
    const caps = (track?.getCapabilities?.() ?? {}) as Record<string, unknown>;
    const lines = [`zoom stream ok: capabilities.zoom ${rangeText(caps.zoom)} | settings.zoom=${String((track?.getSettings?.() as Record<string, unknown> | undefined)?.zoom ?? '-')}`];
    const zoom = caps.zoom as { min?: number; max?: number } | undefined;
    if (track && zoom?.max && zoom.max > (zoom.min ?? 1)) {
      const target = Math.min(zoom.max, (zoom.min ?? 1) * 2);
      try {
        await track.applyConstraints({ advanced: [{ zoom: target } as MediaTrackConstraintSet] });
        lines.push(`zoom applyConstraints ${target} ok -> settings.zoom=${String((track.getSettings() as Record<string, unknown>).zoom ?? '-')}`);
      } catch (error) {
        lines.push(`zoom applyConstraints ${target} failed: ${describeError(error)}`);
      }
    } else {
      lines.push('zoom: the camera does not report a zoom range');
    }
    return lines;
  } catch (error) {
    return [`zoom stream failed: ${describeError(error)}`];
  } finally {
    stream?.getTracks().forEach((t) => t.stop());
  }
}

/** A video stream asked for the sensor size exactly, then a default takePhoto: does the still follow the stream? */
export async function probeExactStream(win: Window & typeof globalThis = window): Promise<string[]> {
  const devices = win.navigator.mediaDevices;
  const Ctor = (win as unknown as { ImageCapture?: PhotoCaptureCtor }).ImageCapture;
  if (!devices?.getUserMedia || !Ctor) return ['exact: camera API is not available'];
  let stream: MediaStream | null = null;
  try {
    stream = await devices.getUserMedia({
      audio: false,
      video: { facingMode: { ideal: 'environment' }, width: { exact: 4624 }, height: { exact: 3472 } },
    });
    const track = stream.getVideoTracks()[0];
    const settings = track.getSettings();
    const lines = [`exact 4624x3472 stream ok: settings ${settings.width ?? '?'}x${settings.height ?? '?'}`];
    const started = performance.now();
    const blob = await new Ctor(track).takePhoto();
    lines.push(`exact stream + default takePhoto -> ${await dimsOf(blob)} ${megabytes(blob.size)} in ${Math.round(performance.now() - started)} ms`);
    return lines;
  } catch (error) {
    return [`exact stream failed: ${describeError(error)}`];
  } finally {
    stream?.getTracks().forEach((t) => t.stop());
  }
}
