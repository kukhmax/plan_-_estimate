import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PhotoBackContext, usePhotoBackStack } from '../hooks/PhotoBackContext';
import { I18nProvider } from '../hooks/useI18n';
import { FakeCameraSetup, installFakeCamera } from '../test/cameraFixtures';
import { resetStillSizeMemory } from '../utils/inAppCamera';
import { CameraCapture } from './CameraCapture';

let fake: FakeCameraSetup;

function Harness(props: Partial<React.ComponentProps<typeof CameraCapture>> & { onBackProbe?: (closeTop: () => boolean) => void }) {
  const { registry, closeTop } = usePhotoBackStack();
  props.onBackProbe?.(closeTop);
  return (
    <PhotoBackContext.Provider value={registry}>
      <CameraCapture onDone={() => undefined} onCancel={() => undefined} onUseNativePicker={() => undefined} {...props} />
    </PhotoBackContext.Provider>
  );
}

function renderCamera(props: Parameters<typeof Harness>[0] = {}) {
  const handlers = {
    onDone: vi.fn(),
    onCancel: vi.fn(),
    onUseNativePicker: vi.fn(),
    onCameraFailed: vi.fn(),
  };
  const view = render(
    <I18nProvider>
      <Harness {...handlers} {...props} />
    </I18nProvider>,
  );
  return { ...handlers, ...view };
}

const shutter = () => screen.getByRole('button', { name: 'Zrób zdjęcie' });
const live = async () => waitFor(() => expect(shutter()).toBeEnabled());
const counted = () => Number(/Zrobiono: (\d+) z/.exec(screen.getByRole('status').textContent ?? '')?.[1] ?? '0');
const shoot = async (times = 1) => {
  for (let i = 0; i < times; i += 1) {
    const before = counted();
    fireEvent.click(shutter());
    await waitFor(() => expect(counted()).toBe(before + 1));
  }
};

