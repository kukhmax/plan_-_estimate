import { Mock, vi } from 'vitest';
import { jpegWithExif } from './jpegFixtures';

// A fake camera for tests: a stream with one video track, and an ImageCapture whose takePhoto returns a small JPEG.

export interface FakeTrack {
  stop: Mock;
  applyConstraints: Mock;
  addEventListener: (name: string, cb: () => void) => void;
  fire: (name: string) => void;
  getCapabilities: () => Record<string, unknown>;
  getSettings: () => Record<string, unknown>;
  readyState: string;
}

export function fakeTrack(capabilities: Record<string, unknown> = { torch: true }): FakeTrack {
  const listeners: Record<string, () => void> = {};
  return {
    stop: vi.fn(),
    applyConstraints: vi.fn().mockResolvedValue(undefined),
    addEventListener: (name, cb) => {
      listeners[name] = cb;
    },
    fire: (name) => listeners[name]?.(),
    getCapabilities: () => capabilities,
    getSettings: () => ({ width: 1920, height: 1440 }),
    readyState: 'live',
  };
}

export const fakeStream = (track: FakeTrack) =>
  ({ getTracks: () => [track], getVideoTracks: () => [track] }) as unknown as MediaStream;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyMock = Mock<any[], any>;

export interface FakeCameraSetup {
  getUserMedia: AnyMock;
  takePhoto: AnyMock;
  getPhotoCapabilities: AnyMock;
  tracks: FakeTrack[];
}

/** Installs navigator.mediaDevices.getUserMedia, window.ImageCapture and a secure context. Call vi.unstubAllGlobals() afterwards. */
export function installFakeCamera(options: { torch?: boolean; photoMax?: { width: number; height: number } | null } = {}): FakeCameraSetup {
  const tracks: FakeTrack[] = [];
  const getUserMedia = vi.fn(async () => {
    const track = fakeTrack(options.torch === false ? {} : { torch: true });
    tracks.push(track);
    return fakeStream(track);
  });
  const takePhoto = vi.fn(async () => new Blob([jpegWithExif({ original: new Date() })], { type: 'image/jpeg' }));
  const photoMax = options.photoMax === undefined ? { width: 4624, height: 3472 } : options.photoMax;
  const getPhotoCapabilities = vi.fn(async () => (photoMax ? { imageWidth: { max: photoMax.width }, imageHeight: { max: photoMax.height } } : {}));
  class FakeImageCapture {
    takePhoto = takePhoto;
    getPhotoCapabilities = getPhotoCapabilities;
  }
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } });
  Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true });
  vi.stubGlobal('ImageCapture', FakeImageCapture);
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:shot'), revokeObjectURL: vi.fn() }));
  return { getUserMedia, takePhoto, getPhotoCapabilities, tracks };
}
