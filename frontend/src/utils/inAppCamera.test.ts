import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installFakeCamera } from '../test/cameraFixtures';
import { jpegWithSize } from '../test/jpegFixtures';
import { readExifCaptureTime } from './jpegExif';
import {
  CropEnv,
  MAX_DIGITAL_ZOOM,
  PREVIEW_CONSTRAINTS,
  STILL_LADDER,
  classifyCameraError,
  closeCamera,
  cropCenter,
  inAppCameraSupported,
  isFourByThree,
  openCamera,
  resetStillSizeMemory,
  setTorch,
  stillFileName,
  stillRequests,
  takeStill,
} from './inAppCamera';

beforeEach(() => {
  resetStillSizeMemory();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('inAppCameraSupported', () => {
  it('needs a secure page, getUserMedia and ImageCapture (iOS WebViews have no ImageCapture and keep the native input)', () => {
    installFakeCamera();
    expect(inAppCameraSupported()).toBe(true);
    vi.stubGlobal('ImageCapture', undefined);
    expect(inAppCameraSupported()).toBe(false);
    installFakeCamera();
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false });
    expect(inAppCameraSupported()).toBe(false);
    installFakeCamera();
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: undefined });
    expect(inAppCameraSupported()).toBe(false);
  });
});

describe('classifyCameraError', () => {
  it.each([
    ['NotAllowedError', 'denied'],
    ['SecurityError', 'denied'],
    ['NotFoundError', 'unavailable'],
    ['OverconstrainedError', 'unavailable'],
    ['NotReadableError', 'busy'],
    ['AbortError', 'busy'],
    ['TypeError', 'unsupported'],
    ['NotSupportedError', 'unsupported'],
    ['Whatever', 'unknown'],
  ])('%s → %s', (name, expected) => {
    expect(classifyCameraError({ name })).toBe(expected);
  });

  it('copes with non-errors', () => {
    expect(classifyCameraError(undefined)).toBe('unknown');
    expect(classifyCameraError('x')).toBe('unknown');
  });
});

describe('openCamera', () => {
  it('asks for the rear camera with a modest preview and reads the largest still the camera offers', async () => {
    const fake = installFakeCamera();
    const session = await openCamera();
    expect(fake.getUserMedia).toHaveBeenCalledWith(PREVIEW_CONSTRAINTS);
    expect(PREVIEW_CONSTRAINTS).toEqual({
      audio: false,
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1440 } },
    });
    expect(session.stillSize).toEqual({ width: 4624, height: 3472 });
    expect(session.hasTorch).toBe(true);
  });

  it('works without photo capabilities and without a torch', async () => {
    installFakeCamera({ torch: false, photoMax: null });
    const session = await openCamera();
    expect(session.stillSize).toBeNull();
    expect(session.hasTorch).toBe(false);
  });

  it('survives a host whose getPhotoCapabilities rejects', async () => {
    const fake = installFakeCamera();
    fake.getPhotoCapabilities.mockRejectedValue(new DOMException('no', 'NotSupportedError'));
    const session = await openCamera();
    expect(session.stillSize).toBeNull();
    expect(session.stream).toBeDefined();
  });

  it('fails with the host error when the camera is refused', async () => {
    const fake = installFakeCamera();
    fake.getUserMedia.mockRejectedValue({ name: 'NotAllowedError' });
    await expect(openCamera()).rejects.toMatchObject({ name: 'NotAllowedError' });
  });

  it('releases a stream that has no video track', async () => {
    const fake = installFakeCamera();
    const stop = vi.fn();
    fake.getUserMedia.mockResolvedValue({ getVideoTracks: () => [], getTracks: () => [{ stop }] });
    await expect(openCamera()).rejects.toMatchObject({ name: 'NotFoundError' });
    expect(stop).toHaveBeenCalledTimes(1);
  });

  it('reports an unsupported host', async () => {
    installFakeCamera();
    vi.stubGlobal('ImageCapture', undefined);
    await expect(openCamera()).rejects.toMatchObject({ name: 'NotSupportedError' });
  });
});

