import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { jpegFile, jpegWithExif } from '../test/jpegFixtures';
import { CAMERA_FRESH_WINDOW_MS, PHOTO_ACCEPT, PhotoPicker, isFreshCapture } from './PhotoPicker';

function renderPicker(onFiles = vi.fn(), disabled = false) {
  const view = render(
    <I18nProvider>
      <PhotoPicker onFiles={onFiles} disabled={disabled} />
    </I18nProvider>,
  );
  return { onFiles, ...view };
}

const camera = () => screen.getByTestId('photo-input-camera') as HTMLInputElement;
const gallery = () => screen.getByTestId('photo-input-gallery') as HTMLInputElement;
const file = (name: string) => new File(['x'], name, { type: 'image/jpeg' }); // no EXIF
const taken = (name: string, ageMs: number) => jpegFile(name, jpegWithExif({ original: new Date(Date.now() - ageMs) }));

describe('PhotoPicker', () => {
  beforeEach(() => localStorage.clear());

  it('offers two buttons, camera and gallery, in Polish', () => {
    renderPicker();
    expect(screen.getByRole('button', { name: 'Zrób zdjęcie' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Z galerii' })).toBeInTheDocument();
  });

  it('is localized in Russian', () => {
    localStorage.setItem('locale', 'ru');
    renderPicker();
    expect(screen.getByRole('button', { name: 'Сделать фото' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Из галереи' })).toBeInTheDocument();
  });

  it('camera input: images only, rear camera, single file; gallery input: same types, multi-select', () => {
    renderPicker();
    expect(camera()).toHaveAttribute('accept', PHOTO_ACCEPT);
    expect(PHOTO_ACCEPT).toBe('image/jpeg,image/png,image/webp'); // HEIC is not offered
    expect(camera()).toHaveAttribute('capture', 'environment');
    expect(camera().multiple).toBe(false);
    expect(gallery()).toHaveAttribute('accept', PHOTO_ACCEPT);
    expect(gallery().multiple).toBe(true);
    expect(gallery()).not.toHaveAttribute('capture');
  });

  it('opens the matching native picker when a button is tapped', () => {
    renderPicker();
    const cameraClick = vi.spyOn(camera(), 'click');
    const galleryClick = vi.spyOn(gallery(), 'click');
    fireEvent.click(screen.getByRole('button', { name: 'Zrób zdjęcie' }));
    expect(cameraClick).toHaveBeenCalledTimes(1);
    expect(galleryClick).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Z galerii' }));
    expect(galleryClick).toHaveBeenCalledTimes(1);
  });

  it('hands the picked files over with the declared source and resets the input', async () => {
    const { onFiles } = renderPicker();
    fireEvent.change(camera(), { target: { files: [taken('c.jpg', 20_000)] } });
    await waitFor(() => expect(onFiles).toHaveBeenCalledTimes(1));
    expect(onFiles).toHaveBeenLastCalledWith([expect.objectContaining({ name: 'c.jpg' })], 'CAMERA');
    fireEvent.change(gallery(), { target: { files: [file('g1.jpg'), file('g2.jpg')] } });
    await waitFor(() => expect(onFiles).toHaveBeenCalledTimes(2));
    expect(onFiles).toHaveBeenLastCalledWith(
      [expect.objectContaining({ name: 'g1.jpg' }), expect.objectContaining({ name: 'g2.jpg' })],
      'GALLERY',
    );
    expect(camera().value).toBe('');
  });

  describe('declared source of the camera button (hosts that ignore `capture`)', () => {
    it('a photo taken a moment ago (EXIF) stays CAMERA', async () => {
      const { onFiles } = renderPicker();
      fireEvent.change(camera(), { target: { files: [taken('new.jpg', 30_000)] } });
      await waitFor(() => expect(onFiles).toHaveBeenCalled());
      expect(onFiles).toHaveBeenLastCalledWith([expect.objectContaining({ name: 'new.jpg' })], 'CAMERA');
    });

    it('an old photo chosen through the camera button is declared GALLERY', async () => {
      const { onFiles } = renderPicker();
      fireEvent.change(camera(), { target: { files: [taken('old.jpg', 35 * 24 * 3_600_000)] } });
      await waitFor(() => expect(onFiles).toHaveBeenCalled());
      expect(onFiles).toHaveBeenLastCalledWith([expect.objectContaining({ name: 'old.jpg' })], 'GALLERY');
    });

    it('a file without EXIF (screenshot, download) is declared GALLERY even though the host copied it just now', async () => {
      const { onFiles } = renderPicker();
      const copied = new File(['x'], 'shot.jpg', { type: 'image/jpeg', lastModified: Date.now() });
      fireEvent.change(camera(), { target: { files: [copied, jpegFile('bare.jpg')] } });
      await waitFor(() => expect(onFiles).toHaveBeenCalled());
      expect(onFiles).toHaveBeenLastCalledWith(expect.any(Array), 'GALLERY');
    });

    it('every file must be fresh for CAMERA', async () => {
      const { onFiles } = renderPicker();
      fireEvent.change(camera(), { target: { files: [taken('a.jpg', 10_000), taken('b.jpg', 3_600_000)] } });
      await waitFor(() => expect(onFiles).toHaveBeenCalled());
      expect(onFiles).toHaveBeenLastCalledWith(expect.any(Array), 'GALLERY');
    });

    it('the gallery button is always GALLERY, even for a fresh photo', async () => {
      const { onFiles } = renderPicker();
      fireEvent.change(gallery(), { target: { files: [taken('fresh.jpg', 1_000)] } });
      await waitFor(() => expect(onFiles).toHaveBeenCalled());
      expect(onFiles).toHaveBeenLastCalledWith([expect.objectContaining({ name: 'fresh.jpg' })], 'GALLERY');
    });

    it('the window is five minutes and tolerates a small clock skew either way', () => {
      expect(CAMERA_FRESH_WINDOW_MS).toBe(300_000);
      const now = 1_000_000_000_000;
      expect(isFreshCapture(new Date(now - 299_000), now)).toBe(true);
      expect(isFreshCapture(new Date(now + 60_000), now)).toBe(true);
      expect(isFreshCapture(new Date(now - 301_000), now)).toBe(false);
      expect(isFreshCapture(new Date(now + 301_000), now)).toBe(false);
      expect(isFreshCapture(null, now)).toBe(false);
    });
  });

  it('clears the input after a pick so the same photo can be chosen again', () => {
    renderPicker();
    for (const input of [camera(), gallery()]) {
      const assigned: string[] = [];
      Object.defineProperty(input, 'value', {
        configurable: true,
        get: () => '',
        set: (value: string) => {
          assigned.push(value);
        },
      });
      fireEvent.change(input, { target: { files: [file('same.jpg')] } });
      expect(assigned).toEqual(['']);
    }
  });

  it('ignores a cancelled picker (no files)', () => {
    const { onFiles } = renderPicker();
    fireEvent.change(camera(), { target: { files: [] } });
    expect(onFiles).not.toHaveBeenCalled();
  });

  it('disables both buttons when asked', () => {
    renderPicker(vi.fn(), true);
    expect(screen.getByRole('button', { name: 'Zrób zdjęcie' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Z galerii' })).toBeDisabled();
  });

  it('mobile layout: stacked at 320 px, side by side from 360 px, full-width ≥ 44 px targets, long labels wrap', () => {
    const { container } = renderPicker();
    expect(container.firstElementChild).toHaveClass('grid', 'grid-cols-1', 'min-[360px]:grid-cols-2');
    for (const name of ['Zrób zdjęcie', 'Z galerii']) {
      const button = screen.getByRole('button', { name });
      expect(button).toHaveClass('min-h-11', 'w-full', 'min-w-0');
      expect(button.querySelector('span')).toHaveClass('break-words');
    }
    expect(container.innerHTML).not.toMatch(/\bw-\[\d+px\]|\bwidth:\s*\d+px/);
  });

  it('keeps the hidden inputs out of the tab order', () => {
    renderPicker();
    expect(camera()).toHaveAttribute('tabindex', '-1');
    expect(camera()).toHaveClass('hidden');
  });
});
