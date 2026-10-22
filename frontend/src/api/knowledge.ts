import type {
  KnowledgeEntryDetail,
  KnowledgeEntryList,
  KnowledgeLinkIndex,
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

let linkIndex: Promise<KnowledgeLinkIndex> | null = null;

/**
 * Every place of the application that points at the knowledge base, asked once and kept while the application is open: a
 * list of risks or phrases shows many cards, and each must not ask the server. A failed request is forgotten, so the
 * next card asks again.
 */
export function fetchKnowledgeLinkIndex(): Promise<KnowledgeLinkIndex> {
  if (!linkIndex) {
    linkIndex = apiRequest<KnowledgeLinkIndex>('/api/knowledge/links/index').catch((error: unknown) => {
      linkIndex = null;
      throw error;
    });
  }
  return linkIndex;
}

export function forgetKnowledgeLinkIndex(): void {
  linkIndex = null;
}

let entryIndex: Promise<KnowledgeEntryList> | null = null;

/** Every title of the knowledge base, asked once and kept while the application is open: the "?" helps of a screen share it. */
export function fetchKnowledgeEntryIndex(): Promise<KnowledgeEntryList> {
  if (!entryIndex) {
    entryIndex = listKnowledgeEntries().catch((error: unknown) => {
      entryIndex = null;
      throw error;
    });
  }
  return entryIndex;
}

export function forgetKnowledgeEntryIndex(): void {
  entryIndex = null;
}