describe('closeCamera / setTorch', () => {
  it('stops every track and tolerates no session', async () => {
    const fake = installFakeCamera();
    const session = await openCamera();
    closeCamera(session);
    expect(fake.tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(() => closeCamera(null)).not.toThrow();
  });

  it('switches the torch through an advanced constraint', async () => {
    const fake = installFakeCamera();
    const session = await openCamera();
    await setTorch(session, true);
    expect(fake.tracks[0].applyConstraints).toHaveBeenCalledWith({ advanced: [{ torch: true }] });
  });
});

describe('takeStill', () => {
  it('asks for the largest still explicitly and wraps the JPEG in a named file', async () => {
    const fake = installFakeCamera();
    const session = await openCamera();
    const now = new Date(2026, 9, 7, 11, 18, 5);
    const file = await takeStill(session, 3, now);
    expect(fake.takePhoto).toHaveBeenCalledWith({ imageWidth: 4624, imageHeight: 3472 });
    expect(file.name).toBe('kamera-20261007-111805-3.jpg');
    expect(file.type).toBe('image/jpeg');
    expect(file.lastModified).toBe(now.getTime());
    expect(file.size).toBeGreaterThan(0);
  });

  it('takes a plain photo when the camera reports no size', async () => {
    const fake = installFakeCamera({ photoMax: null });
    const session = await openCamera();
    await takeStill(session, 1);
    expect(fake.takePhoto).toHaveBeenCalledWith();
  });

  it('moves on to the next size when the host refuses one', async () => {
    const fake = installFakeCamera();
    const session = await openCamera();
    fake.takePhoto.mockRejectedValueOnce(new DOMException('bad size', 'OperationError'));
    const file = await takeStill(session, 1);
    expect(fake.takePhoto).toHaveBeenCalledTimes(2);
    expect(fake.takePhoto).toHaveBeenLastCalledWith({ imageWidth: 4000, imageHeight: 3000 });
    expect(file.size).toBeGreaterThan(0);
  });

  it('gives up with the host error when both tries fail, and refuses an empty photo', async () => {
    const fake = installFakeCamera();
    const session = await openCamera();
    fake.takePhoto.mockRejectedValue(new DOMException('dead', 'OperationError'));
    await expect(takeStill(session, 1)).rejects.toMatchObject({ name: 'OperationError' });
    fake.takePhoto.mockReset().mockResolvedValue(new Blob([], { type: 'image/jpeg' }));
    await expect(takeStill(session, 1)).rejects.toMatchObject({ message: 'the camera returned an empty photo' });
  });

  it('falls back to image/jpeg when the host gives no type', async () => {
    const fake = installFakeCamera();
    const session = await openCamera();
    fake.takePhoto.mockResolvedValue(new Blob(['x']));
    expect((await takeStill(session, 1)).type).toBe('image/jpeg');
  });
});

describe('stillFileName', () => {
  it('is ASCII, sortable and unique within a series', () => {
    const d = new Date(2026, 0, 2, 3, 4, 5);
    expect(stillFileName(d, 1)).toBe('kamera-20260102-030405-1.jpg');
    expect(stillFileName(d, 10)).toBe('kamera-20260102-030405-10.jpg');
  });
});

// ---- 14E.10 follow-up: 4:3 stills and digital zoom (sizes taken from the owner's phone: 3472x3472, 3840x2160, 2304x1296, 1920x1440)

type PhotoRequest = { imageWidth?: number; imageHeight?: number } | undefined;

/** A takePhoto that answers like Chrome on Android: the listed size nearest (sum of differences) to the one asked for. */
function hostWithSizes(fake: ReturnType<typeof installFakeCamera>, sizes: Array<[number, number]>) {
  fake.takePhoto.mockImplementation(async (request: PhotoRequest) => {
    const [width, height] = request?.imageWidth
      ? sizes.reduce((best, size) =>
          Math.abs(size[0] - request.imageWidth!) + Math.abs(size[1] - (request.imageHeight ?? 0)) <
          Math.abs(best[0] - request.imageWidth!) + Math.abs(best[1] - (request.imageHeight ?? 0))
            ? size
            : best,
        )
      : sizes[0];
    return new Blob([jpegWithSize(width, height, { orientation: 6, original: new Date(2026, 9, 7, 12, 0, 0) })], { type: 'image/jpeg' });
  });
}

const OWNER_PHONE: Array<[number, number]> = [
  [3472, 3472],
  [3840, 2160],
  [2304, 1296],
  [1920, 1440],
];
const askedSizes = (fake: ReturnType<typeof installFakeCamera>) =>
  fake.takePhoto.mock.calls.map((call) => (call[0] ? `${call[0].imageWidth}x${call[0].imageHeight}` : 'default'));
const sizeOf = async (file: Blob) => (await import('./jpegMeta')).readJpegSize(file);

describe('isFourByThree', () => {
  it('accepts a 4:3 frame in either orientation, including the 4624x3472 sensor, and nothing else', () => {
    expect(isFourByThree({ width: 4624, height: 3472 })).toBe(true);
    expect(isFourByThree({ width: 1440, height: 1920 })).toBe(true);
    expect(isFourByThree({ width: 4000, height: 3000 })).toBe(true);
    expect(isFourByThree({ width: 3472, height: 3472 })).toBe(false);
    expect(isFourByThree({ width: 3840, height: 2160 })).toBe(false);
    expect(isFourByThree({ width: 4160, height: 3120 })).toBe(true);
    expect(isFourByThree({ width: 0, height: 0 })).toBe(false);
  });
});

describe('stillRequests', () => {
  it('starts with the camera maximum, then the ladder below it, without the maximum twice', () => {
    const asked = stillRequests({ stillSize: { width: 4624, height: 3472 } });
    expect(asked[0]).toEqual({ imageWidth: 4624, imageHeight: 3472 });
    expect(asked.slice(1)).toEqual(STILL_LADDER.map((s) => ({ imageWidth: s.width, imageHeight: s.height })));
    const small = stillRequests({ stillSize: { width: 2048, height: 1536 } });
    expect(small).toEqual([
      { imageWidth: 2048, imageHeight: 1536 },
      { imageWidth: 1920, imageHeight: 1440 },
      { imageWidth: 1280, imageHeight: 960 },
    ]);
  });

  it('starts with the host default when the maximum is unknown', () => {
    const asked = stillRequests({ stillSize: null });
    expect(asked[0]).toBeUndefined();
    expect(asked).toHaveLength(1 + STILL_LADDER.length);
  });
});

describe('takeStill — the largest size that really comes back 4:3', () => {
  it("walks down the ladder on the owner's phone, keeps the 4:3 answer and remembers the size that gave it", async () => {
    const fake = installFakeCamera();
    hostWithSizes(fake, OWNER_PHONE);
    const session = await openCamera();
    const file = await takeStill(session, 1);
    expect(askedSizes(fake)).toEqual(['4624x3472', '4000x3000', '3264x2448', '2592x1944', '2048x1536']);
    expect(await sizeOf(file)).toEqual({ width: 1920, height: 1440 });
    expect(JSON.parse(localStorage.getItem('plan-estimate:camera-still-size:v1') ?? 'null')).toEqual({ width: 2048, height: 1536 });

    fake.takePhoto.mockClear();
    await takeStill(session, 2);
    expect(askedSizes(fake)).toEqual(['2048x1536']); // the next shot (and the next session) asks for it directly
  });

  it('takes the first answer at once when the camera maximum is already 4:3', async () => {
    const fake = installFakeCamera();
    hostWithSizes(fake, [[4624, 3472], [3472, 3472]]);
    const session = await openCamera();
    expect(await sizeOf(await takeStill(session, 1))).toEqual({ width: 4624, height: 3472 });
    expect(askedSizes(fake)).toEqual(['4624x3472']);
  });

  it('forgets a remembered size that no longer gives 4:3 (phone or Telegram update) and searches again', async () => {
    const fake = installFakeCamera();
    localStorage.setItem('plan-estimate:camera-still-size:v1', JSON.stringify({ width: 2048, height: 1536 }));
    hostWithSizes(fake, [[3472, 3472], [3840, 2160], [4000, 3000]]);
    const session = await openCamera();
    const file = await takeStill(session, 1);
    expect(askedSizes(fake)).toEqual(['2048x1536', '4624x3472']); // the host answers 4000x3000 to the camera maximum
    expect(await sizeOf(file)).toEqual({ width: 4000, height: 3000 });
    expect(JSON.parse(localStorage.getItem('plan-estimate:camera-still-size:v1') ?? 'null')).toEqual({ width: 4624, height: 3472 });
  });

  it('keeps the largest answer when the camera has no 4:3 still at all, and does not repeat the search for the next shots', async () => {
    const fake = installFakeCamera();
    hostWithSizes(fake, [[3472, 3472], [3840, 2160]]);
    const session = await openCamera();
    const first = await takeStill(session, 1);
    expect(await sizeOf(first)).toEqual({ width: 3472, height: 3472 });
    expect(askedSizes(fake)).toHaveLength(1 + STILL_LADDER.length);
    expect(localStorage.getItem('plan-estimate:camera-still-size:v1')).toBeNull();

    fake.takePhoto.mockClear();
    await takeStill(session, 2);
    expect(askedSizes(fake)).toEqual(['default']);
  });

  it('drops a stale remembered size from storage when the search finds no 4:3 either', async () => {
    const fake = installFakeCamera();
    localStorage.setItem('plan-estimate:camera-still-size:v1', JSON.stringify({ width: 2048, height: 1536 }));
    hostWithSizes(fake, [[3472, 3472], [3840, 2160]]);
    const session = await openCamera();
    await takeStill(session, 1);
    expect(localStorage.getItem('plan-estimate:camera-still-size:v1')).toBeNull();
  });

  it('works without storage and ignores a corrupt remembered value', async () => {
    const fake = installFakeCamera();
    hostWithSizes(fake, OWNER_PHONE);
    localStorage.setItem('plan-estimate:camera-still-size:v1', '{broken');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    const session = await openCamera();
    expect(await sizeOf(await takeStill(session, 1))).toEqual({ width: 1920, height: 1440 });
  });
});

describe('takeStill — digital zoom', () => {
  const crop = () => vi.fn(async (_blob: Blob, _zoom: number) => new Blob(['cropped'], { type: 'image/jpeg' }));

  it('crops around the centre only when zoomed in, never beyond the maximum zoom', async () => {
    const fake = installFakeCamera();
    const session = await openCamera();
    const cropper = crop();
    await takeStill(session, 1, new Date(), 1, cropper);
    await takeStill(session, 2, new Date(), 1.005, cropper);
    expect(cropper).not.toHaveBeenCalled();
    const zoomed = await takeStill(session, 3, new Date(), 2, cropper);
    expect(cropper).toHaveBeenLastCalledWith(expect.any(Blob), 2);
    expect(
      await new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.readAsText(zoomed);
      }),
    ).toBe('cropped');
    await takeStill(session, 4, new Date(), 9, cropper);
    expect(cropper).toHaveBeenLastCalledWith(expect.any(Blob), MAX_DIGITAL_ZOOM);
    expect(fake.takePhoto).toHaveBeenCalledTimes(4);
  });
});

