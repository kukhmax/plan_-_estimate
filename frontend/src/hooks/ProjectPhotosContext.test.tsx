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

const COUNTS: PhotoCounts = { project: 1, rooms: { r1: 2 }, surfaces: { s1: 3 }, openings: {}, room_totals: { r1: 5 } };
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

  it('applies a correction at once and then takes the server numbers as the truth', async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
    let release: (value: PhotoCounts) => void = () => undefined;
    vi.mocked(fetchPhotoCounts).mockReturnValueOnce(new Promise((resolve) => (release = resolve)));
    act(() => result.current?.adjust('ROOM', 'r1', -1));
    expect(photoCountFor(result.current!.counts, 'ROOM', 'r1')).toBe(1); // at once
    expect(result.current!.counts.room_totals.r1).toBe(4);
    expect(fetchPhotoCounts).toHaveBeenCalledTimes(2); // the confirmation was requested

    await act(async () => release({ ...COUNTS, rooms: { r1: 7 }, room_totals: { r1: 9 } }));
    expect(photoCountFor(result.current!.counts, 'ROOM', 'r1')).toBe(7); // the server wins
    expect(result.current!.counts.room_totals.r1).toBe(9);
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

    /** The confirming refetch stays pending, so the immediate (optimistic) numbers can be read. */
    const holdConfirmation = () => vi.mocked(fetchPhotoCounts).mockImplementation(() => new Promise(() => undefined));

    it('+1 for the surface and for its room when the upload carries its room, with no section open', async () => {
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      holdConfirmation();
      await finishUpload({ projectId: 'p1', context: 'SURFACE', surfaceId: 's1', roomId: 'r1' });
      expect(photoCountFor(result.current!.counts, 'SURFACE', 's1')).toBe(4);
      expect(result.current!.counts.room_totals.r1).toBe(6);
      expect(result.current!.counts.project).toBe(1);
    });

    it('then confirms with the server, whose numbers replace the optimistic ones', async () => {
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      vi.mocked(fetchPhotoCounts).mockResolvedValue({ ...COUNTS, surfaces: { s1: 4 }, room_totals: { r1: 6 } });
      await finishUpload({ projectId: 'p1', context: 'SURFACE', surfaceId: 's1', roomId: 'r1' });
      await waitFor(() => expect(fetchPhotoCounts).toHaveBeenCalledTimes(2));
      await waitFor(() => expect(result.current!.counts.room_totals.r1).toBe(6));
    });

    it('a surface upload without a known room moves only the surface; the refetch brings the room total', async () => {
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      holdConfirmation();
      await finishUpload({ projectId: 'p1', context: 'SURFACE', surfaceId: 's1' });
      expect(photoCountFor(result.current!.counts, 'SURFACE', 's1')).toBe(4);
      expect(result.current!.counts.room_totals.r1).toBe(5);
      expect(fetchPhotoCounts).toHaveBeenCalledTimes(2);
    });

    it('+1 for the object itself', async () => {
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      holdConfirmation();
      await finishUpload({ projectId: 'p1', context: 'PROJECT' });
      expect(result.current!.counts.project).toBe(2);
    });

    it('ignores an upload that belongs to another object', async () => {
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      holdConfirmation();
      await finishUpload({ projectId: 'other', context: 'SURFACE', surfaceId: 's1', roomId: 'r1' });
      expect(photoCountFor(result.current!.counts, 'SURFACE', 's1')).toBe(3);
      expect(fetchPhotoCounts).toHaveBeenCalledTimes(1);
    });

    it('refetches the counts when an upload found its target gone', async () => {
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      const queue = getPhotoUploadQueue();
      let reject: (error: unknown) => void = () => undefined;
      vi.mocked(uploadPhoto).mockImplementation(() => new Promise((_, r) => (reject = r)));
      await act(async () => {
        queue.enqueue([file()], { projectId: 'p1', context: 'SURFACE', surfaceId: 's1', roomId: 'r1' }, 'GALLERY');
      });
      const { PhotoUploadError } = await import('../api/photos');
      await act(async () => reject(new PhotoUploadError('nf', 404, 'SURFACE_NOT_FOUND')));
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
      expect(loadPhotoLocations).toHaveBeenCalledWith('p1', COUNTS, undefined);
    });

    it('passes the counts known at that moment, and the room when only one room is wanted', async () => {
      vi.mocked(fetchPhotoCounts).mockResolvedValue({ ...COUNTS, openings: { o1: 1 } });
      vi.mocked(loadPhotoLocations).mockResolvedValue(data);
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts.openings).toEqual({ o1: 1 }));
      act(() => result.current?.ensureLocations('r1'));
      await waitFor(() => expect(loadPhotoLocations).toHaveBeenCalled());
      const [, passedCounts, passedRoom] = vi.mocked(loadPhotoLocations).mock.calls[0];
      expect(passedCounts.openings).toEqual({ o1: 1 });
      expect(passedRoom).toBe('r1');
    });

    it('ADDS the names of several loads: the room view and the object view can be open together', async () => {
      const roomPart = { rooms: { r1: 'Salon' }, surfaces: { s1: { roomId: 'r1', name: 'Ściana 1', surfaceType: 'WALL' as const } }, openings: {}, complete: true };
      const objectPart = { rooms: { r1: 'Salon', r2: 'Kuchnia' }, surfaces: { s9: { roomId: 'r2', name: 'Ściana 2', surfaceType: 'WALL' as const } }, openings: {}, complete: true };
      vi.mocked(loadPhotoLocations).mockResolvedValueOnce(roomPart).mockResolvedValueOnce(objectPart);
      const { result } = setup();
      await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
      act(() => result.current?.ensureLocations('r1'));
      act(() => result.current?.ensureLocations());
      const both = (surface: string) => result.current!.resolveLocation(attachment('SURFACE', { surface_id: surface }));
      await waitFor(() => expect(both('s9')).toBe('Kuchnia → Ściana 2'));
      expect(both('s1')).toBe('Salon → Ściana 1'); // the earlier load is not forgotten
    });
  });
});

