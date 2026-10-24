import type { KnowledgeDocumentDetail, KnowledgeDocumentInput, KnowledgeDocumentList } from '../types/knowledgeDocument';
import { API_BASE, ApiError, apiRequest } from './http';

const BASE = '/api/knowledge/documents';

export function listKnowledgeDocuments(q = ''): Promise<KnowledgeDocumentList> {
  const query = new URLSearchParams();
  if (q.trim()) query.set('q', q.trim());
  const suffix = query.toString();
  return apiRequest(suffix ? `${BASE}?${suffix}` : BASE);
}

export function fetchKnowledgeDocument(id: string): Promise<KnowledgeDocumentDetail> {
  return apiRequest(`${BASE}/${encodeURIComponent(id)}`);
}

export function deleteKnowledgeDocument(id: string): Promise<void> {
  return apiRequest(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function sendKnowledgeDocumentToChat(id: string): Promise<{ sent: boolean }> {
  return apiRequest(`${BASE}/${encodeURIComponent(id)}/send`, { method: 'POST' });
}

/** A request with a body that is not JSON (a form with a file) or an answer that is not JSON (the file): the browser sets the headers of the form itself. */
async function rawRequest(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = localStorage.getItem('access_token');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (response.ok) return response;
  let detail: unknown = null;
  try {
    const payload: unknown = await response.json();
    detail = payload && typeof payload === 'object' && 'detail' in payload ? (payload as { detail: unknown }).detail : null;
  } catch {
    detail = null;
  }
  const code = detail && typeof detail === 'object' && 'code' in detail && typeof (detail as { code: unknown }).code === 'string' ? (detail as { code: string }).code : undefined;
  const message = detail && typeof detail === 'object' && 'message' in detail && typeof (detail as { message: unknown }).message === 'string' ? (detail as { message: string }).message : `Request failed (${response.status})`;
  throw new ApiError(message, response.status, code, detail);
}

function formOf(input: KnowledgeDocumentInput): FormData {
  const form = new FormData();
  form.set('title', input.title);
  form.set('kind', input.kind);
  form.set('source_url', input.source_url);
  form.set('doc_date', input.doc_date);
  form.set('when_to_use', input.when_to_use);
  form.set('body', input.body);
  form.set('tags', input.tags);
  form.set('remove_file', input.remove_file ? 'true' : 'false');
  if (input.file) form.set('file', input.file, input.file.name);
  return form;
}

/** Adds a document (`id` null) or replaces one. */
export async function saveKnowledgeDocument(id: string | null, input: KnowledgeDocumentInput): Promise<KnowledgeDocumentDetail> {
  const response = await rawRequest(id ? `${BASE}/${encodeURIComponent(id)}` : BASE, { method: id ? 'PUT' : 'POST', body: formOf(input) });
  return (await response.json()) as KnowledgeDocumentDetail;
}

export async function fetchKnowledgeDocumentFile(id: string): Promise<Blob> {
  const response = await rawRequest(`${BASE}/${encodeURIComponent(id)}/file`, { method: 'GET' });
  return response.blob();
}
