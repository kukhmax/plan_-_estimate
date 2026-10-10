import type {
  KnowledgeEntryDetail,
  KnowledgeEntryList,
  KnowledgeMeta,
  KnowledgeSituation,
  KnowledgeSituationItem,
} from '../types/knowledge';
import { apiRequest } from './http';

export function fetchKnowledgeMeta(): Promise<KnowledgeMeta> {
  return apiRequest('/api/knowledge/meta');
}

/** The list of titles; with `q` the entries that match every word of the query, best first (the server searches). */
export function listKnowledgeEntries(q = ''): Promise<KnowledgeEntryList> {
  const query = new URLSearchParams({ limit: '200' });
  if (q.trim()) query.set('q', q.trim());
  return apiRequest(`/api/knowledge/entries?${query.toString()}`);
}

export function fetchKnowledgeEntry(code: string): Promise<KnowledgeEntryDetail> {
  return apiRequest(`/api/knowledge/entries/${encodeURIComponent(code)}`);
}

export function listKnowledgeSituations(): Promise<{ items: KnowledgeSituationItem[] }> {
  return apiRequest('/api/knowledge/situations');
}

export function fetchKnowledgeSituation(code: string): Promise<KnowledgeSituation> {
  return apiRequest(`/api/knowledge/situations/${encodeURIComponent(code)}`);
}
