import { RoomWorkPlanResponse, RoomWorkPlanWritePayload, SurfacePlanOutcome } from '../types/roomWorkPlan';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** An answer of the server that the screen can name: the machine code of `detail.code`. */
export class RoomPlanRequestError extends Error {
  constructor(public readonly code: string | null, public readonly status: number) {
    super(code ?? `room plan request failed: ${status}`);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    const failure = await resp.json().catch(() => ({}));
    throw new RoomPlanRequestError(typeof failure?.detail?.code === 'string' ? failure.detail.code : null, resp.status);
  }
  return resp.json();
}

const roomBase = (projectId: string, roomId: string) => `/api/projects/${projectId}/rooms/${roomId}`;

export const fetchRoomWorkPlan = (projectId: string, roomId: string): Promise<RoomWorkPlanResponse> =>
  call('GET', `${roomBase(projectId, roomId)}/work-plan`);

export const saveRoomWorkPlan = (projectId: string, roomId: string, payload: RoomWorkPlanWritePayload): Promise<RoomWorkPlanResponse> =>
  call('PUT', `${roomBase(projectId, roomId)}/work-plan`, payload);

export const followRoomWorkPlan = (projectId: string, roomId: string, surfaceId: string): Promise<SurfacePlanOutcome> =>
  call('POST', `${roomBase(projectId, roomId)}/surfaces/${surfaceId}/work-plan/follow-room-plan`);
