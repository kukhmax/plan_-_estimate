import {
  DocumentPreviewResult,
  IssuedDocument,
  IssuedDocumentList,
  PhotoReportPartPayload,
  PhotoReportSummary,
} from '../types/document';
import { apiRequest } from './http';

const base = (projectId: string) => `/api/projects/${projectId}`;

export function issueEstimateDocument(projectId: string, estimateId: string): Promise<IssuedDocument> {
  return apiRequest(`${base(projectId)}/documents`, {
    method: 'POST',
    body: JSON.stringify({ kind: 'ESTIMATE', estimate_id: estimateId }),
  });
}

/** The whole report, or a part of it (`part`): the backend refuses a whole report over the photo limit. */
export function issuePhotoReport(projectId: string, part?: PhotoReportPartPayload): Promise<IssuedDocument> {
  return apiRequest(`${base(projectId)}/documents`, {
    method: 'POST',
    body: JSON.stringify(part ? { kind: 'PHOTO_REPORT', ...part } : { kind: 'PHOTO_REPORT' }),
  });
}

export function listDocuments(projectId: string): Promise<IssuedDocumentList> {
  return apiRequest(`${base(projectId)}/documents`);
}

export function getDocument(projectId: string, documentId: string): Promise<IssuedDocument> {
  return apiRequest(`${base(projectId)}/documents/${documentId}`);
}

export function fetchPhotoReportSummary(projectId: string): Promise<PhotoReportSummary> {
  return apiRequest(`${base(projectId)}/photo-report/summary`);
}

export function previewEstimatePdf(projectId: string, estimateId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/estimates/${estimateId}/preview-pdf`, { method: 'POST' });
}
