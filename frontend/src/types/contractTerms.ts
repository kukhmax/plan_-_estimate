import type { AnswerValue } from './contract';

/** "Moje standardowe warunki umowy" (UX walk B2): GET / PUT /api/contract-terms. */
export interface ContractTerms {
  answers: Record<string, AnswerValue>;
  /** The questions of the contract's questionnaire a standard term may answer. */
  keys: string[];
  /** The terms of the owner's latest contract (to start from), null when he has none. */
  latest: { answers: Record<string, AnswerValue>; project_name: string | null } | null;
}
