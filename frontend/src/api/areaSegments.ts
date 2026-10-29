import { apiRequest } from './http';
import {
  AreaPlane,
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

/** The order of the active rectangles of one plane (all of them, the first goes first); the answer is the list as it now is. */
export function reorderAreaSegments(
  projectId: string,
  roomId: string,
  plane: AreaPlane,
  segmentIds: string[],
): Promise<AreaSegmentListResponse> {
  return apiRequest(`${areaSegmentsPath(projectId, roomId)}/reorder`, {
    method: 'POST',
    body: JSON.stringify({ plane, segment_ids: segmentIds }),
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
