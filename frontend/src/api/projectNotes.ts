import type { ProjectNote, ProjectNoteList } from '../types/projectNote';
import { apiRequest } from './http';

const notesPath = (projectId: string) => `/api/projects/${projectId}/notes`;

export function fetchProjectNotes(projectId: string): Promise<ProjectNoteList> {
  return apiRequest(notesPath(projectId));
}

export function createProjectNote(projectId: string, body: string): Promise<ProjectNote> {
  return apiRequest(notesPath(projectId), { method: 'POST', body: JSON.stringify({ body }) });
}

export function updateProjectNote(projectId: string, noteId: string, body: string): Promise<ProjectNote> {
  return apiRequest(`${notesPath(projectId)}/${noteId}`, { method: 'PATCH', body: JSON.stringify({ body }) });
}

export function deleteProjectNote(projectId: string, noteId: string): Promise<void> {
  return apiRequest(`${notesPath(projectId)}/${noteId}`, { method: 'DELETE' });
}
