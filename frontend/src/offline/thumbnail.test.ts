import { afterEach, describe, expect, it, vi } from 'vitest';
import { makeThumbnail } from './thumbnail';

describe('the small picture of a waiting photo (Stage 19E)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('is nothing where the browser cannot draw (no createImageBitmap), and never throws', async () => {
    expect(await makeThumbnail(new Blob(['x']))).toBeNull();
  });

  it('draws the photo no larger than 112 px on its longer side, as a small JPEG data URL', async () => {
    const close = vi.fn();
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 4000, height: 3000, close })));
    const drawn: Array<[number, number]> = [];
    const canvas = {
      width: 0,
      height: 0,
      getContext: () => ({ drawImage: (_b: unknown, _x: number, _y: number, w: number, h: number) => drawn.push([w, h]) }),
      toDataURL: vi.fn(() => 'data:image/jpeg;base64,/9j/'),
    };
    vi.spyOn(document, 'createElement').mockReturnValue(canvas as unknown as HTMLElement);

    expect(await makeThumbnail(new Blob(['x']))).toBe('data:image/jpeg;base64,/9j/');
    expect(drawn).toEqual([[112, 84]]);
    expect(canvas.toDataURL).toHaveBeenCalledWith('image/jpeg', 0.6);
    expect(close).toHaveBeenCalled(); // the picture in memory is let go
  });

  it('does not enlarge a small photo', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 60, height: 40, close: vi.fn() })));
    const drawn: Array<[number, number]> = [];
    const canvas = { width: 0, height: 0, getContext: () => ({ drawImage: (_b: unknown, _x: number, _y: number, w: number, h: number) => drawn.push([w, h]) }), toDataURL: () => 'data:image/jpeg;base64,AA' };
    vi.spyOn(document, 'createElement').mockReturnValue(canvas as unknown as HTMLElement);
    await makeThumbnail(new Blob(['x']));
    expect(drawn).toEqual([[60, 40]]);
  });

  it('is nothing when decoding fails or the canvas gives something else', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn(async () => { throw new Error('not an image'); }));
    expect(await makeThumbnail(new Blob(['x']))).toBeNull();

    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 10, height: 10, close: vi.fn() })));
    vi.spyOn(document, 'createElement').mockReturnValue({ width: 0, height: 0, getContext: () => ({ drawImage: () => {} }), toDataURL: () => 'data:,' } as unknown as HTMLElement);
    expect(await makeThumbnail(new Blob(['x']))).toBeNull();
  });
});
