/** The archived contracts and protocols of all objects and their final deletion (AC-6). Mirrors `schemas/archived_document.py`. */
export type ArchivedDocumentKind = 'CONTRACT' | 'HANDOVER' | 'CONCEALED' | 'ACCEPTANCE' | 'DECISION' | 'DOWNTIME';

export interface ArchivedDocumentItem {
  kind: ArchivedDocumentKind;
  id: string;
  project_id: string;
  project_name: string;
  /** The version of a contract, the sequence of a protocol or an episode. */
  ordinal: number;
  /** Null: a draft that was never issued. */
  number: string | null;
  issued_at: string | null;
  archived_at: string;
}

export interface ArchivedDocuments {
  items: ArchivedDocumentItem[];
  /** The list holds the first 200; the total is whole. */
  total: number;
}

export interface DocumentPurgePreview {
  kind: ArchivedDocumentKind;
  target_id: string;
  ordinal: number;
  archived: boolean;
  issued: boolean;
  can_purge: boolean;
  /** Lines of the journal of sent documents: they stay (deleted on their own). */
  journal_lines: number;
  /** Of a contract: protocols and episodes (not archived) that refer to it; while there are any it is refused. */
  dependents: number;
}

export interface DocumentPurgeResult {
  purged: boolean;
}
