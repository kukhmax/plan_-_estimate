import { act, renderHook, waitFor } from '@testing-library/react';
import { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PhotoBackRegistry } from './PhotoBackContext';
import { I18nProvider } from './useI18n';
import { ProjectPhotosProvider, photoKey, useProjectPhotos } from './ProjectPhotosContext';
import { getPhotoUploadQueue, resetPhotoUploadQueue } from './usePhotoUploadQueue';
import { photoCountFor } from './usePhotoCounts';
import { PhotoCounts } from '../types/photo';
import { makeItem } from '../test/photoFixtures';

vi.mock('../api/photos', async () => {
  const actual = await vi.importActual<typeof import('../api/photos')>('../api/photos');
  return { ...actual, fetchPhotoCounts: vi.fn(), uploadPhoto: vi.fn(), fetchPhoto: vi.fn(), fetchPhotoStorage: vi.fn() };
});
vi.mock('../utils/photoLocations', async () => {
  const actual = await vi.importActual<typeof import('../utils/photoLocations')>('../utils/photoLocations');
  return { ...actual, loadPhotoLocations: vi.fn() };
});
import { fetchPhotoCounts, uploadPhoto } from '../api/photos';
import { loadPhotoLocations } from '../utils/photoLocations';

const COUNTS: PhotoCounts = { project: 1, rooms: { r1: 2 }, surfaces: { s1: 3 }, openings: {} };
const registry: PhotoBackRegistry = { register: () => () => undefined };

function setup(initial: string | null = 'p1') {
  const wrapper = ({ children, projectId }: { children: ReactNode; projectId?: string | null }) => (
    <I18nProvider>
      <ProjectPhotosProvider projectId={projectId === undefined ? initial : projectId} backRegistry={registry}>
        {children}
      </ProjectPhotosProvider>
    </I18nProvider>
  );
  return renderHook(() => useProjectPhotos(), {
    wrapper: ({ children }: { children: ReactNode }) => wrapper({ children }),
  });
}

const file = () => new File(['x'], 'a.jpg', { type: 'image/jpeg' });

beforeEach(() => {
  localStorage.clear();
  resetPhotoUploadQueue();
  vi.mocked(fetchPhotoCounts).mockReset().mockResolvedValue(COUNTS);
  vi.mocked(uploadPhoto).mockReset().mockImplementation(() => new Promise(() => undefined));
  vi.mocked(loadPhotoLocations).mockReset();
});
afterEach(() => resetPhotoUploadQueue());

