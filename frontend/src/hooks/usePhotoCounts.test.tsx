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
  inspections: {}, findings: {}, lineages: {}, questions: {}, works: {}, work_surfaces: {}, inspection_surfaces: {},
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

describe('inspection evidence counts (14F)', () => {
  const evidence: PhotoCounts = {
    ...counts,
    inspections: { i1: 4 },
    questions: { i1: { q1: 2, q2: 1 } },
    findings: { f1: 1, f2: 2 },
    lineages: { L: 3 },
  };

  it('reads the inspection, one question of it, and a finding through its lineage', () => {
    expect(photoCountFor(evidence, 'INSPECTION', 'i1')).toBe(4);
    expect(photoCountFor(evidence, 'INSPECTION', 'i1', { questionId: 'q1' })).toBe(2);
    expect(photoCountFor(evidence, 'INSPECTION', 'i1', { questionId: 'nope' })).toBe(0);
    expect(photoCountFor(evidence, 'INSPECTION', 'other')).toBe(0);
    expect(photoCountFor(evidence, 'FINDING', 'f2', { lineageId: 'L' })).toBe(3); // every row of the lineage
    expect(photoCountFor(evidence, 'FINDING', 'f2')).toBe(2); // without a lineage: the row's own
    expect(photoCountFor(evidence, 'FINDING', 'f2', { lineageId: 'unknown' })).toBe(2);
    expect(photoCountFor(evidence, 'FINDING', undefined)).toBe(0);
  });

  it('tolerates an answer from a server that does not know the new maps', () => {
    const old = { ...counts } as unknown as PhotoCounts;
    expect(photoCountFor(old, 'INSPECTION', 'i1')).toBe(0);
    expect(photoCountFor(old, 'INSPECTION', 'i1', { questionId: 'q1' })).toBe(0);
    expect(photoCountFor(old, 'FINDING', 'f1', { lineageId: 'L' })).toBe(0);
    expect(adjustPhotoCounts(old, 'INSPECTION', 'i1', 1, undefined, { questionId: 'q1' }).inspections.i1).toBe(1);
  });

  it('adjusts the inspection and its question together, dropping emptied entries', () => {
    const added = adjustPhotoCounts(evidence, 'INSPECTION', 'i1', 1, undefined, { questionId: 'q1' });
    expect(added.inspections.i1).toBe(5);
    expect(added.questions.i1.q1).toBe(3);
    expect(added.room_totals).toEqual(evidence.room_totals); // evidence never enters the room totals
    const inspectionLevel = adjustPhotoCounts(evidence, 'INSPECTION', 'i1', 1);
    expect(inspectionLevel.inspections.i1).toBe(5);
    expect(inspectionLevel.questions).toEqual(evidence.questions); // no question: the per-question map is untouched
    let emptied = adjustPhotoCounts(evidence, 'INSPECTION', 'i1', -1, undefined, { questionId: 'q2' });
    expect(emptied.questions.i1).toEqual({ q1: 2 });
    emptied = adjustPhotoCounts(emptied, 'INSPECTION', 'i1', -2, undefined, { questionId: 'q1' });
    expect(emptied.questions).toEqual({});
    expect(adjustPhotoCounts(evidence, 'INSPECTION', 'i1', -99).inspections).toEqual({});
  });

  it('adjusts a finding row and its lineage together', () => {
    const added = adjustPhotoCounts(evidence, 'FINDING', 'f1', 1, undefined, { lineageId: 'L' });
    expect(added.findings.f1).toBe(2);
    expect(added.lineages.L).toBe(4);
    const noLineage = adjustPhotoCounts(evidence, 'FINDING', 'f1', 1);
    expect(noLineage.findings.f1).toBe(2);
    expect(noLineage.lineages).toEqual(evidence.lineages);
    expect(adjustPhotoCounts(evidence, 'FINDING', 'f1', -1, undefined, { lineageId: 'L' }).findings).toEqual({ f2: 2 });
    expect(adjustPhotoCounts(evidence, 'FINDING', undefined, 1)).toBe(evidence);
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

describe('execution evidence counts (14H)', () => {
  const work: PhotoCounts = { ...counts, works: { k1: 2, k2: 1 }, work_surfaces: { s1: 3 } };

  it('reads one planned work, or every execution photo of the surface', () => {
    expect(photoCountFor(work, 'WORK', 's1', { occurrenceKey: 'k1' })).toBe(2);
    expect(photoCountFor(work, 'WORK', 's1', { occurrenceKey: 'unknown' })).toBe(0);
    expect(photoCountFor(work, 'WORK', 's1')).toBe(3);
    expect(photoCountFor(work, 'WORK', 'other')).toBe(0);
    expect(photoCountFor(work, 'WORK', undefined, { occurrenceKey: 'k1' })).toBe(0);
    // the site photos of the same surface are a different number
    expect(photoCountFor(work, 'SURFACE', 's1')).toBe(counts.surfaces.s1 ?? 0);
  });

  it('tolerates an answer from a server that does not know the execution maps', () => {
    const old = { ...counts } as unknown as PhotoCounts;
    expect(photoCountFor(old, 'WORK', 's1', { occurrenceKey: 'k1' })).toBe(0);
    expect(photoCountFor(old, 'WORK', 's1')).toBe(0);
    const added = adjustPhotoCounts(old, 'WORK', 's1', 1, undefined, { occurrenceKey: 'k1' });
    expect(added.works).toEqual({ k1: 1 });
    expect(added.work_surfaces).toEqual({ s1: 1 });
  });

  it('adjusts the planned work and its surface together and never touches the site numbers', () => {
    const added = adjustPhotoCounts(work, 'WORK', 's1', 1, 'r1', { occurrenceKey: 'k1' });
    expect(added.works).toEqual({ k1: 3, k2: 1 });
    expect(added.work_surfaces).toEqual({ s1: 4 });
    expect(added.surfaces).toEqual(work.surfaces);
    expect(added.rooms).toEqual(work.rooms);
    expect(added.room_totals).toEqual(work.room_totals); // execution evidence never enters a room's number
    expect(added.project).toBe(work.project);
  });

  it('without a key only the surface total moves; emptied entries disappear; nothing goes below zero', () => {
    const surfaceOnly = adjustPhotoCounts(work, 'WORK', 's1', 1);
    expect(surfaceOnly.work_surfaces).toEqual({ s1: 4 });
    expect(surfaceOnly.works).toEqual(work.works);
    const lower = adjustPhotoCounts(work, 'WORK', 's1', -1, undefined, { occurrenceKey: 'k2' });
    expect(lower.works).toEqual({ k1: 2 });
    expect(lower.work_surfaces).toEqual({ s1: 2 });
    expect(adjustPhotoCounts(work, 'WORK', 's1', -9, undefined, { occurrenceKey: 'k1' }).works).toEqual({ k2: 1 });
    expect(adjustPhotoCounts(work, 'WORK', undefined, 1)).toBe(work);
  });
});
