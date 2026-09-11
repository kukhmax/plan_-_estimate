import { apiRequest } from './http';
import {
  AreaSegmentCreatePayload,
  AreaSegmentListResponse,
  AreaSegmentType,
  AreaSegmentUpdatePayload,
} from '../types/areaSegment';

function areaSegmentsPath(projectId: string, roomId: string): string {
  return `/api/projects/${projectId}/rooms/${roomId}/area-segments`;
}

export function fetchAreaSegments(
  projectId: string,
  roomId: string,
  includeArchived = false,
): Promise<AreaSegmentListResponse> {
  const query = includeArchived ? '?include_archived=true' : '';
  return apiRequest(`${areaSegmentsPath(projectId, roomId)}${query}`);
}

export function createAreaSegment(
  projectId: string,
  roomId: string,
  payload: AreaSegmentCreatePayload,
): Promise<AreaSegmentType> {
  return apiRequest(areaSegmentsPath(projectId, roomId), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateAreaSegment(
  projectId: string,
  roomId: string,
  segmentId: string,
  payload: AreaSegmentUpdatePayload,
): Promise<AreaSegmentType> {
  return apiRequest(`${areaSegmentsPath(projectId, roomId)}/${segmentId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function archiveAreaSegment(
  projectId: string,
  roomId: string,
  segmentId: string,
): Promise<AreaSegmentType> {
  return apiRequest(`${areaSegmentsPath(projectId, roomId)}/${segmentId}/archive`, {
    method: 'POST',
  });
}

export function restoreAreaSegment(
  projectId: string,
  roomId: string,
  segmentId: string,
): Promise<AreaSegmentType> {
  return apiRequest(`${areaSegmentsPath(projectId, roomId)}/${segmentId}/restore`, {
    method: 'POST',
  });
}
