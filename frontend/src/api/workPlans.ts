import {
  SurfaceWorkPlanApplyResult,
  SurfaceWorkPlanRead,
  SurfaceWorkPlanUpsert,
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
): Promise<SurfaceWorkPlanApplyResult> {
  return apiRequest(
    `${workPlanPath(projectId, roomId, surfaceId)}/apply-to-room-walls`,
    { method: 'POST' },
  );
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
