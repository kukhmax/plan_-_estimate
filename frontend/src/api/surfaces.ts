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
