import {
  DocumentPreviewResult,
  IssuedDocument,
  IssuedDocumentList,
  OwnerDocumentList,
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

/** The journal of every object of the owner, newest first, one page at a time (Stage 16K.5). */
export function listAllDocuments(limit = 30, offset = 0): Promise<OwnerDocumentList> {
  return apiRequest(`/api/documents?limit=${limit}&offset=${offset}`);
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

/** Deletes one row of the journal of the sent documents (DJ-1): only the row; the document and the PDF in the chat stay. 409 `DOCUMENT_IN_PROGRESS` while it is being made. */
export function deleteDocument(projectId: string, documentId: string): Promise<void> {
  return apiRequest(`${base(projectId)}/documents/${documentId}`, { method: 'DELETE' });
}

/** The numbered statement of settlements (Rozliczenie) for the client (the server refuses it while the object has no invoice and no payment). */
export function issueSettlement(projectId: string): Promise<IssuedDocument> {
  return apiRequest(`${base(projectId)}/documents`, { method: 'POST', body: JSON.stringify({ kind: 'SETTLEMENT' }) });
}

/** The working version of the statement (watermark, no number) to the owner's chat. */
export function previewSettlementPdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/settlement/preview`, { method: 'POST' });
}

/** The numbered payment schedule (Harmonogram płatności): the stages in which the client pays (V2-9a; the server refuses it while there is no stage or a stage has no known amount). */
export function issuePaymentSchedule(projectId: string): Promise<IssuedDocument> {
  return apiRequest(`${base(projectId)}/documents`, { method: 'POST', body: JSON.stringify({ kind: 'PAYMENT_SCHEDULE' }) });
}

/** The working version of the payment schedule (watermark, no number) to the owner's chat. */
export function previewPaymentSchedulePdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/payment-schedule/preview`, { method: 'POST' });
}

/** The numbered map of hidden utilities (Mapa instalacji ukrytych): the photos whose markers name a utility (V2-12a; the server refuses it while there is none). */
export function issueInstallationMap(projectId: string): Promise<IssuedDocument> {
  return apiRequest(`${base(projectId)}/documents`, { method: 'POST', body: JSON.stringify({ kind: 'INSTALLATION_MAP' }) });
}

/** The working version of the map of hidden utilities (watermark, no number) to the owner's chat. */
export function previewInstallationMapPdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/installation-map/preview`, { method: 'POST' });
}

/**
 * The numbered measurements of the object (Obmiar obiektu): every size of every room (the server refuses it while the object has no room).
 * `withPhotos` (V2-8d) adds the photos attached to the walls, ceilings and floors under their sizes.
 */
export function issueMeasurements(projectId: string, withPhotos = false): Promise<IssuedDocument> {
  const body = withPhotos ? { kind: 'MEASUREMENTS', with_photos: true } : { kind: 'MEASUREMENTS' };
  return apiRequest(`${base(projectId)}/documents`, { method: 'POST', body: JSON.stringify(body) });
}

/** The working version of the measurements (watermark, no number) to the owner's chat; `withPhotos` as above. */
export function previewMeasurementsPdf(projectId: string, withPhotos = false): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/measurements/preview`, {
    method: 'POST',
    ...(withPhotos ? { body: JSON.stringify({ with_photos: true }) } : {}),
  });
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

/** The working version of the protocol of a pressure test (pale watermark, empty lines and boxes) to the owner's chat, to fill in during the test. */
export function previewPressureTestPdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/pressure-test/preview`, { method: 'POST' });
}

/** The working version of the acceptance protocol (pale watermark, empty boxes and lines) to the owner's chat, to fill in at the wall. */
export function previewAcceptancePdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/acceptance/preview`, { method: 'POST' });
}

/** The working version of the protocol of information and decisions (pale watermark, empty boxes and lines) to the owner's chat, to fill in on the spot. */
export function previewDecisionPdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/decision/preview`, { method: 'POST' });
}

/** The working version of the notice of downtime (pale watermark, the causes to tick, empty lines) to the owner's chat, to fill in on the spot. */
export function previewDowntimeNoticePdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/downtime-notice/preview`, { method: 'POST' });
}

/** The working version of the protocol of downtime (pale watermark, empty rows for the days) to the owner's chat, to fill in on the spot. */
export function previewDowntimeProtocolPdf(projectId: string): Promise<DocumentPreviewResult> {
  return apiRequest(`${base(projectId)}/documents/downtime-protocol/preview`, { method: 'POST' });
}
