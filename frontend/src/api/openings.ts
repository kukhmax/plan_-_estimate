import { apiRequest } from './http';
import {
  OpeningCreatePayload,
  OpeningListResponse,
  OpeningType,
  OpeningUpdatePayload,
} from '../types/opening';

function openingsPath(projectId: string, roomId: string, surfaceId: string): string {
  return `/api/projects/${projectId}/rooms/${roomId}/surfaces/${surfaceId}/openings`;
}

export function fetchOpenings(
  projectId: string,
  roomId: string,
  surfaceId: string,
  includeArchived = false,
): Promise<OpeningListResponse> {
  const query = includeArchived ? '?include_archived=true' : '';
  return apiRequest(`${openingsPath(projectId, roomId, surfaceId)}${query}`);
}

export function fetchOpening(
  projectId: string,
  roomId: string,
  surfaceId: string,
  openingId: string,
): Promise<OpeningType> {
  return apiRequest(`${openingsPath(projectId, roomId, surfaceId)}/${openingId}`);
}

export function createOpening(
  projectId: string,
  roomId: string,
  surfaceId: string,
  payload: OpeningCreatePayload,
): Promise<OpeningType> {
  return apiRequest(openingsPath(projectId, roomId, surfaceId), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateOpening(
  projectId: string,
  roomId: string,
  surfaceId: string,
  openingId: string,
  payload: OpeningUpdatePayload,
): Promise<OpeningType> {
  return apiRequest(`${openingsPath(projectId, roomId, surfaceId)}/${openingId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function archiveOpening(
  projectId: string,
  roomId: string,
  surfaceId: string,
  openingId: string,
): Promise<OpeningType> {
  return apiRequest(
    `${openingsPath(projectId, roomId, surfaceId)}/${openingId}/archive`,
    { method: 'POST' },
  );
}

export function restoreOpening(
  projectId: string,
  roomId: string,
  surfaceId: string,
  openingId: string,
): Promise<OpeningType> {
  return apiRequest(
    `${openingsPath(projectId, roomId, surfaceId)}/${openingId}/restore`,
    { method: 'POST' },
  );
}
