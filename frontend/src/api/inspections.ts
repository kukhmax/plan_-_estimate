import { apiRequest } from './http';
import {
  Inspection,
  InspectionAnswerListResponse,
  InspectionAnswersPutPayload,
  InspectionCreatePayload,
  InspectionDetail,
  InspectionFindingListResponse,
  InspectionListResponse,
  InspectionUpdatePayload,
} from '../types/inspection';

function inspectionsPath(projectId: string, roomId: string): string {
  return `/api/projects/${projectId}/rooms/${roomId}/inspections`;
}

function inspectionPath(
  projectId: string,
  roomId: string,
  inspectionId: string,
): string {
  return `${inspectionsPath(projectId, roomId)}/${inspectionId}`;
}

export function fetchInspections(
  projectId: string,
  roomId: string,
  includeArchived = false,
): Promise<InspectionListResponse> {
  const query = includeArchived ? '?include_archived=true' : '';
  return apiRequest(`${inspectionsPath(projectId, roomId)}${query}`);
}

export function createInspection(
  projectId: string,
  roomId: string,
  payload: InspectionCreatePayload,
): Promise<Inspection> {
  return apiRequest(inspectionsPath(projectId, roomId), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchInspection(
  projectId: string,
  roomId: string,
  inspectionId: string,
): Promise<InspectionDetail> {
  return apiRequest(inspectionPath(projectId, roomId, inspectionId));
}

export function updateInspection(
  projectId: string,
  roomId: string,
  inspectionId: string,
  payload: InspectionUpdatePayload,
): Promise<Inspection> {
  return apiRequest(inspectionPath(projectId, roomId, inspectionId), {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function fetchInspectionAnswers(
  projectId: string,
  roomId: string,
  inspectionId: string,
): Promise<InspectionAnswerListResponse> {
  return apiRequest(`${inspectionPath(projectId, roomId, inspectionId)}/answers`);
}

export function putInspectionAnswers(
  projectId: string,
  roomId: string,
  inspectionId: string,
  payload: InspectionAnswersPutPayload,
): Promise<InspectionAnswerListResponse> {
  return apiRequest(`${inspectionPath(projectId, roomId, inspectionId)}/answers`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function completeInspection(
  projectId: string,
  roomId: string,
  inspectionId: string,
): Promise<Inspection> {
  return apiRequest(`${inspectionPath(projectId, roomId, inspectionId)}/complete`, {
    method: 'POST',
  });
}

export function reopenInspection(
  projectId: string,
  roomId: string,
  inspectionId: string,
): Promise<Inspection> {
  return apiRequest(`${inspectionPath(projectId, roomId, inspectionId)}/reopen`, {
    method: 'POST',
  });
}

export function archiveInspection(
  projectId: string,
  roomId: string,
  inspectionId: string,
): Promise<Inspection> {
  return apiRequest(`${inspectionPath(projectId, roomId, inspectionId)}/archive`, {
    method: 'POST',
  });
}

export function restoreInspection(
  projectId: string,
  roomId: string,
  inspectionId: string,
): Promise<Inspection> {
  return apiRequest(`${inspectionPath(projectId, roomId, inspectionId)}/restore`, {
    method: 'POST',
  });
}

export function fetchInspectionFindings(
  projectId: string,
  roomId: string,
  inspectionId: string,
  includeInactive = false,
): Promise<InspectionFindingListResponse> {
  const query = includeInactive ? '?include_inactive=true' : '';
  return apiRequest(
    `${inspectionPath(projectId, roomId, inspectionId)}/findings${query}`,
  );
}