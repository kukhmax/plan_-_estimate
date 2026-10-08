// TypeScript mirrors of the backend photo DTOs (backend/app/schemas/photo.py, Stage 14C/14E.2).
// Contract: docs/STAGE_14E_PHOTO_UI_CONTRACT.md §4.

export const PHOTO_CATEGORIES = [
  'GENERAL',
  'BEFORE',
  'DEFECT',
  'PREPARATION',
  'IN_PROGRESS',
  'HIDDEN_WORK',
  'AFTER',
  'DAMAGE',
] as const;
export type PhotoCategory = (typeof PHOTO_CATEGORIES)[number];

// The site contexts of the 14E UI, the inspection evidence of 14F and the execution evidence (WORK) of 14H.
export const PHOTO_CONTEXTS = ['PROJECT', 'ROOM', 'SURFACE', 'OPENING', 'INSPECTION', 'FINDING', 'WORK'] as const;
export type PhotoContext = (typeof PHOTO_CONTEXTS)[number];

export type PhotoCaptureSource = 'CAMERA' | 'GALLERY';
export type PhotoStorageState = 'OK' | 'WARNING' | 'FULL';
export type PhotoContentType = 'image/jpeg' | 'image/png' | 'image/webp';

export interface PhotoAssetRead {
  id: string;
  project_id: string;
  status: 'READY' | 'PENDING' | 'FAILED';
  content_type: PhotoContentType;
  byte_size: number;
  width: number;
  height: number;
  original_filename: string | null;
  /** EXIF DateTimeOriginal: camera-local wall-clock time, no timezone. */
  captured_at: string | null;
  /** Client-declared and informational only; null for photos uploaded before the field existed. */
  capture_source: PhotoCaptureSource | null;
  /** UTC instant. */
  uploaded_at: string;
  archived_at: string | null;
}

