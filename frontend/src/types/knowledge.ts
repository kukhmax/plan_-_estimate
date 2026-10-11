/** Stage 17D — the knowledge base (mirrors backend `schemas/knowledge.py` and `domain/knowledge/catalog.py`). Read only. */
import type { DocumentKind } from './document';

export type KnowledgeStatus = 'DRAFT' | 'APPROVED';
export type KnowledgeSourceKind = 'STATUTE' | 'NORM' | 'ITB' | 'OTHER';
export type KnowledgeLinkKind = 'RISK' | 'CLAUSE' | 'PHRASE' | 'DOCUMENT';

export interface KnowledgeMeta {
  version: number;
  updated_on: string;
  disclaimer_pl: string | null;
  disclaimer_ru: string | null;
  disclaimer_status: KnowledgeStatus;
  sources: number;
  entries: number;
  situations: number;
}

export interface KnowledgeEntryItem {
  code: string;
  kind: KnowledgeSourceKind;
  source: string;
  source_designation: string;
  locator: string | null;
  title_pl: string;
  title_ru: string;
  status: KnowledgeStatus;
  tags: string[];
}

export interface KnowledgeEntryList {
  items: KnowledgeEntryItem[];
  total: number;
}

export interface KnowledgeReviewNote {
  ref: string;
  text: string;
  status: 'OPEN' | 'RESOLVED';
}

export interface KnowledgeEntry {
  code: string;
  source: string;
  locator: string | null;
  title_pl: string;
  title_ru: string;
  summary_pl: string | null;
  explanation_ru: string | null;
  tags: string[];
  status: KnowledgeStatus;
  approved_by: string | null;
  approved_on: string | null;
  checked_on: string | null;
  review_notes: KnowledgeReviewNote[];
}

export interface KnowledgeSource {
  code: string;
  kind: KnowledgeSourceKind;
  title_pl: string;
  designation: string;
  url: string | null;
  status: KnowledgeStatus;
}

export interface KnowledgeLink {
  target_kind: KnowledgeLinkKind;
  target: string;
  entries: string[];
}

/** A place that points at an entry, named for a person (17E.1): a clause carries its paragraph and the title of its section. */
export interface KnowledgePlace {
  target_kind: KnowledgeLinkKind;
  target: string;
  section_number: number | null;
  clause_number: number | null;
  section_title_pl: string | null;
}

export interface KnowledgeEntryDetail {
  entry: KnowledgeEntry;
  source: KnowledgeSource;
  linked_from: KnowledgeLink[];
  places: KnowledgePlace[];
}

export interface KnowledgeSituationItem {
  code: string;
  title_pl: string;
  title_ru: string;
  status: KnowledgeStatus;
}

export interface KnowledgeAnswer {
  text_pl: string;
  text_ru: string;
  next: string;
}

export interface KnowledgeQuestion {
  id: string;
  text_pl: string;
  text_ru: string;
  answers: KnowledgeAnswer[];
}

export interface KnowledgeOutcome {
  id: string;
  steps_pl: string[];
  steps_ru: string[];
  entries: string[];
  phrases: string[];
  documents: DocumentKind[];
  lawyer: boolean;
}

export interface KnowledgeSituation {
  code: string;
  status: KnowledgeStatus;
  title_pl: string;
  title_ru: string;
  start: string;
  questions: KnowledgeQuestion[];
  outcomes: KnowledgeOutcome[];
}

/** One place of the application with the entries it points at (Stage 17E); the rows are the rows of the list. */
export interface KnowledgeLinkRow {
  target_kind: KnowledgeLinkKind;
  target: string;
  entries: KnowledgeEntryItem[];
}

export interface KnowledgeLinkIndex {
  items: KnowledgeLinkRow[];
}