describe('ProjectPhotosProvider', () => {
  it('provides nothing — and loads nothing — while no object is open', () => {
    const { result } = setup(null);
    expect(result.current).toBeNull();
    expect(fetchPhotoCounts).not.toHaveBeenCalled();
  });

  it('loads the counts of the open object once', async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
    expect(fetchPhotoCounts).toHaveBeenCalledTimes(1);
    expect(fetchPhotoCounts).toHaveBeenCalledWith('p1');
    expect(result.current?.projectId).toBe('p1');
  });

  it('toggles a section and refetches the counts only when it expands', async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
    const key = photoKey('ROOM', 'r1');
    expect(result.current?.isExpanded(key)).toBe(false);

    act(() => result.current?.toggle(key));
    expect(result.current?.isExpanded(key)).toBe(true);
    await waitFor(() => expect(fetchPhotoCounts).toHaveBeenCalledTimes(2));

    act(() => result.current?.toggle(key));
    expect(result.current?.isExpanded(key)).toBe(false);
    expect(fetchPhotoCounts).toHaveBeenCalledTimes(2);
  });

  it('keys sections by context and target', () => {
    expect(photoKey('PROJECT')).toBe('PROJECT:');
    expect(photoKey('ROOM', 'r1')).not.toBe(photoKey('SURFACE', 'r1'));
  });

  it('applies optimistic corrections', async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
    act(() => result.current?.adjust('ROOM', 'r1', -1));
    expect(photoCountFor(result.current!.counts, 'ROOM', 'r1')).toBe(1);
  });

  describe('counting finished uploads (once, by the host)', () => {
    async function finishUpload(target: Parameters<ReturnType<typeof getPhotoUploadQueue>['enqueue']>[1]) {
      const queue = getPhotoUploadQueue();
      let resolve: (value: never) => void = () => undefined;
      vi.mocked(uploadPhoto).mockImplementation(() => new Promise((r) => (resolve = r as never)));
      await act(async () => {
        queue.enqueue([file()], target, 'CAMERA');
      });
      const item = makeItem({ attachment: { context: target.context } });
      await act(async () =>
        resolve({ asset: item.asset, attachment: item.attachment, thumbnail_url: 't', display_url: 'd', urls_expire_at: 'x', storage: { state: 'OK' } } as never),
      );
    }

    it('+1 for the room the photo was uploaded to, with no section open', async () => {
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      await finishUpload({ projectId: 'p1', context: 'ROOM', roomId: 'r1' });
      expect(photoCountFor(result.current!.counts, 'ROOM', 'r1')).toBe(3);
      expect(result.current!.counts.project).toBe(1);
    });

    it('+1 for the object itself and for a surface / opening', async () => {
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      await finishUpload({ projectId: 'p1', context: 'PROJECT' });
      expect(result.current!.counts.project).toBe(2);
      await finishUpload({ projectId: 'p1', context: 'SURFACE', surfaceId: 's1' });
      expect(photoCountFor(result.current!.counts, 'SURFACE', 's1')).toBe(4);
      await finishUpload({ projectId: 'p1', context: 'OPENING', openingId: 'o9' });
      expect(photoCountFor(result.current!.counts, 'OPENING', 'o9')).toBe(1);
    });

    it('ignores an upload that belongs to another object', async () => {
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      await finishUpload({ projectId: 'other', context: 'ROOM', roomId: 'r1' });
      expect(photoCountFor(result.current!.counts, 'ROOM', 'r1')).toBe(2);
    });

    it('refetches the counts when an upload found its target gone', async () => {
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      const queue = getPhotoUploadQueue();
      let reject: (error: unknown) => void = () => undefined;
      vi.mocked(uploadPhoto).mockImplementation(() => new Promise((_, r) => (reject = r)));
      await act(async () => {
        queue.enqueue([file()], { projectId: 'p1', context: 'ROOM', roomId: 'r1' }, 'GALLERY');
      });
      const { PhotoUploadError } = await import('../api/photos');
      await act(async () => reject(new PhotoUploadError('nf', 404, 'ROOM_NOT_FOUND')));
      await waitFor(() => expect(fetchPhotoCounts).toHaveBeenCalledTimes(2));
    });
  });

  describe('location names for the project-wide list', () => {
    const data = {
      rooms: { r1: 'Salon' },
      surfaces: { s1: { roomId: 'r1', name: 'Ściana 1', surfaceType: 'WALL' as const } },
      openings: {},
      complete: true,
    };
    const attachment = (context: string, ids: Record<string, string | null>) =>
      makeItem({ attachment: { context, room_id: null, surface_id: null, opening_id: null, ...ids } }).attachment;

    it('shows dashes before the names are loaded and the path after', async () => {
      vi.mocked(loadPhotoLocations).mockResolvedValue(data);
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      const wall = attachment('SURFACE', { surface_id: 's1' });
      expect(result.current!.resolveLocation(wall)).toBe('— → —');
      expect(result.current!.resolveLocation(attachment('PROJECT', {}))).toBe('Obiekt');

      act(() => result.current?.ensureLocations());
      await waitFor(() => expect(result.current!.resolveLocation(wall)).toBe('Salon → Ściana 1'));
      expect(loadPhotoLocations).toHaveBeenCalledWith('p1', COUNTS);
    });

    it('uses the counts known at that moment to decide how deep to load', async () => {
      vi.mocked(loadPhotoLocations).mockResolvedValue(data);
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      act(() => result.current?.adjust('OPENING', 'o1', 1));
      act(() => result.current?.ensureLocations());
      await waitFor(() => expect(loadPhotoLocations).toHaveBeenCalled());
      expect(vi.mocked(loadPhotoLocations).mock.calls[0][1].openings).toEqual({ o1: 1 });
    });

    it('drops the answer of a load superseded by a newer one', async () => {
      let first: (value: typeof data) => void = () => undefined;
      vi.mocked(loadPhotoLocations)
        .mockReturnValueOnce(new Promise((resolve) => (first = resolve)))
        .mockResolvedValueOnce({ ...data, rooms: { r1: 'Nowy' } });
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      act(() => result.current?.ensureLocations());
      act(() => result.current?.ensureLocations());
      await waitFor(() => expect(result.current!.resolveLocation(attachment('ROOM', { room_id: 'r1' }))).toBe('Nowy'));
      await act(async () => first(data)); // the stale answer arrives last
      expect(result.current!.resolveLocation(attachment('ROOM', { room_id: 'r1' }))).toBe('Nowy');
    });
  });
});
