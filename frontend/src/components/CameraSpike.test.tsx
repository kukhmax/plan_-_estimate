import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { jpegWithExif } from '../test/jpegFixtures';
import { CameraSpike } from './CameraSpike';

function fakeTrack(settings: Record<string, unknown> = { width: 1920, height: 1080, frameRate: 30, facingMode: 'environment' }) {
  const listeners: Record<string, () => void> = {};
  return {
    stop: vi.fn(),
    readyState: 'live',
    getSettings: () => settings,
    getCapabilities: () => ({ width: { min: 1, max: 4000 }, height: { min: 1, max: 3000 }, torch: true }),
    addEventListener: (name: string, cb: () => void) => {
      listeners[name] = cb;
    },
    fire: (name: string) => listeners[name]?.(),
  };
}

function fakeStream(track: ReturnType<typeof fakeTrack>) {
  return { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream;
}

let getUserMedia: ReturnType<typeof vi.fn>;

function renderSpike(onClose = vi.fn()) {
  render(
    <I18nProvider>
      <CameraSpike onClose={onClose} />
    </I18nProvider>,
  );
  return { onClose };
}

const report = () => screen.getByTestId('camera-report').textContent ?? '';

beforeEach(() => {
  localStorage.clear();
  getUserMedia = vi.fn();
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia, enumerateDevices: async () => [{ kind: 'videoinput', label: 'Back camera' }] },
  });
  // jsdom does not implement media playback
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() }));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('CameraSpike', () => {
  it('shows the environment first and four-line help in Polish', () => {
    renderSpike();
    expect(screen.getByRole('dialog', { name: 'Diagnostyka kamery' })).toBeInTheDocument();
    expect(report()).toContain('== environment ==');
    expect(report()).toContain('getUserMedia=true');
    expect(screen.getByRole('button', { name: 'Zdjęcie: takePhoto' })).toBeDisabled();
  });

  it('is localized in Russian', () => {
    localStorage.setItem('locale', 'ru');
    renderSpike();
    expect(screen.getByRole('dialog', { name: 'Диагностика камеры' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Остановить камеру' })).toBeDisabled();
  });

  it('starts the camera with the chosen preset and reports what the host granted', async () => {
    const track = fakeTrack();
    getUserMedia.mockResolvedValue(fakeStream(track));
    renderSpike();
    fireEvent.click(screen.getByRole('button', { name: 'Uruchom kamerę — 1920×1080' }));
    await waitFor(() => expect(report()).toContain('settings: 1920x1080 @30 facing=environment state=live'));
    expect(getUserMedia).toHaveBeenCalledWith({
      audio: false,
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
    });
    expect(report()).toContain('== start fhd (1920x1080) ==');
    expect(report()).toMatch(/getUserMedia ok in \d+ ms/);
    expect(report()).toContain('capabilities: width 1..4000 height 1..3000 zoom - torch=true');
    expect(report()).toContain('devices: videoinput=1 (labels visible)');
    expect(screen.getByRole('button', { name: 'Zdjęcie: takePhoto' })).toBeEnabled();
  });

  it('writes a denied permission into the report instead of failing silently', async () => {
    getUserMedia.mockRejectedValue(new DOMException('Permission denied', 'NotAllowedError'));
    renderSpike();
    fireEvent.click(screen.getByRole('button', { name: 'Uruchom kamerę — maksymalna rozdzielczość' }));
    await waitFor(() => expect(report()).toMatch(/getUserMedia failed in \d+ ms: NotAllowedError: Permission denied/));
    expect(screen.getByRole('button', { name: 'Zdjęcie: takePhoto' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Uruchom kamerę — 1280×720' })).toBeEnabled();
  });

  it('says so when the host has no camera API', async () => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: undefined });
    renderSpike();
    fireEvent.click(screen.getByRole('button', { name: 'Uruchom kamerę — 1280×720' }));
    await waitFor(() => expect(report()).toContain('navigator.mediaDevices.getUserMedia is not available'));
  });

  it('takes a still with ImageCapture and shows it with its details', async () => {
    const track = fakeTrack();
    getUserMedia.mockResolvedValue(fakeStream(track));
    class FakeImageCapture {
      takePhoto = async () => new Blob([jpegWithExif({ original: new Date() })], { type: 'image/jpeg' });
    }
    vi.stubGlobal('ImageCapture', FakeImageCapture);
    renderSpike();
    fireEvent.click(screen.getByRole('button', { name: 'Uruchom kamerę — 1920×1080' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Zdjęcie: takePhoto' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Zdjęcie: takePhoto' }));
    await waitFor(() => expect(report()).toMatch(/takePhoto ok in \d+ ms: image\/jpeg .* exif=\d{4}-/));
    expect(screen.getByRole('img', { name: 'takePhoto' })).toHaveAttribute('src', 'blob:test');
    expect(screen.getByRole('region', { name: 'Wykonane zdjęcia testowe' })).toBeInTheDocument();
  });

  it('reports a canvas still that has no frame yet (jsdom video has no size)', async () => {
    getUserMedia.mockResolvedValue(fakeStream(fakeTrack()));
    renderSpike();
    fireEvent.click(screen.getByRole('button', { name: 'Uruchom kamerę — 1920×1080' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Zdjęcie: klatka z podglądu' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Zdjęcie: klatka z podglądu' }));
    await waitFor(() => expect(report()).toContain('canvas: the video has no frame yet'));
  });

  it('records that the host stopped the camera (track ended)', async () => {
    const track = fakeTrack();
    getUserMedia.mockResolvedValue(fakeStream(track));
    renderSpike();
    fireEvent.click(screen.getByRole('button', { name: 'Uruchom kamerę — 1920×1080' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Zatrzymaj kamerę' })).toBeEnabled());
    act(() => track.fire('ended'));
    expect(report()).toContain('track ended (the host stopped the camera)');
  });

  it('stops the camera on "Stop", on restart and when the screen closes', async () => {
    const first = fakeTrack();
    const second = fakeTrack();
    getUserMedia.mockResolvedValueOnce(fakeStream(first)).mockResolvedValueOnce(fakeStream(second));
    const { onClose } = renderSpike();
    fireEvent.click(screen.getByRole('button', { name: 'Uruchom kamerę — 1920×1080' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Zatrzymaj kamerę' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Zatrzymaj kamerę' }));
    expect(first.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Zatrzymaj kamerę' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Uruchom kamerę — 1280×720' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Zatrzymaj kamerę' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij' }));
    expect(second.stop).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('releases the camera when it is unmounted while running', async () => {
    const track = fakeTrack();
    getUserMedia.mockResolvedValue(fakeStream(track));
    const { unmount } = render(
      <I18nProvider>
        <CameraSpike onClose={() => undefined} />
      </I18nProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Uruchom kamerę — 1920×1080' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Zatrzymaj kamerę' })).toBeEnabled());
    unmount();
    expect(track.stop).toHaveBeenCalledTimes(1);
  });

  it('copies the whole report, or tells how to copy by hand when the clipboard is not there', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    renderSpike();
    fireEvent.click(screen.getByRole('button', { name: 'Skopiuj raport' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Raport skopiowany.'));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('== environment =='));

    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
    fireEvent.click(screen.getByRole('button', { name: 'Skopiuj raport' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Nie można skopiować automatycznie'));
    expect(report()).toContain('copy failed: Error: clipboard is not available');
  });

  it('keeps controls thumb-sized and the report wrapping (mobile rules)', () => {
    renderSpike();
    for (const name of ['Uruchom kamerę — maksymalna rozdzielczość', 'Zdjęcie: takePhoto', 'Skopiuj raport']) {
      expect(screen.getByRole('button', { name })).toHaveClass('min-h-11', 'w-full');
    }
    expect(screen.getByTestId('camera-report')).toHaveClass('whitespace-pre-wrap', 'break-words');
  });

  it('the size test prints the ladder, then the zoom and exact-stream probes, and ends with the camera stopped', async () => {
    const track = fakeTrack();
    getUserMedia.mockResolvedValue(fakeStream(track));
    class FakeImageCapture {
      takePhoto = async () => new Blob([jpegWithExif()], { type: 'image/jpeg' });
      getPhotoCapabilities = async () => ({ imageWidth: { min: 1, max: 4624, step: 1 }, imageHeight: { min: 1, max: 3472, step: 1 } });
    }
    vi.stubGlobal('ImageCapture', FakeImageCapture);
    renderSpike();
    expect(screen.getByRole('button', { name: 'Test rozmiarów zdjęć i zoomu' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Uruchom kamerę — 1920×1080' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Test rozmiarów zdjęć i zoomu' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Test rozmiarów zdjęć i zoomu' }));
    await waitFor(() => expect(report()).toContain('== exact-size stream =='), { timeout: 4000 });
    expect(report()).toContain('== size ladder (takePhoto) ==');
    expect(report()).toContain('photoCapabilities: imageWidth 1..4624');
    expect(report()).toContain('ask 4624x3472 -> got');
    expect(report()).toContain('== zoom ==');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Zatrzymaj kamerę' })).toBeDisabled());
  });
});
