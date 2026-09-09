import { apiRequest } from './http';
import {
  RoomCreatePayload,
  RoomListResponse,
  RoomType,
  RoomUpdatePayload,
} from '../types/room';

function roomsPath(projectId: string): string {
  return `/api/projects/${projectId}/rooms`;
}

export function fetchRooms(projectId: string, includeArchived = false): Promise<RoomListResponse> {
  const query = includeArchived ? '?include_archived=true' : '';
  return apiRequest(`${roomsPath(projectId)}${query}`);
}

export function fetchRoom(projectId: string, roomId: string): Promise<RoomType> {
  return apiRequest(`${roomsPath(projectId)}/${roomId}`);
}

export function createRoom(projectId: string, payload: RoomCreatePayload): Promise<RoomType> {
  return apiRequest(roomsPath(projectId), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateRoom(
  projectId: string,
  roomId: string,
  payload: RoomUpdatePayload,
): Promise<RoomType> {
  return apiRequest(`${roomsPath(projectId)}/${roomId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function archiveRoom(projectId: string, roomId: string): Promise<RoomType> {
  return apiRequest(`${roomsPath(projectId)}/${roomId}/archive`, { method: 'POST' });
}

export function restoreRoom(projectId: string, roomId: string): Promise<RoomType> {
  return apiRequest(`${roomsPath(projectId)}/${roomId}/restore`, { method: 'POST' });
}
