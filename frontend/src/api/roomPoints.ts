import type { AddToEstimateResult, PointFields, PointsPackResult, RoomPoint } from '../types/roomPoints';
import { apiRequest } from './http';

const points = (projectId: string, roomId: string) => `/api/projects/${projectId}/rooms/${roomId}/points`;

/** The points and routes of a room, in the order of entry. Online only. */
export async function fetchRoomPoints(projectId: string, roomId: string): Promise<RoomPoint[]> {
  return (await apiRequest<{ items: RoomPoint[] }>(points(projectId, roomId))).items;
}

export function createRoomPoint(projectId: string, roomId: string, fields: PointFields): Promise<RoomPoint> {
  return apiRequest(points(projectId, roomId), { method: 'POST', body: JSON.stringify(fields) });
}

export function updateRoomPoint(projectId: string, roomId: string, pointId: string, fields: Partial<PointFields>): Promise<RoomPoint> {
  return apiRequest(`${points(projectId, roomId)}/${pointId}`, { method: 'PATCH', body: JSON.stringify(fields) });
}

export function deleteRoomPoint(projectId: string, roomId: string, pointId: string): Promise<void> {
  return apiRequest(`${points(projectId, roomId)}/${pointId}`, { method: 'DELETE' });
}

/** The rows of the whole object become the lines of a draft estimate (a snapshot; what is in it already is not added twice). */
export function addPointsToEstimate(projectId: string, estimateId: string): Promise<AddToEstimateResult> {
  return apiRequest(`/api/projects/${projectId}/estimates/${estimateId}/add-points`, { method: 'POST' });
}

/** The typical items of the trades that work in points and routes, made in the owner's price book (idempotent, no prices). */
export function makePointsPack(): Promise<PointsPackResult> {
  return apiRequest('/api/price-items/points-pack', { method: 'POST' });
}
