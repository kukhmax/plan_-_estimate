/** Stage 15F — the journal of issued documents and the photo report summary (mirrors backend `schemas/issued_document.py`). */
export type DocumentKind = 'ESTIMATE' | 'PHOTO_REPORT';
export type DocumentStatus = 'PENDING' | 'SENT' | 'FAILED';

export interface IssuedDocument {
  id: string;
  project_id: string;
  kind: DocumentKind;
  source_id: string | null;
  source_version: number | null;
  title: string;
  number: string;
  project_seq: number;
  template_version: string;
  status: DocumentStatus;
  /** A stable code (see `documents.errors` in the locales) when status is FAILED. */
  error_code: string | null;
  scope: { room_ids: string[]; include_project_photos: boolean } | null;
  pages: number | null;
  byte_size: number | null;
  issued_at: string;
  sent_at: string | null;
}

export interface IssuedDocumentList {
  items: IssuedDocument[];
  total: number;
}

export interface PhotoReportRoomSummary {
  room_id: string;
  name: string;
  photos: number;
  has_inspection_content: boolean;
}

export interface PhotoReportSummary {
  photo_count: number;
  project_photos: number;
  limit: number;
  over_limit: boolean;
  has_content: boolean;
  rooms: PhotoReportRoomSummary[];
}

export interface DocumentPreviewResult {
  sent: boolean;
  pages: number;
  byte_size: number;
}

/** A part of a photo report: the chosen rooms (the general photos of the object only when asked for). */
export interface PhotoReportPartPayload {
  room_ids: string[];
  include_project_photos: boolean;
}
