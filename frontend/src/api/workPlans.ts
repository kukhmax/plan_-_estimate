import {
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

export function isSurfaceWorkPlanMissing(error: unknown): boolean {
  return error instanceof ApiError &&
    error.status === 404 &&
    error.message === 'Surface work plan not found';
}
