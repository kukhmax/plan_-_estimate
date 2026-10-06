import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PhotoCounts } from '../types/photo';
import { makeItem } from '../test/photoFixtures';
import { EMPTY_LOCATIONS, PhotoLocationData, PhotoLocationLabels, loadPhotoLocations, resolveLocationSegments } from './photoLocations';

vi.mock('../api/rooms', () => ({ fetchRooms: vi.fn() }));
vi.mock('../api/surfaces', () => ({ fetchSurfaces: vi.fn() }));
vi.mock('../api/openings', () => ({ fetchOpenings: vi.fn() }));
import { fetchOpenings } from '../api/openings';
import { fetchRooms } from '../api/rooms';
import { fetchSurfaces } from '../api/surfaces';

const counts = (over: Partial<PhotoCounts> = {}): PhotoCounts => ({ project: 0, rooms: {}, surfaces: {}, openings: {}, ...over });
const room = (id: string, name: string) => ({ id, name }) as never;
const surface = (id: string, roomId: string, name: string, type = 'WALL') => ({ id, room_id: roomId, name, surface_type: type }) as never;
const opening = (id: string, type: string, name: string | null) => ({ id, opening_type: type, name }) as never;

const PL: PhotoLocationLabels = { wall: 'Ściana', floor: 'Podłoga', ceiling: 'Sufit', door: 'Drzwi', window: 'Okno', other: 'Inny' };
const RU: PhotoLocationLabels = { wall: 'Стена', floor: 'Пол', ceiling: 'Потолок', door: 'Дверь', window: 'Окно', other: 'Другое' };

beforeEach(() => {
  vi.mocked(fetchRooms).mockReset().mockResolvedValue({ items: [room('r1', 'Salon'), room('r2', 'Kuchnia')], total: 2 } as never);
  vi.mocked(fetchSurfaces).mockReset().mockImplementation(async (_p, roomId) => ({
    items: roomId === 'r1' ? [surface('s1', 'r1', 'Ściana 1'), surface('s2', 'r1', 'Sufit', 'CEILING')] : [surface('s3', 'r2', 'Wall 2')],
    total: 0,
  }) as never);
  vi.mocked(fetchOpenings).mockReset().mockImplementation(async (_p, _r, surfaceId) => ({
    items: surfaceId === 's1' ? [opening('o1', 'DOOR', 'balkonowe')] : [],
    total: 0,
  }) as never);
});

describe('loadPhotoLocations — loads only as deep as the photos need', () => {
  it('rooms only when nothing but rooms / the object itself carry photos', async () => {
    const data = await loadPhotoLocations('p', counts({ rooms: { r1: 1 } }));
    expect(fetchRooms).toHaveBeenCalledWith('p', true);
    expect(fetchSurfaces).not.toHaveBeenCalled();
    expect(fetchOpenings).not.toHaveBeenCalled();
    expect(data.rooms).toEqual({ r1: 'Salon', r2: 'Kuchnia' });
    expect(data.complete).toBe(true);
  });

  it('adds the surfaces of every room (archived included) when a surface has photos', async () => {
    const data = await loadPhotoLocations('p', counts({ surfaces: { s1: 2 } }));
    expect(fetchSurfaces).toHaveBeenCalledTimes(2);
    expect(vi.mocked(fetchSurfaces).mock.calls.every((call) => call[2] === true)).toBe(true);
    expect(data.surfaces.s1).toEqual({ roomId: 'r1', name: 'Ściana 1', surfaceType: 'WALL' });
    expect(fetchOpenings).not.toHaveBeenCalled();
  });

  it('adds openings — of WALLS only — when an opening has photos', async () => {
    const data = await loadPhotoLocations('p', counts({ openings: { o1: 1 } }));
    expect(fetchOpenings).toHaveBeenCalledTimes(2); // s1 and s3 are walls, the ceiling s2 is not asked
    expect(vi.mocked(fetchOpenings).mock.calls.map((call) => call[2]).sort()).toEqual(['s1', 's3']);
    expect(data.openings.o1).toEqual({ surfaceId: 's1', roomId: 'r1', type: 'DOOR', name: 'balkonowe' });
  });

  it('limits the opening requests running at once', async () => {
    vi.mocked(fetchRooms).mockResolvedValue({ items: [room('r1', 'A')], total: 1 } as never);
    vi.mocked(fetchSurfaces).mockResolvedValue({
      items: Array.from({ length: 15 }, (_, i) => surface(`w${i}`, 'r1', `Ściana ${i + 1}`)),
      total: 15,
    } as never);
    let running = 0;
    let peak = 0;
    vi.mocked(fetchOpenings).mockImplementation(async () => {
      running += 1;
      peak = Math.max(peak, running);
      await new Promise((resolve) => setTimeout(resolve, 1));
      running -= 1;
      return { items: [], total: 0 } as never;
    });
    await loadPhotoLocations('p', counts({ openings: { x: 1 } }));
    expect(fetchOpenings).toHaveBeenCalledTimes(15);
    expect(peak).toBeLessThanOrEqual(6);
  });

  it('degrades instead of failing: a failed room list gives empty names, a failed surface list keeps the rest', async () => {
    vi.mocked(fetchRooms).mockRejectedValueOnce(new Error('offline'));
    expect(await loadPhotoLocations('p', counts({ surfaces: { s1: 1 } }))).toEqual({ rooms: {}, surfaces: {}, openings: {}, complete: false });

    vi.mocked(fetchSurfaces).mockImplementation(async (_p, roomId) => {
      if (roomId === 'r1') throw new Error('offline');
      return { items: [surface('s3', 'r2', 'Wall 2')], total: 1 } as never;
    });
    const partial = await loadPhotoLocations('p', counts({ surfaces: { s3: 1 } }));
    expect(partial.complete).toBe(false);
    expect(partial.rooms.r1).toBe('Salon');
    expect(Object.keys(partial.surfaces)).toEqual(['s3']);
  });
});

