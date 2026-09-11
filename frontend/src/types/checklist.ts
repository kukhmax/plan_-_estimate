export type SubstrateValue =
  | 'CONCRETE'
  | 'GYPSUM_PLASTER'
  | 'CEMENT_LIME_PLASTER'
  | 'GYPSUM_BOARD'
  | 'PAINTED'
  | 'OTHER';

export type QualityLevelValue =
  | 'S1'
  | 'S2'
  | 'S3'
  | 'S4'
  | 'Q1'
  | 'Q2'
  | 'Q3'
  | 'Q4';

export type AnswerTypeValue =
  | 'BOOLEAN'
  | 'SINGLE_CHOICE'
  | 'MULTI_CHOICE'
  | 'NUMBER'
  | 'TEXT';

export type PlaneValue = 'FLOOR' | 'CEILING';

export interface ChecklistOption {
  id: string;
  position: number;
  key: string;
  label_key: string;
  finding_key: string | null;
}

export interface ChecklistQuestion {
  id: string;
  position: number;
  key: string;
  text_key: string;
  hint_key: string | null;
  unit_key: string | null;
  answer_type: AnswerTypeValue;
  finding_key: string | null;
  options: ChecklistOption[];
}

export interface ChecklistSection {
  id: string;
  key: string;
  position: number;
  title_key: string;
  description_key: string | null;
  questions: ChecklistQuestion[];
}

export interface ChecklistTemplate {
  id: string;
  code: string;
  version: number;
  substrate: SubstrateValue | null;
  title_key: string;
  active: boolean;
  sections: ChecklistSection[];
  created_at: string;
  updated_at: string;
}

export interface ChecklistTemplateListResponse {
  items: ChecklistTemplate[];
  total: number;
}