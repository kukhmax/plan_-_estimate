import {
  BulkExecutionResultRead,
  ExecutionDetachAffected,
  ExecutionSnapshotItem,
  SurfaceWorkExecutionRead,
  SurfaceWorkPlanApplyResult,
  SurfaceWorkPlanRead,
  SurfaceWorkPlanUpsert,
  WorkExecutionTransition,
} from '../types/workPlan';
import { ApiError, apiRequest } from './http';

function workPlanPath(projectId: string, roomId: string, surfaceId: string): string {
  return `/api/projects/${projectId}/rooms/${roomId}/surfaces/${surfaceId}/work-plan`;
}

export function fetchSurfaceWorkPlan(
  projectId: string,
  roomId: string,
  surfaceId: string,
): Promise<SurfaceWorkPlanRead> {
  return apiRequest(workPlanPath(projectId, roomId, surfaceId));
}

export function putSurfaceWorkPlan(
  projectId: string,
  roomId: string,
  surfaceId: string,
  payload: SurfaceWorkPlanUpsert,
): Promise<SurfaceWorkPlanRead> {
  return apiRequest(workPlanPath(projectId, roomId, surfaceId), {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function applyWorkPlanToRoomWalls(
  projectId: string,
  roomId: string,
  surfaceId: string,
  confirmExecutionDetachKeys?: string[],
): Promise<SurfaceWorkPlanApplyResult> {
  return apiRequest(
    `${workPlanPath(projectId, roomId, surfaceId)}/apply-to-room-walls`,
    confirmExecutionDetachKeys
      ? { method: 'POST', body: JSON.stringify({ confirm_execution_detach_keys: confirmExecutionDetachKeys }) }
      : { method: 'POST' },
  );
}

/** Stage 13H.3: the only way to change execution state of one occurrence. */
export function transitionWorkExecution(
  projectId: string,
  roomId: string,
  surfaceId: string,
  occurrenceKey: string,
  transition: WorkExecutionTransition,
): Promise<SurfaceWorkExecutionRead> {
  return apiRequest(
    `${workPlanPath(projectId, roomId, surfaceId)}/occurrences/${occurrenceKey}/execution`,
    { method: 'PATCH', body: JSON.stringify(transition) },
  );
}

/** 409 WORK_EXECUTION_CONFLICT: the occurrence's status changed elsewhere
 * (stale expected_status or a transition no longer allowed). */
export function isWorkExecutionConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && error.code === 'WORK_EXECUTION_CONFLICT';
}

function isAffectedEntry(value: unknown): value is ExecutionDetachAffected {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return typeof v.occurrence_key === 'string' && typeof v.surface_id === 'string' &&
    typeof v.status === 'string' && typeof v.price_item_code === 'string';
}

/** 409 WORK_EXECUTION_DETACH_CONFIRMATION_REQUIRED (Stage 13H.4): returns the
 * server's authoritative affected list (possibly empty), or null for any
 * other error. Parsed from `detail.code` + structured data, never from text. */
export function parseExecutionDetachConfirmation(error: unknown): ExecutionDetachAffected[] | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  if (error.code !== 'WORK_EXECUTION_DETACH_CONFIRMATION_REQUIRED') return null;
  const detail = error.detail as { affected?: unknown } | undefined;
  const affected = Array.isArray(detail?.affected) ? detail.affected : [];
  return affected.filter(isAffectedEntry);
}

/** A save echoed an occurrence_key that is no longer current: the plan was
 * changed elsewhere since it was loaded (backend 409, Stage 13B/13E.2C). */
export function isStaleWorkPlanError(error: unknown): boolean {
  return error instanceof ApiError &&
    error.status === 409 &&
    error.message.includes('is not a current occurrence of this work plan');
}

export function isSurfaceWorkPlanMissing(error: unknown): boolean {
  return error instanceof ApiError &&
    error.status === 404 &&
    error.message === 'Surface work plan not found';
}

/** Stage 13H.5B: read-only preview of carrying this wall's execution
 * progress forward to the room's other walls (no mutation). */
export function previewExecutionToRoomWalls(
  projectId: string,
  roomId: string,
  surfaceId: string,
): Promise<BulkExecutionResultRead> {
  return apiRequest(
    `${workPlanPath(projectId, roomId, surfaceId)}/execution/apply-to-room-walls-preview`,
    { method: 'POST' },
  );
}

/** Stage 13H.5B: atomic apply. `expectedSource` must be the preview's
 * snapshot exactly as returned (order and NOT_STARTED entries included). */
export function applyExecutionToRoomWalls(
  projectId: string,
  roomId: string,
  surfaceId: string,
  expectedSource: ExecutionSnapshotItem[],
): Promise<BulkExecutionResultRead> {
  return apiRequest(
    `${workPlanPath(projectId, roomId, surfaceId)}/execution/apply-to-room-walls`,
    { method: 'POST', body: JSON.stringify({ expected_source: expectedSource }) },
  );
}

/** 409 WORK_EXECUTION_SOURCE_CHANGED: the source wall's works or statuses
 * changed since the preview; a new preview is required. */
export function isWorkExecutionSourceChanged(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && error.code === 'WORK_EXECUTION_SOURCE_CHANGED';
}