export interface PhotoAttachmentRead {
  id: string;
  asset_id: string;
  project_id: string;
  context: string;
  room_id: string | null;
  surface_id: string | null;
  opening_id: string | null;
  /** Inspection evidence (Stage 14F.2); `question_id` is set only on INSPECTION photos taken for one checklist question. */
  inspection_id: string | null;
  question_id: string | null;
  finding_id: string | null;
  /** Execution evidence (Stage 14H.1): a WORK photo names its surface and the Stage 13 occurrence of the plan, plus the operation snapshotted when it was taken. */
  occurrence_key: string | null;
  price_item_id: string | null;
  category: PhotoCategory;
  caption: string | null;
  include_in_report: boolean;
  position: number;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PhotoListItem {
  attachment: PhotoAttachmentRead;
  asset: PhotoAssetRead;
  thumbnail_url: string | null;
  /** Point markers on this attachment (Stage 14G). */
  annotation_count: number;
}

export interface PhotoListResponse {
  items: PhotoListItem[];
  next_cursor: string | null;
  urls_expire_at: string | null;
}

/** A point marker (Stage 14G): where on the display image, as fractions 0..1 from the top-left corner. */
export interface PhotoAnnotationRead {
  id: string;
  attachment_id: string;
  kind: 'POINT';
  x: number;
  y: number;
  label: string | null;
  /** A freehand contour around the defect (Stage 14G.4): points as fractions 0..1 like x / y; null = none. */
  outline: Array<[number, number]> | null;
  position: number;
  created_at: string;
  updated_at: string;
}

/** A marker label holds at most this many characters (the server enforces the same limit). */
export const MAX_MARKER_LABEL_LENGTH = 40;

export interface PhotoDetailResponse {
  asset: PhotoAssetRead;
  attachments: PhotoAttachmentRead[];
  thumbnail_url: string | null;
  display_url: string | null;
  urls_expire_at: string | null;
  /** Markers of every attachment of the asset (each names its attachment), in display order. */
  annotations: PhotoAnnotationRead[];
  /** Most markers one attachment may carry. */
  annotation_limit: number;
  /** Most points of one marker's contour. */
  outline_max_points: number;
}

export interface PhotoUploadResponse {
  asset: PhotoAssetRead;
  attachment: PhotoAttachmentRead | null;
  thumbnail_url: string;
  display_url: string;
  urls_expire_at: string;
  storage: { state: PhotoStorageState };
}

export interface PhotoStorageStatus {
  uploads_enabled: boolean;
  media_available: boolean;
  used_bytes: number;
  warning_bytes: number;
  soft_cap_bytes: number;
  state: PhotoStorageState;
}

/** GET /photos/counts: visible photos per target; targets without photos are absent. */
export interface PhotoCounts {
  project: number;
  rooms: Record<string, number>;
  surfaces: Record<string, number>;
  openings: Record<string, number>;
  /** Photos per room INCLUDING those of its surfaces and their openings (what a room card shows). */
  room_totals: Record<string, number>;
  /** Inspection evidence (Stage 14F.2), kept apart from the room totals: photos per inspection (inspection- and question-level together). */
  inspections: Record<string, number>;
  /** Photos per finding row, and per finding lineage (the sum over every row of the lineage). */
  findings: Record<string, number>;
  lineages: Record<string, number>;
  /** Question-level photos only: inspection id → question id → count (inspection-level photos are in no question). */
  questions: Record<string, Record<string, number>>;
  /** Execution evidence (Stage 14H.1), kept apart from the site photos: photos per occurrence_key (detached occurrences included) and per surface. */
  works: Record<string, number>;
  work_surfaces: Record<string, number>;
  /** Photos kept only in the inspections of a surface (inspection-, question- and finding-level), per surface (Stage 14H.5). */
  inspection_surfaces: Record<string, number>;
}

export interface PhotoListParams {
  context?: PhotoContext;
  roomId?: string;
  surfaceId?: string;
  openingId?: string;
  /** Every photo of this room: the room itself, its surfaces and their openings (no other target filter). */
  inRoomId?: string;
  /** INSPECTION: one inspection (`inspectionId`), optionally one of its checklist questions. FINDING: one finding row. */
  inspectionId?: string;
  questionId?: string;
  findingId?: string;
  /** Every FINDING photo of one finding lineage (all rows of it); exclusive with the target filters. */
  lineageId?: string;
  /** WORK: with `surfaceId`, one occurrence of the surface's work plan (without it: every occurrence of the surface, detached ones included). */
  occurrenceKey?: string;
  /** Only the site contexts (object, room, surface, opening): the object-wide list, without inspection evidence. */
  siteOnly?: boolean;
  category?: PhotoCategory;
  includeInReport?: boolean;
  archived?: boolean;
  limit?: number;
  cursor?: string;
}

export interface PhotoAttachmentPatch {
  caption?: string | null;
  category?: PhotoCategory;
  include_in_report?: boolean;
  position?: number;
}

export interface PhotoAttachPayload {
  context: PhotoContext;
  room_id?: string;
  surface_id?: string;
  opening_id?: string;
  inspection_id?: string;
  question_id?: string;
  finding_id?: string;
  occurrence_key?: string;
  category?: PhotoCategory;
  caption?: string | null;
  include_in_report?: boolean;
}

/** Where a photo is attached: exactly the one id required by the context (none for PROJECT). */
export interface PhotoTarget {
  projectId: string;
  context: PhotoContext;
  roomId?: string;
  surfaceId?: string;
  openingId?: string;
  /** INSPECTION: the inspection, and the checklist question when the photo documents one answer. */
  inspectionId?: string;
  questionId?: string;
  /** FINDING: the finding row the photo is attached to, and its lineage (lets the counts follow; never sent). */
  findingId?: string;
  lineageId?: string;
  /** WORK: the planned work (with `surfaceId`) the photo documents. */
  occurrenceKey?: string;
  /** Category sent with the upload when the host suggests one (Realizacja: by the work's status); never part of the identity. */
  category?: PhotoCategory;
}
