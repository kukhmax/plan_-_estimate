import { describe, expect, it, vi } from 'vitest';
import { jpegWithExif } from '../test/jpegFixtures';
import {
  PROBE_PRESETS,
  buildConstraints,
  captureFromVideo,
  captureWithImageCapture,
  SIZE_LADDER,
  describeDevices,
  describeEnvironment,
  describeError,
  describePermission,
  describePhotoCapabilities,
  describeTrack,
  probeExactStream,
  probeZoom,
  runSizeLadder,
} from './cameraProbe';

const fakeWin = (extra: Record<string, unknown> = {}) =>
  ({
    isSecureContext: true,
    navigator: { mediaDevices: { getUserMedia: () => undefined }, userAgent: 'UA/1.0', permissions: undefined },
    screen: { width: 1080, height: 2400 },
    devicePixelRatio: 2.75,
    createImageBitmap: () => undefined,
    ...extra,
  }) as unknown as Window & typeof globalThis;

const track = (settings: Record<string, unknown>, capabilities: Record<string, unknown>) =>
  ({ getSettings: () => settings, getCapabilities: () => capabilities, readyState: 'live' }) as unknown as MediaStreamTrack;

describe('buildConstraints', () => {
  it('asks for the rear camera and the preset size, without audio', () => {
    expect(buildConstraints(PROBE_PRESETS[0])).toEqual({
      audio: false,
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 4096 }, height: { ideal: 3072 } },
    });
    expect(PROBE_PRESETS.map((p) => p.id)).toEqual(['max', 'fhd', 'hd']);
  });
});

describe('describeError', () => {
  it('names the error class and message', () => {
    expect(describeError(new DOMException('Permission denied', 'NotAllowedError'))).toBe('NotAllowedError: Permission denied');
    expect(describeError(new TypeError('x'))).toBe('TypeError: x');
    expect(describeError({ name: 'OverconstrainedError' })).toBe('OverconstrainedError');
    expect(describeError({ name: 'NotReadableError', message: 'Could not start video source' })).toBe('NotReadableError: Could not start video source');
    expect(describeError({ message: 'only a message' })).toBe('only a message');
    expect(describeError(new Error(''))).toBe('Error');
    expect(describeError('plain')).toBe('plain');
    expect(describeError(undefined)).toBe('undefined');
  });
});

describe('describeEnvironment', () => {
  it('reports the capabilities that matter and the Telegram host', () => {
    const lines = describeEnvironment(
      fakeWin({ ImageCapture: class {}, Telegram: { WebApp: { platform: 'android', version: '8.0', colorScheme: 'dark' } } }),
    );
    expect(lines[0]).toContain('secureContext=true');
    expect(lines[0]).toContain('getUserMedia=true');
    expect(lines[0]).toContain('ImageCapture=true');
    expect(lines[1]).toBe('telegram platform=android version=8.0 scheme=dark');
    expect(lines[2]).toBe('screen=1080x2400 dpr=2.75');
    expect(lines[3]).toBe('ua=UA/1.0');
  });

  it('says so when there is no camera API at all', () => {
    const win = fakeWin();
    (win.navigator as unknown as { mediaDevices: unknown }).mediaDevices = undefined;
    const [first, second] = describeEnvironment(win);
    expect(first).toContain('mediaDevices=false');
    expect(first).toContain('getUserMedia=false');
    expect(first).toContain('ImageCapture=false');
    expect(second).toContain('platform=-');
  });
});