beforeEach(() => {
  localStorage.clear();
  resetStillSizeMemory();
  fake = installFakeCamera();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('CameraCapture — a series of shots', () => {
  it('starts the camera, shows the counter and enables the shutter when live', async () => {
    renderCamera();
    expect(screen.getByRole('dialog', { name: 'Aparat' })).toBeInTheDocument();
    expect(screen.getByText('Uruchamianie aparatu…')).toBeInTheDocument();
    expect(shutter()).toBeDisabled();
    await live();
    expect(screen.getByRole('status')).toHaveTextContent('Zrobiono: 0 z 10');
    expect(screen.getByRole('button', { name: 'Gotowe (0)' })).toBeDisabled();
  });

  it('every shot is a full-size still, counted, and the last one is shown as a thumbnail', async () => {
    renderCamera();
    await live();
    await shoot(2);
    expect(fake.takePhoto).toHaveBeenCalledWith({ imageWidth: 4624, imageHeight: 3472 });
    expect(screen.getByRole('status')).toHaveTextContent('Zrobiono: 2 z 10');
    expect(screen.getByRole('img', { name: 'Ostatnie zdjęcie' })).toHaveAttribute('src', 'blob:shot');
    expect(screen.getByRole('button', { name: 'Gotowe (2)' })).toBeEnabled();
  });

  it('"Gotowe" hands the files over in order, once, and releases the camera', async () => {
    const { onDone } = renderCamera();
    await live();
    await shoot(3);
    fireEvent.click(screen.getByRole('button', { name: 'Gotowe (3)' }));
    expect(onDone).toHaveBeenCalledTimes(1);
    const files = onDone.mock.calls[0][0] as File[];
    expect(files.map((f) => f.name.replace(/^kamera-\d{8}-\d{6}-/, ''))).toEqual(['1.jpg', '2.jpg', '3.jpg']);
    expect(files.every((f) => f.type === 'image/jpeg' && f.size > 0)).toBe(true);
    expect(fake.tracks[0].stop).toHaveBeenCalled();
  });

  it('stops at ten shots and says so', async () => {
    renderCamera();
    await live();
    await shoot(10);
    expect(shutter()).toBeDisabled();
    expect(screen.getByText(/Osiągnięto limit 10 zdjęć/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Gotowe (10)' })).toBeEnabled();
  });

  it('a failed shot is reported, does not count, and the next one works', async () => {
    renderCamera();
    await live();
    const working = fake.takePhoto.getMockImplementation();
    fake.takePhoto.mockRejectedValue(new DOMException('x', 'OperationError')); // every size fails
    fireEvent.click(shutter());
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Nie udało się zrobić zdjęcia.')); // the "saving" note is an alert too
    expect(screen.getByRole('status')).toHaveTextContent('Zrobiono: 0 z 10');
    fake.takePhoto.mockImplementation(working as NonNullable<typeof working>);
    await shoot();
    expect(screen.getByRole('status')).toHaveTextContent('Zrobiono: 1 z 10');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows a flash for every shot', async () => {
    renderCamera();
    await live();
    fireEvent.click(shutter());
    expect(await screen.findByTestId('camera-flash')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('camera-flash')).toBeNull());
  });
});

describe('CameraCapture — closing', () => {
  it('closes at once when nothing was taken', async () => {
    const { onCancel } = renderCamera();
    await live();
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij aparat' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(fake.tracks[0].stop).toHaveBeenCalled();
  });

  it('asks before throwing shots away; "back to the camera" keeps them', async () => {
    const { onCancel, onDone } = renderCamera();
    await live();
    await shoot(2);
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij aparat' }));
    const ask = screen.getByRole('alertdialog', { name: 'Odrzucić zrobione zdjęcia?' });
    expect(ask).toHaveTextContent('Zrobiono 2 zdjęć');
    fireEvent.click(within(ask).getByRole('button', { name: 'Wróć do aparatu' }));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(onCancel).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent('Zrobiono: 2 z 10');
    expect(onDone).not.toHaveBeenCalled();
  });

  it('discarding really closes, hands nothing over and releases the camera', async () => {
    const { onCancel, onDone } = renderCamera();
    await live();
    await shoot();
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij aparat' }));
    fireEvent.click(screen.getByRole('button', { name: 'Odrzuć' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onDone).not.toHaveBeenCalled();
    expect(fake.tracks[0].stop).toHaveBeenCalled();
  });

  it('the Telegram BackButton goes through the photo back registry: close, ask, then back to the camera', async () => {
    let closeTop = () => false;
    const { onCancel } = renderCamera({ onBackProbe: (fn) => (closeTop = fn) });
    await live();
    await shoot();
    act(() => void closeTop());
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    act(() => void closeTop()); // a second press while the question is open: back to the camera
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('BackButton with no shots closes the camera', async () => {
    let closeTop = () => false;
    const { onCancel } = renderCamera({ onBackProbe: (fn) => (closeTop = fn) });
    await live();
    act(() => void closeTop());
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('releases the camera when it is unmounted while live', async () => {
    const { unmount } = renderCamera();
    await live();
    unmount();
    expect(fake.tracks[0].stop).toHaveBeenCalled();
  });
});

describe('CameraCapture — when the camera cannot be used', () => {
  it('permission denied: explains, offers the phone picker (not a retry), and tells the parent', async () => {
    fake.getUserMedia.mockRejectedValue({ name: 'NotAllowedError' });
    const { onUseNativePicker, onCameraFailed } = renderCamera();
    expect(await screen.findByRole('heading', { name: 'Aparat jest niedostępny' })).toBeInTheDocument();
    expect(screen.getByText(/Brak zgody na aparat/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Uruchom aparat ponownie' })).toBeNull();
    expect(onCameraFailed).toHaveBeenCalledWith('denied');
    expect(shutter()).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Wybierz zdjęcie z telefonu' }));
    expect(onUseNativePicker).toHaveBeenCalledTimes(1);
  });

  it('a busy camera can be retried and then works', async () => {
    fake.getUserMedia.mockRejectedValueOnce({ name: 'NotReadableError' });
    renderCamera();
    expect(await screen.findByText(/Aparat jest zajęty/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Uruchom aparat ponownie' }));
    await live();
    expect(screen.queryByRole('heading', { name: 'Aparat jest niedostępny' })).toBeNull();
  });

  it('a missing camera and an unknown failure have their own texts', async () => {
    fake.getUserMedia.mockRejectedValueOnce({ name: 'NotFoundError' });
    const first = renderCamera();
    expect(await screen.findByText('Nie znaleziono aparatu. Wybierz zdjęcie z telefonu.')).toBeInTheDocument();
    first.unmount();
    fake.getUserMedia.mockRejectedValueOnce({ name: 'WeirdError' });
    renderCamera();
    expect(await screen.findByText('Nie udało się uruchomić aparatu. Wybierz zdjęcie z telefonu.')).toBeInTheDocument();
  });

  it('shots taken before a failure can still be handed over', async () => {
    const { onDone } = renderCamera();
    await live();
    await shoot();
    fireEvent.click(screen.getByRole('button', { name: 'Gotowe (1)' }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});

describe('CameraCapture — host events', () => {
  it('the torch button exists only when the camera has a torch and switches it', async () => {
    renderCamera();
    await live();
    fireEvent.click(screen.getByRole('button', { name: 'Włącz latarkę' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Wyłącz latarkę' })).toHaveAttribute('aria-pressed', 'true'));
    expect(fake.tracks[0].applyConstraints).toHaveBeenCalledWith({ advanced: [{ torch: true }] });
  });

  it('no torch button on a camera without a torch', async () => {
    fake = installFakeCamera({ torch: false });
    renderCamera();
    await live();
    expect(screen.queryByRole('button', { name: /latarkę/ })).toBeNull();
  });

  it('a torch the host refuses is reported', async () => {
    renderCamera();
    await live();
    fake.tracks[0].applyConstraints.mockRejectedValue(new DOMException('x', 'NotSupportedError'));
    fireEvent.click(screen.getByRole('button', { name: 'Włącz latarkę' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się przełączyć latarki.');
  });

  it('restarts the camera when the host stops it, and keeps the shots', async () => {
    renderCamera();
    await live();
    await shoot();
    act(() => fake.tracks[0].fire('ended'));
    await waitFor(() => expect(fake.getUserMedia).toHaveBeenCalledTimes(2));
    await live();
    expect(screen.getByRole('status')).toHaveTextContent('Zrobiono: 1 z 10');
  });

  it('releases the camera in the background and starts it again on return, shots kept', async () => {
    renderCamera();
    await live();
    await shoot();
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    act(() => void document.dispatchEvent(new Event('visibilitychange')));
    expect(fake.tracks[0].stop).toHaveBeenCalled();
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    act(() => void document.dispatchEvent(new Event('visibilitychange')));
    await waitFor(() => expect(fake.getUserMedia).toHaveBeenCalledTimes(2));
    await live();
    expect(screen.getByRole('status')).toHaveTextContent('Zrobiono: 1 z 10');
  });
});

describe('CameraCapture — language and mobile rules', () => {
  it('is localized in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderCamera();
    expect(screen.getByRole('dialog', { name: 'Камера' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Сделать фото' })).toBeEnabled());
    expect(screen.getByRole('button', { name: 'Готово (0)' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Снято: 0 из 10');
  });

  it('is full screen above the viewer, with thumb-sized controls and a big shutter', async () => {
    renderCamera();
    await live();
    const dialog = screen.getByRole('dialog', { name: 'Aparat' });
    expect(dialog).toHaveClass('fixed', 'inset-0', 'z-[70]');
    expect(dialog.parentElement).toBe(document.body); // a portal: no clipped or offset ancestors
    expect(screen.getByRole('button', { name: 'Zamknij aparat' })).toHaveClass('min-h-11', 'min-w-11');
    expect(screen.getByRole('button', { name: 'Gotowe (0)' })).toHaveClass('min-h-11', 'min-w-0', 'break-words');
    expect(shutter()).toHaveClass('h-[72px]', 'w-[72px]');
  });
});

// ---- 14E.10 follow-up: digital zoom (the phone reports no hardware zoom) and the first-shot size hint

function touch(target: Element, type: 'pointerdown' | 'pointermove' | 'pointerup', pointerId: number, x: number, y = 0) {
  const event = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y }); // jsdom has no PointerEvent
  Object.defineProperty(event, 'pointerId', { value: pointerId });
  fireEvent(target, event);
}
const preview = () => screen.getByLabelText('camera-preview');
const scaleOf = () => /scale\(([\d.]+)\)/.exec(preview().getAttribute('style') ?? '')?.[1];

describe('CameraCapture — digital zoom', () => {
  it('starts at 1x, steps 1x → 2x → 3x → 1x on the pill and scales the preview around its centre', async () => {
    renderCamera();
    await live();
    const pill = () => screen.getByRole('button', { name: /^Powiększenie/ });
    expect(pill()).toHaveTextContent('1×');
    expect(scaleOf()).toBe('1');
    fireEvent.click(pill());
    expect(pill()).toHaveTextContent('2×');
    expect(scaleOf()).toBe('2');
    fireEvent.click(pill());
    expect(pill()).toHaveTextContent('3×');
    fireEvent.click(pill());
    expect(pill()).toHaveTextContent('1×');
    expect(preview().getAttribute('style')).toContain('transform-origin: center');
    expect(pill().className).toContain('min-h-11');
  });

  it('two fingers zoom proportionally to the spread, within 1x–3x; one finger does nothing', async () => {
    renderCamera();
    await live();
    const area = screen.getByTestId('camera-viewfinder');
    touch(area, 'pointerdown', 1, 100);
    touch(area, 'pointermove', 1, 300);
    expect(scaleOf()).toBe('1');
    touch(area, 'pointermove', 1, 100);
    touch(area, 'pointerdown', 2, 200);
    touch(area, 'pointermove', 2, 300); // spread 100 → 200: twice as far apart
    expect(scaleOf()).toBe('2');
    touch(area, 'pointermove', 2, 900); // far beyond: clamped to the maximum
    expect(scaleOf()).toBe('3');
    touch(area, 'pointermove', 2, 150); // pinch in below 1x: clamped
    expect(scaleOf()).toBe('1');
    expect(area.style.touchAction).toBe('none');
  });

  it('a second pinch starts from the zoom the first one left', async () => {
    renderCamera();
    await live();
    const area = screen.getByTestId('camera-viewfinder');
    touch(area, 'pointerdown', 1, 100);
    touch(area, 'pointerdown', 2, 200);
    touch(area, 'pointermove', 2, 300);
    expect(scaleOf()).toBe('2');
    touch(area, 'pointerup', 2, 300);
    touch(area, 'pointerup', 1, 100);
    touch(area, 'pointerdown', 3, 100);
    touch(area, 'pointerdown', 4, 150);
    touch(area, 'pointermove', 4, 175); // 50 → 75: ×1.5 on top of 2x
    expect(scaleOf()).toBe('3');
  });

  it('a zoomed shot is the centre crop of the 4:3 still, and the zoom stays for the next shot of the series', async () => {
    const drawImage = vi.fn();
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 1440, height: 1920, close: vi.fn() })));
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((cb) => cb(new Blob(['zoomed-jpeg'], { type: 'image/jpeg' })));
    const { onDone } = renderCamera();
    await live();
    fireEvent.click(screen.getByRole('button', { name: /^Powiększenie/ }));
    await shoot(2);
    expect(drawImage).toHaveBeenCalledTimes(2);
    expect(drawImage).toHaveBeenLastCalledWith(expect.anything(), 360, 480, 720, 960, 0, 0, 720, 960);
    expect(screen.getByRole('button', { name: /^Powiększenie/ })).toHaveTextContent('2×');
    fireEvent.click(screen.getByRole('button', { name: /^Gotowe/ }));
    const files = onDone.mock.calls[0][0] as File[];
    expect(files.map((f) => f.size)).toEqual(['zoomed-jpeg'.length, 'zoomed-jpeg'.length]);
  });

  it('an unzoomed shot is not re-encoded', async () => {
    const createImageBitmap = vi.fn();
    vi.stubGlobal('createImageBitmap', createImageBitmap);
    renderCamera();
    await live();
    await shoot();
    expect(createImageBitmap).not.toHaveBeenCalled();
  });

  it('a zoomed shot that cannot be cropped is reported as a failed shot, not saved unzoomed', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn(async () => { throw new DOMException('no', 'InvalidStateError'); }));
    renderCamera();
    await live();
    fireEvent.click(screen.getByRole('button', { name: /^Powiększenie/ }));
    fireEvent.click(shutter());
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Nie udało się zrobić zdjęcia.')); // the "saving" note is an alert too
    expect(counted()).toBe(0);
  });
});

describe('CameraCapture — the first shot may take longer', () => {
  it('says that the 4:3 format is being searched when a shot takes more than a moment, and clears the hint afterwards', async () => {
    renderCamera();
    await live();
    vi.useFakeTimers();
    try {
      let release: (blob: Blob) => void = () => undefined;
      fake.takePhoto.mockImplementationOnce(() => new Promise<Blob>((resolve) => { release = resolve; }));
      fireEvent.click(shutter());
      await act(async () => { vi.advanceTimersByTime(500); });
      expect(screen.getByRole('alert')).toHaveTextContent('Zapisywanie zdjęcia…');
      await act(async () => { vi.advanceTimersByTime(1500); });
      expect(screen.getByRole('alert')).toHaveTextContent('Pierwsze zdjęcie trwa dłużej: dobieram format 4:3…');
      await act(async () => {
        release(new Blob(['x'], { type: 'image/jpeg' }));
        await vi.advanceTimersByTimeAsync(100); // the size check reads the photo through timers that are faked here
      });
    } finally {
      vi.useRealTimers();
    }
    await waitFor(() => expect(counted()).toBe(1));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('does not show the hint after a quick shot is finished', async () => {
    renderCamera();
    await live();
    await shoot();
    vi.useFakeTimers();
    try {
      await act(async () => { vi.advanceTimersByTime(5000); });
    } finally {
      vi.useRealTimers();
    }
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
