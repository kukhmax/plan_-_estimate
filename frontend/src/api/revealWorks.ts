import {
  RevealWorkApplyResult,
  RevealWorkListResponse,
  RevealWorkSetPayload,
} from '../types/revealWork';
import { apiRequest } from './http';

function revealWorksPath(
  projectId: string,
  roomId: string,
  surfaceId: string,
  openingId: string,
): string {
  return `/api/projects/${projectId}/rooms/${roomId}/surfaces/${surfaceId}` +
    `/openings/${openingId}/reveal-works`;
}

export function fetchRevealWorks(
  projectId: string,
  roomId: string,
  surfaceId: string,
  openingId: string,
): Promise<RevealWorkListResponse> {
  return apiRequest(revealWorksPath(projectId, roomId, surfaceId, openingId));
}

// Full replacement PUT — see RevealWorkSetPayload.
export function putRevealWorks(
  projectId: string,
  roomId: string,
  surfaceId: string,
  openingId: string,
  payload: RevealWorkSetPayload,
): Promise<RevealWorkListResponse> {
  return apiRequest(revealWorksPath(projectId, roomId, surfaceId, openingId), {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

// 204 No Content — handled by the shared apiRequest 204 fix (Stage 10G.3C).
export function clearRevealWorks(
  projectId: string,
  roomId: string,
  surfaceId: string,
  openingId: string,
): Promise<void> {
  return apiRequest(revealWorksPath(projectId, roomId, surfaceId, openingId), {
    method: 'DELETE',
  });
}

// Stage 10G.4 — atomic room-scoped bulk apply. Copies this opening's
// currently persisted ordered reveal work selection to every other
// reveal-enabled, non-archived opening in the room (all-or-nothing).
export function applyRevealWorksToRoom(
  projectId: string,
  roomId: string,
  surfaceId: string,
  openingId: string,
): Promise<RevealWorkApplyResult> {
  return apiRequest(
    `${revealWorksPath(projectId, roomId, surfaceId, openingId)}/apply-to-room-openings`,
    { method: 'POST' },
  );
}
