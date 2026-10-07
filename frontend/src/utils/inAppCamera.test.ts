import { afterEach, describe, expect, it, vi } from 'vitest';
import { installFakeCamera } from '../test/cameraFixtures';
import {
  PREVIEW_CONSTRAINTS,
  classifyCameraError,
  closeCamera,
  inAppCameraSupported,
  openCamera,
  setTorch,
  stillFileName,
  takeStill,
} from './inAppCamera';

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

  it('retries once with the host defaults when the explicit size is refused', async () => {
    const fake = installFakeCamera();
    const session = await openCamera();
    fake.takePhoto.mockRejectedValueOnce(new DOMException('bad size', 'OperationError'));
    const file = await takeStill(session, 1);
    expect(fake.takePhoto).toHaveBeenCalledTimes(2);
    expect(fake.takePhoto).toHaveBeenLastCalledWith();
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