describe('resolveLocationSegments', () => {
  const data: PhotoLocationData = {
    rooms: { r1: 'Salon' },
    surfaces: {
      s1: { roomId: 'r1', name: 'Ściana 1', surfaceType: 'WALL' },
      s2: { roomId: 'r1', name: 'Sufit', surfaceType: 'CEILING' },
    },
    openings: { o1: { surfaceId: 's1', roomId: 'r1', type: 'WINDOW', name: null } },
    complete: true,
  };
  const at = (context: string, ids: { room_id?: string; surface_id?: string; opening_id?: string }) =>
    makeItem({ attachment: { context, room_id: ids.room_id ?? null, surface_id: ids.surface_id ?? null, opening_id: ids.opening_id ?? null } }).attachment;

  it('builds room → surface → opening, with the generated wall numbering in the current language', () => {
    expect(resolveLocationSegments(at('ROOM', { room_id: 'r1' }), data, PL)).toEqual(['Salon']);
    expect(resolveLocationSegments(at('SURFACE', { surface_id: 's1' }), data, PL)).toEqual(['Salon', 'Ściana 1']);
    expect(resolveLocationSegments(at('SURFACE', { surface_id: 's1' }), data, RU)).toEqual(['Salon', 'Стена 1']);
    expect(resolveLocationSegments(at('SURFACE', { surface_id: 's2' }), data, RU)).toEqual(['Salon', 'Потолок']);
    expect(resolveLocationSegments(at('OPENING', { opening_id: 'o1' }), data, PL)).toEqual(['Salon', 'Ściana 1', 'Okno']);
  });

  it('shows the opening name when it has one', () => {
    const named = { ...data, openings: { o1: { surfaceId: 's1', roomId: 'r1', type: 'DOOR' as const, name: 'balkonowe' } } };
    expect(resolveLocationSegments(at('OPENING', { opening_id: 'o1' }), named, PL)[2]).toBe('Drzwi (balkonowe)');
  });

  it('leaves the object without segments and unknown targets undefined', () => {
    expect(resolveLocationSegments(at('PROJECT', {}), data, PL)).toEqual([]);
    expect(resolveLocationSegments(at('SURFACE', { surface_id: 'gone' }), data, PL)).toEqual([undefined, undefined]);
    expect(resolveLocationSegments(at('OPENING', { opening_id: 'gone' }), EMPTY_LOCATIONS, PL)).toEqual([undefined, undefined, undefined]);
    expect(resolveLocationSegments(at('ROOM', { room_id: 'gone' }), data, PL)).toEqual([undefined]);
  });
});