describe('cropCenter', () => {
  const shot = new Date(2026, 9, 7, 12, 0, 0);
  function fakeEnv(options: { noContext?: boolean; encodeFails?: boolean } = {}) {
    const bitmap = { width: 1440, height: 1920, close: vi.fn() };
    const drawImage = vi.fn();
    const canvas = {
      width: 0,
      height: 0,
      getContext: () => (options.noContext ? null : { drawImage }),
      toBlob: (cb: (b: Blob | null) => void) => cb(options.encodeFails ? null : new Blob([jpegWithSize(720, 960)], { type: 'image/jpeg' })),
    };
    const createImageBitmap = vi.fn(async () => bitmap);
    return { env: { createImageBitmap, createCanvas: () => canvas } as unknown as CropEnv, bitmap, drawImage, canvas, createImageBitmap };
  }
  const original = () => new Blob([jpegWithSize(1440, 1920, { orientation: 6, original: shot })], { type: 'image/jpeg' });

  it('draws the middle 1/zoom of the upright photo, closes the bitmap and keeps the capture time', async () => {
    const { env, bitmap, drawImage, canvas, createImageBitmap } = fakeEnv();
    const cropped = await cropCenter(original(), 2, env);
    expect(createImageBitmap).toHaveBeenCalledWith(expect.any(Blob), { imageOrientation: 'from-image' });
    expect([canvas.width, canvas.height]).toEqual([720, 960]);
    expect(drawImage).toHaveBeenCalledWith(bitmap, 360, 480, 720, 960, 0, 0, 720, 960);
    expect(bitmap.close).toHaveBeenCalledTimes(1);
    expect(await readExifCaptureTime(cropped)).toEqual(shot);
  });

  it('rounds odd sizes and stays inside the photo at 3x', async () => {
    const { env, drawImage } = fakeEnv();
    await cropCenter(original(), 3, env);
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 480, 640, 480, 640, 0, 0, 480, 640);
  });

  it('fails loudly (and still closes the bitmap) when there is no canvas context or the JPEG cannot be encoded', async () => {
    const noContext = fakeEnv({ noContext: true });
    await expect(cropCenter(original(), 2, noContext.env)).rejects.toMatchObject({ name: 'NotSupportedError' });
    expect(noContext.bitmap.close).toHaveBeenCalledTimes(1);
    const noEncode = fakeEnv({ encodeFails: true });
    await expect(cropCenter(original(), 2, noEncode.env)).rejects.toMatchObject({ name: 'EncodingError' });
    expect(noEncode.bitmap.close).toHaveBeenCalledTimes(1);
  });
});
