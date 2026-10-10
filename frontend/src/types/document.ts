/** Stage 15F — the journal of issued documents and the photo report summary (mirrors backend `schemas/issued_document.py`). */
export type DocumentKind = 'ESTIMATE' | 'PHOTO_REPORT' | 'TECH_CARD' | 'PRODUCTION_PLAN' | 'CONTRACT' | 'HANDOVER_PROTOCOL' | 'CONCEALED_WORKS_PROTOCOL' | 'FINAL_PROTOCOL';
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

/** Why a recommended extra work has no price: the owner decides it, makes an estimate, brings the accepted work into it, or prices its line. */
export type UnpricedReason = 'PENDING' | 'NO_ESTIMATE' | 'NOT_IN_ESTIMATE' | 'NO_PRICE';

/** A recommended extra work that blocks the photo report, with where to fix it (Stage 15H.1). */
export interface UnpricedWork {
  room_id: string;
  room_name: string;
  surface_id: string;
  surface_name: string;
  surface_type: string;
  work_code: string;
  work_display_name: string | null;
  work_name_key: string | null;
  reason: UnpricedReason;
  inspection_id: string | null;
  inspection_surface_id: string | null;
  inspection_plane: 'FLOOR' | 'CEILING' | null;
}

export interface PhotoReportSummary {
  photo_count: number;
  project_photos: number;
  limit: number;
  over_limit: boolean;
  has_content: boolean;
  rooms: PhotoReportRoomSummary[];
  /** Recommended extra works the report would list, and those without a price in the current estimate (they block it). */
  recommended_count: number;
  unpriced_works: string[];
  /** The same works, structured: the screen names them in the interface language and leads to the fix. */
  unpriced_items: UnpricedWork[];
  /** The current estimate (whose prices are used) and its status; null when the object has none. */
  estimate_id: string | null;
  estimate_status: string | null;
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

/** A surface with planned works that cannot be in a numbered technological card yet, and what it lacks (Stage 16C). */
export interface TechCardMissingItem {
  room: string;
  surface: string;
  surface_type: string;
  missing: Array<'QUALITY_TARGET' | 'INSPECTION'>;
}
