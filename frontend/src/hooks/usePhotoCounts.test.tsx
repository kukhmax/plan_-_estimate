import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PhotoCounts } from '../types/photo';
import {
  EMPTY_PHOTO_COUNTS,
  adjustPhotoCounts,
  photoCountFor,
  roomPhotoTotal,
  totalPhotoCount,
  usePhotoCounts,
} from './usePhotoCounts';

vi.mock('../api/photos', () => ({ fetchPhotoCounts: vi.fn() }));
import { fetchPhotoCounts } from '../api/photos';

const counts: PhotoCounts = {
  project: 2,
  rooms: { r1: 3 },
  surfaces: { s1: 1, s2: 4 },
  openings: { o1: 1 },
  room_totals: { r1: 3 + 1 + 4 + 1 },
  inspections: {}, findings: {}, lineages: {},
};

describe('photo count helpers', () => {
  it('reads the count of a target per context and zero when absent', () => {
    expect(photoCountFor(counts, 'PROJECT')).toBe(2);
    expect(photoCountFor(counts, 'ROOM', 'r1')).toBe(3);
    expect(photoCountFor(counts, 'SURFACE', 's2')).toBe(4);
    expect(photoCountFor(counts, 'OPENING', 'o1')).toBe(1);
    expect(photoCountFor(counts, 'ROOM', 'missing')).toBe(0);
    expect(photoCountFor(counts, 'ROOM')).toBe(0);
  });

  it('a room total spans its surfaces and openings and is zero for an unknown room', () => {
    expect(roomPhotoTotal(counts, 'r1')).toBe(9);
    expect(roomPhotoTotal(counts, 'nope')).toBe(0);
    expect(roomPhotoTotal({ ...counts, room_totals: undefined } as unknown as PhotoCounts, 'r1')).toBe(0);
  });

  it('keeps a room total in step when the owning room is known', () => {
    const afterSurface = adjustPhotoCounts(counts, 'SURFACE', 's1', 1, 'r1');
    expect(afterSurface.surfaces.s1).toBe(2);
    expect(afterSurface.room_totals.r1).toBe(10);
    expect(adjustPhotoCounts(counts, 'OPENING', 'o1', -1, 'r1').room_totals.r1).toBe(8);
    expect(adjustPhotoCounts(counts, 'ROOM', 'r1', 1).room_totals.r1).toBe(10); // a room photo knows its room by itself
    // unknown room: only the leaf moves, the host refetches for the truth
    expect(adjustPhotoCounts(counts, 'SURFACE', 's1', 1).room_totals).toEqual(counts.room_totals);
    expect(adjustPhotoCounts(counts, 'SURFACE', 's1', -99, 'r1').room_totals.r1).toBeUndefined();
  });

  it('totals every visible attachment of the object (the project-wide list, C-3)', () => {
    expect(totalPhotoCount(counts)).toBe(2 + 3 + 1 + 4 + 1);
    expect(totalPhotoCount(EMPTY_PHOTO_COUNTS)).toBe(0);
  });

  it('adjusts optimistically without mutating, never below zero, dropping emptied targets', () => {
    const snapshot = JSON.stringify(counts);
    expect(adjustPhotoCounts(counts, 'ROOM', 'r1', 2).rooms).toEqual({ r1: 5 });
    expect(adjustPhotoCounts(counts, 'ROOM', 'new', 1).rooms).toEqual({ r1: 3, new: 1 });
    expect(adjustPhotoCounts(counts, 'SURFACE', 's1', -1).surfaces).toEqual({ s2: 4 });
    expect(adjustPhotoCounts(counts, 'SURFACE', 's1', -9).surfaces).toEqual({ s2: 4 });
    expect(adjustPhotoCounts(counts, 'PROJECT', undefined, -5).project).toBe(0);
    expect(adjustPhotoCounts(counts, 'OPENING', undefined, 1)).toBe(counts);
    expect(JSON.stringify(counts)).toBe(snapshot);
  });
});

describe('usePhotoCounts', () => {
  beforeEach(() => {
    vi.mocked(fetchPhotoCounts).mockReset();
  });

  it('fetches the counts once for the project', async () => {
    vi.mocked(fetchPhotoCounts).mockResolvedValue(counts);
    const { result } = renderHook(() => usePhotoCounts('p1'));
    expect(result.current.status).toBe('loading');
    expect(result.current.counts).toEqual(EMPTY_PHOTO_COUNTS);
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.counts).toEqual(counts);
    expect(fetchPhotoCounts).toHaveBeenCalledTimes(1);
    expect(fetchPhotoCounts).toHaveBeenCalledWith('p1');
  });

  it('applies optimistic adjustments and replaces them with the server truth on refresh', async () => {
    vi.mocked(fetchPhotoCounts).mockResolvedValueOnce(counts);
    const { result } = renderHook(() => usePhotoCounts('p1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));

    act(() => result.current.adjust('ROOM', 'r1', 1));
    expect(photoCountFor(result.current.counts, 'ROOM', 'r1')).toBe(4);

    vi.mocked(fetchPhotoCounts).mockResolvedValueOnce({ ...counts, rooms: { r1: 7 } });
    await act(() => result.current.refresh());
    expect(photoCountFor(result.current.counts, 'ROOM', 'r1')).toBe(7);
  });

  it('reports an error without losing the last counts', async () => {
    vi.mocked(fetchPhotoCounts).mockResolvedValueOnce(counts);
    const { result } = renderHook(() => usePhotoCounts('p1'));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    vi.mocked(fetchPhotoCounts).mockRejectedValueOnce(new Error('offline'));
    await act(() => result.current.refresh());
    expect(result.current.status).toBe('error');
    expect(result.current.counts).toEqual(counts);
  });

  it('starts from zero and ignores the late answer of the previous project', async () => {
    let releaseFirst: (value: PhotoCounts) => void = () => undefined;
    vi.mocked(fetchPhotoCounts).mockReturnValueOnce(new Promise((resolve) => (releaseFirst = resolve)));
    const { result, rerender } = renderHook(({ id }) => usePhotoCounts(id), { initialProps: { id: 'p1' } });

    vi.mocked(fetchPhotoCounts).mockResolvedValueOnce({ ...EMPTY_PHOTO_COUNTS, project: 9 });
    rerender({ id: 'p2' });
    await waitFor(() => expect(result.current.counts.project).toBe(9));

    await act(async () => releaseFirst(counts)); // p1 answers late
    expect(result.current.counts.project).toBe(9);
  });

  it('does nothing without a project', () => {
    const { result } = renderHook(() => usePhotoCounts(null));
    expect(fetchPhotoCounts).not.toHaveBeenCalled();
    expect(result.current.counts).toEqual(EMPTY_PHOTO_COUNTS);
  });
});
