import { apiRequest } from './http';
import {
  CommunicationApplicationDetailRead,
  CommunicationListResponse,
  CommunicationStatusValue,
} from '../types/communication';

function communicationsPath(
  projectId: string,
  roomId: string,
  inspectionId: string,
): string {
  return `/api/projects/${projectId}/rooms/${roomId}/inspections/${inspectionId}/communications`;
}

/** Flat list; the backend defaults to active when status is omitted. */
export function fetchCommunications(
  projectId: string,
  roomId: string,
  inspectionId: string,
  { status }: { status?: CommunicationStatusValue } = {},
): Promise<CommunicationListResponse> {
  let path = communicationsPath(projectId, roomId, inspectionId);
  // "all" and "resolved" must be sent explicitly, not dropped: the backend
  // defaults to active when the status parameter is absent.
  if (status) {
    path = `${path}?status=${status}`;
  }
  return apiRequest(path);
}

export function evaluateCommunications(
  projectId: string,
  roomId: string,
  inspectionId: string,
): Promise<CommunicationListResponse> {
  return apiRequest(
    `${communicationsPath(projectId, roomId, inspectionId)}/evaluate`,
    { method: 'POST' },
  );
}

/** One application with its traceability source, fetched lazily on demand. */
export function fetchCommunicationDetail(
  projectId: string,
  roomId: string,
  inspectionId: string,
  communicationId: string,
): Promise<CommunicationApplicationDetailRead> {
  return apiRequest(
    `${communicationsPath(projectId, roomId, inspectionId)}/${communicationId}`,
  );
}