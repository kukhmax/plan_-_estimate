import type { ArchivedDocumentKind, ArchivedDocuments, DocumentPurgePreview, DocumentPurgeResult } from '../types/archivedDocument';
import { apiRequest } from './http';

/** The archived contracts and protocols of all objects in work, with the object (AC-6): only the data of the card. */
export function fetchArchivedDocuments(): Promise<ArchivedDocuments> {
  return apiRequest('/api/archive/documents');
}

export function fetchDocumentPurgePreview(kind: ArchivedDocumentKind, id: string): Promise<DocumentPurgePreview> {
  return apiRequest(`/api/archive/documents/${kind}/${id}/purge-preview`);
}

/** Only an archived record can be deleted for good; a contract that protocols still refer to is refused (409). */
export function purgeArchivedDocument(kind: ArchivedDocumentKind, id: string): Promise<DocumentPurgeResult> {
  return apiRequest(`/api/archive/documents/${kind}/${id}/purge`, { method: 'POST' });
}
