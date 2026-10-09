/** The contract of an object and the answers of its questionnaire (Stage 16E.1; mirrors backend `schemas/contract.py`). */
export type ContractStatus = 'DRAFT' | 'ISSUED' | 'SIGNED' | 'ARCHIVED';

/** What a stored answer looks like, by the kind of its question (see the backend `domain/contracts/answers.py`). */
export type RequirementAnswer = boolean | number | { min: number; max: number };
export type AnswerValue = string | number | boolean | string[] | Record<string, RequirementAnswer>;

export interface Contract {
  id: string;
  project_id: string;
  version: number;
  status: ContractStatus;
  answers: Record<string, AnswerValue>;
  /** The stored answers with the catalogue's defaults under them. */
  effective_answers: Record<string, AnswerValue>;
  /** The REQUIRED questions that have no answer yet, in the questionnaire's order. */
  missing_required: string[];
  questionnaire_version: number;
  created_at: string;
  updated_at: string;
}

export interface ContractListResponse {
  items: Contract[];
  total: number;
}

/** Only the answers that change; null clears an answer. */
export type ContractAnswersChange = Record<string, AnswerValue | null>;