describe('describePermission / describeDevices', () => {
  it('handles a missing Permissions API, a state and a failure', async () => {
    expect(await describePermission(fakeWin())).toBe('permissions API: not available');
    const ok = fakeWin();
    (ok.navigator as unknown as { permissions: unknown }).permissions = { query: async () => ({ state: 'prompt' }) };
    expect(await describePermission(ok)).toBe('permission camera=prompt');
    const bad = fakeWin();
    (bad.navigator as unknown as { permissions: unknown }).permissions = {
      query: async () => {
        throw new TypeError('unsupported');
      },
    };
    expect(await describePermission(bad)).toBe('permission camera: TypeError: unsupported');
  });

  it('counts video inputs and whether labels are visible', async () => {
    const devices = { enumerateDevices: async () => [{ kind: 'videoinput', label: 'Back' }, { kind: 'videoinput', label: '' }, { kind: 'audioinput', label: 'x' }] } as unknown as MediaDevices;
    expect(await describeDevices(devices)).toBe('devices: videoinput=2 (labels visible)');
    const hidden = { enumerateDevices: async () => [{ kind: 'videoinput', label: '' }] } as unknown as MediaDevices;
    expect(await describeDevices(hidden)).toBe('devices: videoinput=1 (labels hidden)');
    expect(await describeDevices(undefined)).toBe('devices: enumerateDevices not available');
  });
});

describe('describeTrack', () => {
  it('prints the granted size, frame rate and the capability ranges', () => {
    const lines = describeTrack(
      track({ width: 1920, height: 1080, frameRate: 30, facingMode: 'environment' }, { width: { min: 1, max: 4000 }, height: { min: 1, max: 3000 }, zoom: { min: 1, max: 8 }, torch: true }),
    );
    expect(lines[0]).toBe('settings: 1920x1080 @30 facing=environment state=live');
    expect(lines[1]).toBe('capabilities: width 1..4000 height 1..3000 zoom 1..8 torch=true');
  });

  it('is calm about a host that reports nothing', () => {
    const lines = describeTrack(track({}, {}));
    expect(lines[0]).toBe('settings: ?x? @? facing=- state=live');
    expect(lines[1]).toBe('capabilities: width - height - zoom - torch=false');
  });
});

describe('captureWithImageCapture', () => {
  it('reports size, type and the EXIF capture time of the returned JPEG', async () => {
    const jpeg = new Blob([jpegWithExif({ original: new Date(2026, 9, 7, 10, 0, 0) })], { type: 'image/jpeg' });
    class Fake {
      takePhoto = async () => jpeg;
    }
    const result = await captureWithImageCapture(track({}, {}), { ImageCapture: Fake });
    expect(result.ok).toBe(true);
    expect(result.method).toBe('takePhoto');
    expect(result.blob).toBe(jpeg);
    expect(result.line).toMatch(/^takePhoto ok in \d+ ms: image\/jpeg 0\.00 MB /);
    expect(result.line).toContain('exif=2026-10-07');
  });

  it('reports a JPEG without EXIF and a host without ImageCapture', async () => {
    class Fake {
      takePhoto = async () => new Blob([jpegWithExif()], { type: 'image/jpeg' });
    }
    expect((await captureWithImageCapture(track({}, {}), { ImageCapture: Fake })).line).toContain('exif=none');
    const missing = await captureWithImageCapture(track({}, {}), {});
    expect(missing).toEqual({ method: 'takePhoto', ok: false, line: 'takePhoto: ImageCapture is not available' });
  });

  it('turns a rejected takePhoto into a line instead of throwing', async () => {
    class Fake {
      takePhoto = async () => {
        throw new DOMException('not supported', 'NotSupportedError');
      };
    }
    const result = await captureWithImageCapture(track({}, {}), { ImageCapture: Fake });
    expect(result.ok).toBe(false);
    expect(result.line).toBe('takePhoto failed: NotSupportedError: not supported');
  });
});

