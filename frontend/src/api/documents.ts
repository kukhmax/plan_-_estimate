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

/** The numbered technological card of the whole object (the server refuses it with a list while data are missing). */
export function issueTechCard(projectId: string): Promise<IssuedDocument> {
  return apiRequest(`${base(projectId)}/documents`, { method: 'POST', body: JSON.stringify({ kind: 'TECH_CARD' }) });
}

/** The working version of the card (watermark, empty lines for what is missing) to the owner's chat. */
export function previewTechCardPdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/tech-card/preview`, { method: 'POST' });
}

/** The numbered production plan of the whole object (the server refuses it while no surface has a planned work). */
export function issueProductionPlan(projectId: string): Promise<IssuedDocument> {
  return apiRequest(`${base(projectId)}/documents`, { method: 'POST', body: JSON.stringify({ kind: 'PRODUCTION_PLAN' }) });
}

/** The working version of the plan (pale watermark, empty lines for what is missing) to the owner's chat. */
export function previewProductionPlanPdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/production-plan/preview`, { method: 'POST' });
}

/** The working version of the contract with its annexes (pale watermark, empty lines for what is missing) to the owner's chat. */
export function previewContractPdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/contract/preview`, { method: 'POST' });
}

/** The working version of the handover protocol (pale watermark, empty boxes and lines) to the owner's chat, to fill in on the premises. */
export function previewHandoverPdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/handover/preview`, { method: 'POST' });
}

/** The working version of the protocol of concealed works (pale watermark, empty boxes and lines) to the owner's chat, to fill in on the spot. */
export function previewConcealedPdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/concealed-works/preview`, { method: 'POST' });
}
