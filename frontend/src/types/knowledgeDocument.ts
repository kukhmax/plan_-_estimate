/** V2-7a — a document of the owner's own in the knowledge base. */
export const DOCUMENT_KINDS = ['STATUTE', 'NORM', 'MANUFACTURER', 'TEMPLATE', 'OTHER'] as const;
export type DocumentKindValue = (typeof DOCUMENT_KINDS)[number];

export interface KnowledgeDocumentItem {
  id: string;
  title: string;
  kind: DocumentKindValue;
  source_url: string | null;
  doc_date: string | null;
  tags: string[];
  file_name: string | null;
  file_mime: string | null;
  file_size: number | null;
  has_text: boolean;
  snippet: string | null;
  updated_at: string;
}

export interface KnowledgeDocumentDetail extends KnowledgeDocumentItem {
  when_to_use: string | null;
  body: string | null;
  created_at: string;
}

export interface KnowledgeDocumentList {
  items: KnowledgeDocumentItem[];
  total: number;
  max_documents: number;
  max_file_bytes: number;
}

/** What the form of a document sends: every field (the server replaces the document by it); the file only when it was chosen. */
export interface KnowledgeDocumentInput {
  title: string;
  kind: DocumentKindValue;
  source_url: string;
  doc_date: string;
  when_to_use: string;
  body: string;
  tags: string;
  file: File | null;
  remove_file: boolean;
}
