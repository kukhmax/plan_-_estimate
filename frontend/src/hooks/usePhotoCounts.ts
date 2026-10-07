import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPhotoCounts } from '../api/photos';
import { PhotoContext, PhotoCounts } from '../types/photo';

// Badge counts for the open project (contract §9): one request per workspace load, optimistic adjustments after
// upload / archive / restore, refetch on demand.

export const EMPTY_PHOTO_COUNTS: PhotoCounts = { project: 0, rooms: {}, surfaces: {}, openings: {}, room_totals: {}, inspections: {}, findings: {}, lineages: {}, questions: {} };

/** Extra identity of an inspection-evidence target (Stage 14F): the checklist question of a question-level photo, the lineage of a finding. */
export interface PhotoCountScope {
  questionId?: string;
  lineageId?: string;
}

/**
 * Visible photos attached directly to a target. `targetId` is ignored for PROJECT. INSPECTION: the inspection's own count, or
 * with `questionId` the question-level photos of that question; FINDING: the lineage's count (a finding shows the photos of
 * every row of its lineage), falling back to the row's own.
 */
export function photoCountFor(counts: PhotoCounts, context: PhotoContext, targetId?: string, scope: PhotoCountScope = {}): number {
  if (context === 'PROJECT') return counts.project;
  if (!targetId) return 0;
  if (context === 'INSPECTION') {
    return scope.questionId ? (counts.questions?.[targetId]?.[scope.questionId] ?? 0) : (counts.inspections?.[targetId] ?? 0);
  }
  if (context === 'FINDING') {
    return (scope.lineageId ? counts.lineages?.[scope.lineageId] : undefined) ?? counts.findings?.[targetId] ?? 0;
  }
  const bucket = context === 'ROOM' ? counts.rooms : context === 'SURFACE' ? counts.surfaces : counts.openings;
  return bucket[targetId] ?? 0;
}

/** Every visible photo of a room: its own, those of its surfaces and of their openings (the room card's number). */
export function roomPhotoTotal(counts: PhotoCounts, roomId: string): number {
  return counts.room_totals?.[roomId] ?? 0;
}

/** Every visible attachment of the object (what the project-level list shows, C-3). */
export function totalPhotoCount(counts: PhotoCounts): number {
  const sum = (bucket: Record<string, number>) => Object.values(bucket).reduce((total, value) => total + value, 0);
  return counts.project + sum(counts.rooms) + sum(counts.surfaces) + sum(counts.openings);
}

function bump(bucket: Record<string, number>, id: string, delta: number): Record<string, number> {
  const next = Math.max(0, (bucket[id] ?? 0) + delta);
  const copy = { ...bucket };
  if (next === 0) delete copy[id];
  else copy[id] = next;
  return copy;
}

/**
 * Pure counterpart of the optimistic update; never goes below zero and drops emptied targets. `roomId` is the room a
 * SURFACE / OPENING photo belongs to when the caller knows it: it keeps the room's total in step. Without it the room
 * total is left alone (the host refetches the counts for the truth).
 */
export function adjustPhotoCounts(
  counts: PhotoCounts,
  context: PhotoContext,
  targetId: string | undefined,
  delta: number,
  roomId?: string,
  scope: PhotoCountScope = {},
): PhotoCounts {
  if (context === 'PROJECT') return { ...counts, project: Math.max(0, counts.project + delta) };
  if (!targetId) return counts;
  if (context === 'INSPECTION') {
    const questions = counts.questions ?? {};
    const inspectionQuestions = scope.questionId ? bump(questions[targetId] ?? {}, scope.questionId, delta) : null;
    const nextQuestions = { ...questions };
    if (inspectionQuestions) {
      if (Object.keys(inspectionQuestions).length === 0) delete nextQuestions[targetId];
      else nextQuestions[targetId] = inspectionQuestions;
    }
    return { ...counts, inspections: bump(counts.inspections ?? {}, targetId, delta), questions: nextQuestions };
  }
  if (context === 'FINDING') {
    return {
      ...counts,
      findings: bump(counts.findings ?? {}, targetId, delta),
      ...(scope.lineageId ? { lineages: bump(counts.lineages ?? {}, scope.lineageId, delta) } : {}),
    };
  }
  const key = context === 'ROOM' ? 'rooms' : context === 'SURFACE' ? 'surfaces' : 'openings';
  const owningRoom = context === 'ROOM' ? targetId : roomId;
  return {
    ...counts,
    [key]: bump(counts[key], targetId, delta),
    ...(owningRoom ? { room_totals: bump(counts.room_totals ?? {}, owningRoom, delta) } : {}),
  };
}

export type PhotoCountsStatus = 'loading' | 'ready' | 'error';

export interface PhotoCountsView {
  counts: PhotoCounts;
  status: PhotoCountsStatus;
  refresh: () => Promise<void>;
  adjust: (context: PhotoContext, targetId: string | undefined, delta: number, roomId?: string, scope?: PhotoCountScope) => void;
}

export function usePhotoCounts(projectId: string | null | undefined): PhotoCountsView {
  const [counts, setCounts] = useState<PhotoCounts>(EMPTY_PHOTO_COUNTS);
  const [status, setStatus] = useState<PhotoCountsStatus>('loading');
  const latest = useRef(0);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const token = ++latest.current;
    try {
      const next = await fetchPhotoCounts(projectId);
      if (token === latest.current) {
        setCounts(next);
        setStatus('ready');
      }
    } catch {
      if (token === latest.current) setStatus('error');
    }
  }, [projectId]);

  useEffect(() => {
    setCounts(EMPTY_PHOTO_COUNTS);
    setStatus('loading');
    void refresh();
    return () => {
      latest.current += 1; // drop the answer of a request for the previous project
    };
  }, [refresh]);

  const adjust = useCallback(
    (context: PhotoContext, targetId: string | undefined, delta: number, roomId?: string, scope?: PhotoCountScope) => {
      setCounts((current) => adjustPhotoCounts(current, context, targetId, delta, roomId, scope));
    },
    [],
  );

  return { counts, status, refresh, adjust };
}
