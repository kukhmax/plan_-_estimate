import { apiRequest } from './http';
import {
  SurfaceCreatePayload,
  SurfaceListResponse,
  SurfaceType,
  SurfaceUpdatePayload,
} from '../types/surface';

function surfacesPath(projectId: string, roomId: string): string {
  return `/api/projects/${projectId}/rooms/${roomId}/surfaces`;
}

export function fetchSurfaces(
  projectId: string,
  roomId: string,
  includeArchived = false,
): Promise<SurfaceListResponse> {
  const query = includeArchived ? '?include_archived=true' : '';
  return apiRequest(`${surfacesPath(projectId, roomId)}${query}`);
}

export function fetchSurface(
  projectId: string,
  roomId: string,
  surfaceId: string,
): Promise<SurfaceType> {
  return apiRequest(`${surfacesPath(projectId, roomId)}/${surfaceId}`);
}

export function createSurface(
  projectId: string,
  roomId: string,
  payload: SurfaceCreatePayload,
): Promise<SurfaceType> {
  return apiRequest(surfacesPath(projectId, roomId), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateSurface(
  projectId: string,
  roomId: string,
  surfaceId: string,
  payload: SurfaceUpdatePayload,
): Promise<SurfaceType> {
  return apiRequest(`${surfacesPath(projectId, roomId)}/${surfaceId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function archiveSurface(
  projectId: string,
  roomId: string,
  surfaceId: string,
): Promise<SurfaceType> {
  return apiRequest(`${surfacesPath(projectId, roomId)}/${surfaceId}/archive`, {
    method: 'POST',
  });
}

export function restoreSurface(
  projectId: string,
  roomId: string,
  surfaceId: string,
): Promise<SurfaceType> {
  return apiRequest(`${surfacesPath(projectId, roomId)}/${surfaceId}/restore`, {
    method: 'POST',
  });
}

export function generateWalls(
  projectId: string,
  roomId: string,
): Promise<SurfaceListResponse> {
  return apiRequest(`${surfacesPath(projectId, roomId)}/generate`, {
    method: 'POST',
  });
}

/** Joins walls of a room into one (the first id stays and keeps the plan; the others are archived into it). */
export function mergeSurfaces(projectId: string, roomId: string, surfaceIds: string[]): Promise<SurfaceType> {
  return apiRequest(`${surfacesPath(projectId, roomId)}/merge`, {
    method: 'POST',
    body: JSON.stringify({ surface_ids: surfaceIds }),
  });
}

/** Separates a merged wall: the joined walls come back with their photos and openings. */
export function unmergeSurface(projectId: string, roomId: string, surfaceId: string): Promise<SurfaceType> {
  return apiRequest(`${surfacesPath(projectId, roomId)}/${surfaceId}/unmerge`, { method: 'POST' });
}

/** Changes the size of one part of a merged wall. */
export function updateSurfacePart(
  projectId: string,
  roomId: string,
  surfaceId: string,
  partId: string,
  size: { width: number; height: number },
): Promise<SurfaceType> {
  return apiRequest(`${surfacesPath(projectId, roomId)}/${surfaceId}/parts/${partId}`, {
    method: 'PATCH',
    body: JSON.stringify(size),
  });
}

/** The same merged wall once more: a new merged wall with copies of the parts (no photos, openings or plan). */
export function duplicateMergedSurface(
  projectId: string,
  roomId: string,
  surfaceId: string,
  payload: { name: string; position: number | null },
): Promise<SurfaceType> {
  return apiRequest(`${surfacesPath(projectId, roomId)}/${surfaceId}/duplicate-merged`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