describe('ProjectPhotosProvider — another object', () => {
  it('forgets expansions, counts and names, and ignores a late answer about the previous object', async () => {
    let project: string | null = 'p1';
    const wrapper = ({ children }: { children: ReactNode }) => (
      <I18nProvider>
        <ProjectPhotosProvider projectId={project} backRegistry={registry}>
          {children}
        </ProjectPhotosProvider>
      </I18nProvider>
    );
    let late: (value: { rooms: Record<string, string>; surfaces: Record<string, never>; openings: Record<string, never>; complete: boolean }) => void = () => undefined;
    vi.mocked(loadPhotoLocations).mockReturnValueOnce(new Promise((resolve) => (late = resolve as never)));
    const { result, rerender } = renderHook(() => useProjectPhotos(), { wrapper });
    await waitFor(() => expect(result.current?.counts).toEqual(COUNTS));
    act(() => result.current?.toggle(photoKey('ROOM', 'r1')));
    act(() => result.current?.ensureLocations());

    vi.mocked(fetchPhotoCounts).mockResolvedValue({ project: 0, rooms: {}, surfaces: {}, openings: {}, room_totals: {} });
    project = 'p2';
    rerender();
    await waitFor(() => expect(result.current?.counts.project).toBe(0));
    expect(result.current?.isExpanded(photoKey('ROOM', 'r1'))).toBe(false);

    await act(async () => late({ rooms: { r1: 'OldRoom' }, surfaces: {}, openings: {}, complete: true }));
    const room = makeItem({ attachment: { context: 'ROOM', room_id: 'r1' } }).attachment;
    expect(result.current!.resolveLocation(room)).toBe('—'); // the previous object's name did not leak in
  });
});