describe('captureFromVideo', () => {
  const video = (width: number, height: number) => ({ videoWidth: width, videoHeight: height }) as unknown as HTMLVideoElement;

  it('refuses a video without a frame', async () => {
    expect((await captureFromVideo(video(0, 0))).line).toBe('canvas: the video has no frame yet');
  });

  it('draws the frame at its own size and encodes a JPEG', async () => {
    const drawImage = vi.fn();
    const blob = new Blob([jpegWithExif()], { type: 'image/jpeg' });
    const canvas = {
      width: 0,
      height: 0,
      getContext: () => ({ drawImage }),
      toBlob: (cb: (b: Blob | null) => void, type: string, quality: number) => {
        expect([type, quality]).toEqual(['image/jpeg', 0.92]);
        cb(blob);
      },
    };
    const create = vi.spyOn(document, 'createElement').mockReturnValue(canvas as unknown as HTMLElement);
    const result = await captureFromVideo(video(1920, 1080));
    create.mockRestore();
    expect(canvas.width).toBe(1920);
    expect(canvas.height).toBe(1080);
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 1920, 1080);
    expect(result.ok).toBe(true);
    expect(result.line).toMatch(/^canvas ok in \d+ ms: image\/jpeg /);
    expect(result.line).toContain('exif=none');
  });

  it('reports a missing 2d context and an encoder that returns nothing', async () => {
    const noContext = { getContext: () => null };
    let spy = vi.spyOn(document, 'createElement').mockReturnValue(noContext as unknown as HTMLElement);
    expect((await captureFromVideo(video(10, 10))).line).toBe('canvas: no 2d context');
    spy.mockRestore();
    const noBlob = { getContext: () => ({ drawImage: () => undefined }), toBlob: (cb: (b: Blob | null) => void) => cb(null) };
    spy = vi.spyOn(document, 'createElement').mockReturnValue(noBlob as unknown as HTMLElement);
    expect((await captureFromVideo(video(10, 10))).line).toBe('canvas: toBlob returned nothing');
    spy.mockRestore();
  });
});

describe('size ladder, zoom and exact-stream probes (14E.10 follow-up)', () => {
  const mkTrack = (caps: Record<string, unknown> = {}, settings: Record<string, unknown> = {}) =>
    ({
      getCapabilities: () => caps,
      getSettings: () => settings,
      applyConstraints: vi.fn().mockResolvedValue(undefined),
      stop: vi.fn(),
    }) as unknown as MediaStreamTrack & { applyConstraints: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn> };

  const win = (extra: Record<string, unknown>) =>
    fakeWin({ navigator: { mediaDevices: undefined, userAgent: 'UA' }, ...extra });

  it('describePhotoCapabilities prints the size ranges and survives a missing or failing API', async () => {
    const lines = await describePhotoCapabilities({
      takePhoto: async () => new Blob(),
      getPhotoCapabilities: async () => ({ imageWidth: { min: 640, max: 4624, step: 16 }, imageHeight: { min: 480, max: 3472, step: 16 }, fillLightMode: ['off', 'flash'] }),
    });
    expect(lines[0]).toBe('photoCapabilities: imageWidth 640..4624 step 16 | imageHeight 480..3472 step 16');
    expect(lines[1]).toContain('fillLightMode=["off","flash"]');
    expect((await describePhotoCapabilities({ takePhoto: async () => new Blob() }))[0]).toContain('not available');
    const failing = await describePhotoCapabilities({
      takePhoto: async () => new Blob(),
      getPhotoCapabilities: async () => {
        throw new DOMException('no', 'NotSupportedError');
      },
    });
    expect(failing[0]).toBe('photoCapabilities failed: NotSupportedError: no');
  });

  it('runSizeLadder asks for the default and every ladder size and prints each outcome, failures included', async () => {
    const asked: Array<unknown> = [];
    class Fake {
      takePhoto = async (settings?: { imageWidth?: number }) => {
        asked.push(settings ?? 'default');
        if (settings?.imageWidth === 3264) throw new DOMException('bad size', 'OperationError');
        return new Blob([jpegWithExif()], { type: 'image/jpeg' });
      };
      getPhotoCapabilities = async () => ({ imageWidth: { min: 1, max: 4624, step: 1 }, imageHeight: { min: 1, max: 3472, step: 1 } });
    }
    const lines = await runSizeLadder(mkTrack(), { ImageCapture: Fake });
    expect(asked).toEqual(['default', ...SIZE_LADDER.map((s) => ({ imageWidth: s.width, imageHeight: s.height }))]);
    expect(lines[0]).toContain('photoCapabilities: imageWidth 1..4624');
    expect(lines.filter((l) => l.startsWith('ask '))).toHaveLength(1 + SIZE_LADDER.length);
    expect(lines.find((l) => l.startsWith('ask default'))).toMatch(/^ask default -> got .* 0\.00 MB in \d+ ms$/);
    expect(lines.find((l) => l.startsWith('ask 3264x2448'))).toBe('ask 3264x2448 -> failed: OperationError: bad size');
    expect(await runSizeLadder(mkTrack(), {})).toEqual(['sizes: ImageCapture is not available']);
  });

  it('probeZoom asks for the zoom, reports the range, sets 2x and always releases its stream', async () => {
    const track = mkTrack({ zoom: { min: 1, max: 8, step: 0.1 } }, { zoom: 1 });
    const getUserMedia = vi.fn().mockResolvedValue({ getVideoTracks: () => [track], getTracks: () => [track] });
    const lines = await probeZoom(win({ navigator: { mediaDevices: { getUserMedia }, userAgent: 'UA' } }));
    expect(getUserMedia.mock.calls[0][0].video).toMatchObject({ zoom: true });
    expect(lines[0]).toBe('zoom stream ok: capabilities.zoom 1..8 step 0.1 | settings.zoom=1');
    expect(track.applyConstraints).toHaveBeenCalledWith({ advanced: [{ zoom: 2 }] });
    expect(lines[1]).toContain('zoom applyConstraints 2 ok');
    expect(track.stop).toHaveBeenCalledTimes(1);
  });

  it('probeZoom says so when there is no zoom range, and when the stream or the constraint fails', async () => {
    const plain = mkTrack({});
    const ok = vi.fn().mockResolvedValue({ getVideoTracks: () => [plain], getTracks: () => [plain] });
    const noZoom = await probeZoom(win({ navigator: { mediaDevices: { getUserMedia: ok }, userAgent: 'UA' } }));
    expect(noZoom[1]).toBe('zoom: the camera does not report a zoom range');
    expect(plain.stop).toHaveBeenCalledTimes(1);

    const stuck = mkTrack({ zoom: { min: 1, max: 4 } });
    stuck.applyConstraints.mockRejectedValue(new DOMException('no ptz', 'NotAllowedError'));
    const refused = await probeZoom(win({ navigator: { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getVideoTracks: () => [stuck], getTracks: () => [stuck] }) }, userAgent: 'UA' } }));
    expect(refused[1]).toBe('zoom applyConstraints 2 failed: NotAllowedError: no ptz');

    const denied = await probeZoom(win({ navigator: { mediaDevices: { getUserMedia: vi.fn().mockRejectedValue({ name: 'NotAllowedError', message: 'x' }) }, userAgent: 'UA' } }));
    expect(denied).toEqual(['zoom stream failed: NotAllowedError: x']);
    expect(await probeZoom(win({}))).toEqual(['zoom: getUserMedia is not available']);
  });

  it('probeExactStream asks for the sensor size exactly and prints the granted size and the default still', async () => {
    const track = mkTrack({}, { width: 4624, height: 3472 });
    const getUserMedia = vi.fn().mockResolvedValue({ getVideoTracks: () => [track], getTracks: () => [track] });
    class Fake {
      takePhoto = async () => new Blob([jpegWithExif()], { type: 'image/jpeg' });
    }
    const lines = await probeExactStream(win({ ImageCapture: Fake, navigator: { mediaDevices: { getUserMedia }, userAgent: 'UA' } }));
    expect(getUserMedia.mock.calls[0][0].video).toMatchObject({ width: { exact: 4624 }, height: { exact: 3472 } });
    expect(lines[0]).toBe('exact 4624x3472 stream ok: settings 4624x3472');
    expect(lines[1]).toMatch(/^exact stream \+ default takePhoto -> .* in \d+ ms$/);
    expect(track.stop).toHaveBeenCalledTimes(1);
    expect(await probeExactStream(win({}))).toEqual(['exact: camera API is not available']);
    const failing = await probeExactStream(win({ ImageCapture: Fake, navigator: { mediaDevices: { getUserMedia: vi.fn().mockRejectedValue({ name: 'OverconstrainedError' }) }, userAgent: 'UA' } }));
    expect(failing).toEqual(['exact stream failed: OverconstrainedError']);
  });
});
